from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import mean
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.models.registro import RegistroDiario


# 🔧 Normalizador universal
def _to_int(valor):
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None


def _score_sono(valor: Optional[int]) -> int:
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor >= 4:
        return 0
    if valor == 3:
        return 1
    return 2


def _score_irritabilidade(valor: Optional[int]) -> int:
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor <= 1:
        return 0
    if valor == 2:
        return 1
    return 2


def _score_crise_sensorial(valor: Optional[int]) -> int:
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor == 0:
        return 0
    if valor == 1:
        return 1
    return 2


def _score_evacuacao(valor: Optional[bool]) -> int:
    if valor is None:
        return 0
    return 0 if valor is True else 1


def _score_bristol(valor: Optional[int]) -> int:
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor in (3, 4, 5):
        return 0
    if valor in (2, 6):
        return 1
    if valor in (1, 7):
        return 2
    return 0


def calcular_pontuacao_risco_registro(registro: RegistroDiario) -> int:
    return (
        _score_sono(registro.sono_qualidade)
        + _score_irritabilidade(registro.irritabilidade)
        + _score_crise_sensorial(registro.crise_sensorial)
        + _score_evacuacao(registro.evacuacao)
        + _score_bristol(registro.consistencia_fezes)
    )


def classificar_risco_por_pontuacao(pontos: int) -> str:
    if pontos >= 6:
        return "alto_risco"
    if pontos >= 3:
        return "atencao"
    return "baixo_risco"


def _pontuacao_media(registros: list[RegistroDiario]) -> float:
    if not registros:
        return 0.0
    return mean(calcular_pontuacao_risco_registro(r) for r in registros)


def calcular_tendencia(registros_ordenados_desc: list[RegistroDiario]) -> str:
    if len(registros_ordenados_desc) < 2:
        return "sem_dados"

    recentes = registros_ordenados_desc[:3]
    anteriores = registros_ordenados_desc[3:6]

    if not anteriores:
        return "estavel"

    media_recentes = _pontuacao_media(recentes)
    media_anteriores = _pontuacao_media(anteriores)
    delta = media_recentes - media_anteriores

    if delta >= 1:
        return "piora"
    if delta <= -1:
        return "melhora"
    return "estavel"


def gerar_resumo_status(registro: Optional[RegistroDiario], risco_atual: str, tendencia: str) -> str:
    if not registro:
        return "Paciente sem registros clínicos suficientes para análise."

    sinais = []

    sono = _to_int(registro.sono_qualidade)
    irrit = _to_int(registro.irritabilidade)
    crise = _to_int(registro.crise_sensorial)
    fezes = _to_int(registro.consistencia_fezes)

    if sono is not None and sono <= 2:
        sinais.append("sono de baixa qualidade")

    if irrit is not None and irrit >= 3:
        sinais.append("irritabilidade elevada")

    if crise is not None and crise >= 2:
        sinais.append("crise sensorial frequente")

    if registro.evacuacao is False:
        sinais.append("ausência de evacuação no registro")

    if fezes in (1, 7):
        sinais.append("alteração intestinal importante")

    base = {
        "baixo_risco": "Paciente em baixo risco clínico",
        "atencao": "Paciente em atenção clínica",
        "alto_risco": "Paciente em alto risco clínico",
    }.get(risco_atual, "Paciente sem classificação clínica")

    tendencia_txt = {
        "melhora": "com tendência de melhora",
        "estavel": "com tendência estável",
        "piora": "com tendência de piora",
        "sem_dados": "sem dados suficientes de tendência",
    }.get(tendencia, "sem dados suficientes de tendência")

    if sinais:
        return f"{base}, {tendencia_txt}. Principais sinais: {', '.join(sinais)}."
    return f"{base}, {tendencia_txt}."


def obter_registros_paciente(db: Session, paciente_id: int) -> list[RegistroDiario]:
    return (
        db.query(RegistroDiario)
        .filter(RegistroDiario.paciente_id == paciente_id)
        .order_by(RegistroDiario.data.desc(), RegistroDiario.id.desc())
        .all()
    )


def analisar_risco_paciente(db: Session, paciente: Paciente) -> dict:
    registros = obter_registros_paciente(db, paciente.id)
    ultimo_registro = registros[0] if registros else None

    pontuacao = calcular_pontuacao_risco_registro(ultimo_registro) if ultimo_registro else 0
    risco_atual = classificar_risco_por_pontuacao(pontuacao) if ultimo_registro else "sem_dados"
    tendencia = calcular_tendencia(registros)
    resumo = gerar_resumo_status(ultimo_registro, risco_atual, tendencia)

    return {
        "paciente_id": paciente.id,
        "nome": paciente.nome,
        "clinica_id": paciente.clinica_id,
        "profissional_id": getattr(paciente, "profissional_id", None),
        "profissional_nome": (
            paciente.profissional.nome if getattr(paciente, "profissional", None) else None
        ),
        "risco_atual": risco_atual,
        "tendencia": tendencia,
        "pontuacao_risco": pontuacao,
        "ultimo_registro": ultimo_registro.data if ultimo_registro else None,
        "status_resumido": resumo,
        "total_registros": len(registros),
    }


def analisar_mapa_risco_clinica(db: Session, clinica_id: int) -> dict:
    pacientes = (
        db.query(Paciente)
        .filter(Paciente.clinica_id == clinica_id, Paciente.ativo == True)
        .all()
    )

    analises = [analisar_risco_paciente(db, p) for p in pacientes]

    contagem_risco = Counter(a["risco_atual"] for a in analises)
    contagem_tendencia = Counter(a["tendencia"] for a in analises)

    pacientes_em_alerta = [a for a in analises if a["risco_atual"] in ("atencao", "alto_risco")]
    pacientes_em_piora = [a for a in analises if a["tendencia"] == "piora"]
    pacientes_alto_risco = [a for a in analises if a["risco_atual"] == "alto_risco"]

    pacientes_ordenados = sorted(
        analises,
        key=lambda x: (x["pontuacao_risco"], x["total_registros"]),
        reverse=True,
    )

    return {
        "clinica_id": clinica_id,
        "total_pacientes": len(analises),
        "baixo_risco": contagem_risco.get("baixo_risco", 0),
        "atencao": contagem_risco.get("atencao", 0),
        "alto_risco": contagem_risco.get("alto_risco", 0),
        "sem_dados": contagem_risco.get("sem_dados", 0),
        "em_melhora": contagem_tendencia.get("melhora", 0),
        "estaveis": contagem_tendencia.get("estavel", 0),
        "em_piora": contagem_tendencia.get("piora", 0),
        "pacientes_em_alerta": pacientes_em_alerta[:10],
        "pacientes_em_piora": pacientes_em_piora[:10],
        "pacientes_alto_risco": pacientes_alto_risco[:10],
        "ranking_risco": pacientes_ordenados[:20],
        "gerado_em": datetime.now(),
    }


def obter_evolucao_paciente(db: Session, paciente: Paciente) -> list[dict]:
    registros = (
        db.query(RegistroDiario)
        .filter(RegistroDiario.paciente_id == paciente.id)
        .order_by(RegistroDiario.data.asc(), RegistroDiario.id.asc())
        .all()
    )

    serie = []

    for r in registros:
        pontos = calcular_pontuacao_risco_registro(r)
        risco = classificar_risco_por_pontuacao(pontos)

        serie.append(
            {
                "data": r.data,
                "pontuacao_risco": pontos,
                "risco": risco,
                "sono_qualidade": _to_int(r.sono_qualidade),
                "irritabilidade": _to_int(r.irritabilidade),
                "crise_sensorial": _to_int(r.crise_sensorial),
                "evacuacao": r.evacuacao,
                "consistencia_fezes": _to_int(r.consistencia_fezes),
            }
        )

    return serie
