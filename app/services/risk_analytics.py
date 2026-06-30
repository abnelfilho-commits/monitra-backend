from __future__ import annotations

from collections import Counter
from datetime import datetime

from sqlalchemy.orm import Session

from app.models.paciente import Paciente
from app.services.neuro_engine import (
    analisar_paciente,
    obter_registros_neuro_paciente,
    calcular_pontuacao_risco_registro,
    classificar_risco_por_pontuacao,
)


def analisar_risco_paciente(db: Session, paciente: Paciente) -> dict:

    analise = analisar_paciente(
        db,
        paciente.id
    )

    analise.update({

        "paciente_id": paciente.id,

        "nome": paciente.nome,

        "clinica_id": paciente.clinica_id,

        "profissional_id": getattr(
            paciente,
            "profissional_id",
            None
        ),

        "profissional_nome": (
            paciente.profissional.nome
            if getattr(paciente, "profissional", None)
            else None
        )

    })

    return analise


def analisar_mapa_risco_clinica(db: Session, clinica_id: int) -> dict:
    pacientes = (
        db.query(Paciente)
        .filter(Paciente.clinica_id == clinica_id, Paciente.ativo == True)
        .all()
    )

    analises = [analisar_risco_paciente(db, p) for p in pacientes]

    contagem_risco = Counter(a["risco_atual"] for a in analises)
    contagem_tendencia = Counter(a["tendencia"] for a in analises)

    pacientes_em_alerta = [
        a for a in analises
        if a["risco_atual"] in ("atencao", "alto_risco")
    ]

    pacientes_em_piora = [
        a for a in analises
        if a["tendencia"] == "piora"
    ]

    pacientes_alto_risco = [
        a for a in analises
        if a["risco_atual"] == "alto_risco"
    ]

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
    registros = list(reversed(obter_registros_neuro_paciente(db, paciente.id)))

    serie = []

    for r in registros:
        pontos = calcular_pontuacao_risco_registro(r)
        risco = classificar_risco_por_pontuacao(pontos)

        serie.append({
            "data": r.data,
            "pontuacao_risco": pontos,
            "risco": risco,
            "sono_qualidade": r.sono_qualidade,
            "irritabilidade": r.irritabilidade,
            "crise_sensorial": r.crise_sensorial,
            "evacuacao": r.evacuacao,
            "consistencia_fezes": r.consistencia_fezes,
            "tempo_tela": r.tempo_tela,
            "seletividade_alimentar": r.seletividade_alimentar,
            "aceitou_alimento_novo": r.aceitou_alimento_novo,
        })

    return serie