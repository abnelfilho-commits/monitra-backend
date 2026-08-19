from statistics import mean
from types import SimpleNamespace
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.services.neuro_clinical_rules import avaliar_regras

MODULO_NEURO_ID = 1


def _to_int(valor):
    if valor is None or valor == "":
        return None
    try:
        return int(valor)
    except (ValueError, TypeError):
        return None


def _score_sono(valor):
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor >= 4:
        return 0
    if valor == 3:
        return 1
    return 2


def _score_irritabilidade(valor):
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor <= 1:
        return 0
    if valor == 2:
        return 1
    return 2


def _score_crise_sensorial(valor):
    valor = _to_int(valor)
    if valor is None:
        return 0
    if valor == 0:
        return 0
    if valor == 1:
        return 1
    return 2


def _score_evacuacao(valor):
    if valor is None:
        return 0
    return 0 if valor is True else 1


def _score_bristol(valor):
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


def _score_tempo_tela(valor):
    if not valor:
        return 0
    if valor == "MENOS_1H":
        return 0
    if valor == "1_2H":
        return 1
    if valor == "2_4H":
        return 2
    if valor == "MAIS_4H":
        return 3
    return 0


def _score_seletividade(valor):
    if not valor:
        return 0
    if valor == "NENHUMA":
        return 0
    if valor == "LEVE":
        return 1
    if valor == "MODERADA":
        return 2
    if valor == "GRAVE":
        return 3
    return 0

def _score_aceitou_alimento_novo(valor):
    if valor is None:
        return 0
    return 0 if valor is True else 1


def classificar_risco_por_pontuacao(pontos: int) -> str:
    if pontos >= 9:
        return "alto_risco"
    if pontos >= 4:
        return "atencao"
    return "baixo_risco"


def calcular_pontuacao_risco_registro(registro) -> int:
    return (
        _score_sono(getattr(registro, "sono_qualidade", None))
        + _score_irritabilidade(getattr(registro, "irritabilidade", None))
        + _score_crise_sensorial(getattr(registro, "crise_sensorial", None))
        + _score_evacuacao(getattr(registro, "evacuacao", None))
        + _score_bristol(getattr(registro, "consistencia_fezes", None))
        + _score_tempo_tela(getattr(registro, "tempo_tela", None))
        + _score_seletividade(getattr(registro, "seletividade_alimentar", None))
        + _score_aceitou_alimento_novo(getattr(registro, "aceitou_alimento_novo", None))
    )


def obter_registros_neuro_paciente(db: Session, paciente_id: int):
    rows = db.execute(text("""
        SELECT
            rl.id,
            rl.paciente_id,
            rl.data_registro AS data,
            rl.criado_em AS created_at,
            rl.origem,

            MAX(CASE WHEN cf.nome_campo = 'sono_qualidade'
                THEN rr.valor_numero END) AS sono_qualidade,

            COALESCE(
                BOOL_OR(
                    CASE
                        WHEN cf.nome_campo = 'evacuacao'
                        THEN rr.valor_booleano
                    END
                ),
                false
            ) AS evacuacao,

            MAX(CASE WHEN cf.nome_campo = 'consistencia_fezes'
                THEN rr.valor_numero END) AS consistencia_fezes,

            MAX(CASE WHEN cf.nome_campo = 'irritabilidade'
                THEN rr.valor_numero END) AS irritabilidade,

            MAX(CASE WHEN cf.nome_campo = 'crise_sensorial'
                THEN rr.valor_numero END) AS crise_sensorial,

            MAX(CASE WHEN cf.nome_campo = 'tempo_tela'
                THEN rr.valor_texto END) AS tempo_tela,

            MAX(CASE WHEN cf.nome_campo = 'seletividade_alimentar'
                THEN rr.valor_texto END) AS seletividade_alimentar,

            COALESCE(
                BOOL_OR(
                    CASE
                        WHEN cf.nome_campo = 'aceitou_alimento_novo'
                        THEN rr.valor_booleano
                    END
                ),
                false
            ) AS aceitou_alimento_novo,

            MAX(CASE WHEN cf.nome_campo = 'observacao'
                THEN rr.valor_texto END) AS observacao
        FROM registros_longitudinais rl
        LEFT JOIN respostas_registro rr
            ON rr.registro_id = rl.id
        LEFT JOIN campos_formulario cf
            ON cf.id = rr.campo_id
        LEFT JOIN formularios_modulo fm
            ON fm.id = rl.formulario_id

        WHERE rl.paciente_id = :paciente_id
        AND rl.modulo_id = :modulo_id
        AND fm.tipo = 'REGISTRO_DIARIO'


        GROUP BY
            rl.id,
            rl.paciente_id,
            rl.data_registro,
            rl.criado_em,
            rl.origem

        ORDER BY rl.data_registro DESC, rl.id DESC
    """), {
        "paciente_id": paciente_id,
        "modulo_id": MODULO_NEURO_ID,
    }).fetchall()

    return [SimpleNamespace(**dict(r._mapping)) for r in rows]


def _pontuacao_media(registros) -> float:
    if not registros:
        return 0.0
    return mean(calcular_pontuacao_risco_registro(r) for r in registros)


def calcular_tendencia(registros_ordenados_desc) -> str:
    if len(registros_ordenados_desc) < 2:
        return "sem_dados"

    recentes = registros_ordenados_desc[:3]
    anteriores = registros_ordenados_desc[3:6]

    if not anteriores:
        return "estavel"

    delta = _pontuacao_media(recentes) - _pontuacao_media(anteriores)

    if delta >= 2:
        return "piora"
    if delta <= -2:
        return "melhora"
    return "estavel"


def gerar_resumo_status(registro, risco_atual: str, tendencia: str) -> str:
    if not registro:
        return "Paciente sem registros clínicos suficientes para análise."

    sinais = []

    sono = _to_int(getattr(registro, "sono_qualidade", None))
    irrit = _to_int(getattr(registro, "irritabilidade", None))
    crise = _to_int(getattr(registro, "crise_sensorial", None))
    fezes = _to_int(getattr(registro, "consistencia_fezes", None))
    tempo_tela = getattr(registro, "tempo_tela", None)
    seletividade = getattr(registro, "seletividade_alimentar", None)
    aceitou_novo = getattr(registro, "aceitou_alimento_novo", None)

    if sono is not None and sono <= 2:
        sinais.append("sono de baixa qualidade")

    if irrit is not None and irrit >= 3:
        sinais.append("irritabilidade elevada")

    if crise is not None and crise >= 2:
        sinais.append("crise sensorial frequente")

    if getattr(registro, "evacuacao", None) is False:
        sinais.append("ausência de evacuação no registro")

    if fezes in (1, 7):
        sinais.append("alteração intestinal importante")

    if tempo_tela in ("2_4H", "MAIS_4H"):
        sinais.append("tempo de tela elevado")

    if seletividade in ("MODERADA", "GRAVE"):
        sinais.append("seletividade alimentar relevante")

    if aceitou_novo is False:
        sinais.append("recusa de novo alimento")

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

def calcular_painel_clinico(registros):
    registros_recentes = registros[:5]
    registros_atuais = registros_recentes[:2]
    registros_historicos = registros_recentes[2:]

    if not registros_recentes:
        return {
            "sono": 0,
            "irritabilidade": 0,
            "crise_sensorial": 0,
            "intestinal": 0,
            "alimentacao": 0,
            "alimentacao_historico": 0,
            "total_registros": 0,
        }

    def media_valores(campo):
        valores = [
            _to_int(getattr(r, campo, None))
            for r in registros_recentes
            if _to_int(getattr(r, campo, None)) is not None
        ]
        if not valores:
            return 0
        return round(sum(valores) / len(valores))

    def avaliar_alimentacao(registros_avaliados):
        ocorrencias = 0

        for r in registros_avaliados:
            seletividade = getattr(
                r,
                "seletividade_alimentar",
                None
            )
            aceitou_novo = getattr(
                r,
                "aceitou_alimento_novo",
                None
            )

            if seletividade in ("MODERADA", "GRAVE"):
                ocorrencias += 1

            if aceitou_novo is False:
                ocorrencias += 1

        return ocorrencias

    intestinal_score = 0

    for r in registros_recentes:
        bristol = _to_int(
            getattr(r, "consistencia_fezes", None)
        )
        evacuacao = getattr(r, "evacuacao", None)

        if bristol in (1, 2, 6, 7):
            intestinal_score += 1

        if evacuacao is False:
            intestinal_score += 1

    return {
        "sono": media_valores("sono_qualidade"),
        "irritabilidade": media_valores("irritabilidade"),
        "crise_sensorial": media_valores("crise_sensorial"),
        "intestinal": intestinal_score,
        "alimentacao": avaliar_alimentacao(registros_atuais),
        "alimentacao_historico": avaliar_alimentacao(
            registros_historicos
        ),
        "total_registros": len(registros_recentes),
    }

def gerar_resumo_clinico_painel(painel):
    if not painel or painel.get("total_registros", 0) == 0:
        return "Ainda não há dados clínicos suficientes para gerar análise."

    sinais = []

    alimentacao_atual = painel.get("alimentacao", 0)
    alimentacao_historico = painel.get(
        "alimentacao_historico",
        0
    )

    if painel.get("sono", 0) > 0 and painel["sono"] <= 2:
        sinais.append("sono de baixa qualidade")

    if painel.get("irritabilidade", 0) >= 3:
        sinais.append("irritabilidade elevada")

    if painel.get("crise_sensorial", 0) >= 2:
        sinais.append("crises sensoriais recorrentes")

    if painel.get("intestinal", 0) >= 2:
        sinais.append("alterações intestinais recorrentes")

    if alimentacao_atual >= 2:
        sinais.append(
            "seletividade alimentar relevante nos registros mais recentes"
        )

    if (
        alimentacao_atual == 0
        and alimentacao_historico > 0
        and not sinais
    ):
        return (
            "Os registros mais recentes sugerem estabilidade clínica, "
            "com parâmetros alimentares atualmente satisfatórios e "
            "melhora em relação ao histórico recente."
        )

    if not sinais:
        return (
            "Os registros recentes sugerem estabilidade clínica relativa, "
            "sem sinais críticos predominantes."
        )

    return (
        "Nos registros recentes, observa-se "
        + ", ".join(sinais)
        + ". O quadro sugere necessidade de acompanhamento clínico longitudinal."
    )


def classificar_momento_clinico(risco, tendencia, prioridade):
    if risco == "alto_risco" or prioridade == "ALTA":
        return {
            "status": "CRITICO",
            "titulo": "Atenção clínica intensificada",
            "descricao": "Há sinais recentes que indicam necessidade de acompanhamento mais próximo.",
        }

    if risco == "atencao" or tendencia == "piora":
        return {
            "status": "ATENCAO",
            "titulo": "Alerta clínico",
            "descricao": "O quadro geral sugere atenção clínica e monitoramento longitudinal.",
        }

    if risco == "baixo_risco":
        return {
            "status": "ESTAVEL",
            "titulo": "Estabilidade clínica",
            "descricao": "Os registros recentes sugerem quadro globalmente estável.",
        }

    return {
        "status": "SEM_DADOS",
        "titulo": "Sem leitura clínica",
        "descricao": "Ainda não há base suficiente para interpretação automática.",
    }

def analisar_paciente(db: Session, paciente_id: int):

    registros = obter_registros_neuro_paciente(
        db,
        paciente_id
    )

    ultimo = registros[0] if registros else None

    pontuacao = (
        calcular_pontuacao_risco_registro(ultimo)
        if ultimo
        else 0
    )

    risco = (
        classificar_risco_por_pontuacao(pontuacao)
        if ultimo
        else "sem_dados"
    )

    tendencia = calcular_tendencia(registros)

    resumo = gerar_resumo_status(
        ultimo,
        risco,
        tendencia
    )

    regras = avaliar_regras(registros)

    painel_clinico = calcular_painel_clinico(registros)

    resumo_clinico = gerar_resumo_clinico_painel(
        painel_clinico
    )

    momento_clinico = classificar_momento_clinico(
        risco,
        tendencia,
        regras["prioridade"]
    )

    return {

        "pontuacao_risco": pontuacao,

        "risco_atual": risco,

        "tendencia": tendencia,

        "status_resumido": resumo,

        "total_registros": len(registros),

        "ultimo_registro": (
            ultimo.data
            if ultimo
            else None
        ),

        "alertas": regras["alertas"],

        "prioridade": regras["prioridade"],

        "protocolo": regras["protocolo"],

        "interpretacao": regras["interpretacao"],

        "eixo_dominante": regras.get("eixo_dominante"),
        
        "painel_clinico": painel_clinico,

        "resumo_clinico": resumo_clinico,

        "momento_clinico": momento_clinico,

    }