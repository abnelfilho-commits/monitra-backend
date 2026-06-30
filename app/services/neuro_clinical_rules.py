from app.services.eixos import calcular_eixo_dominante


def avaliar_regras(registros):

    alertas = []

    prioridade = "BAIXA"

    protocolo = "Acompanhamento de rotina"

    interpretacoes = []

    eixo = calcular_eixo_dominante(registros)

    if not registros:

        return {
            "alertas": [],
            "prioridade": prioridade,
            "protocolo": protocolo,
            "interpretacao": "Sem registros suficientes.",
            "eixo": eixo,
        }

    ultimo = registros[0]

    # ------------------------
    # Higiene do Sono
    # ------------------------

    if (
        getattr(ultimo, "sono_qualidade", None) is not None
        and ultimo.sono_qualidade <= 2
        and getattr(ultimo, "tempo_tela", None) in (
            "2_4H",
            "MAIS_4H",
        )
    ):

        alertas.append(
            "Possível comprometimento da higiene do sono associado ao tempo de tela."
        )

        interpretacoes.append(
            "Há indícios de que a exposição às telas possa estar contribuindo para piora do sono."
        )

    # ------------------------
    # Desregulação Sensorial
    # ------------------------

    irritabilidade = getattr(ultimo, "irritabilidade", None) or 0
    crise_sensorial = getattr(ultimo, "crise_sensorial", None) or 0

    if (
        irritabilidade >= 3
        and crise_sensorial >= 2
    ):

        prioridade = "ALTA"

        protocolo = "Reavaliação multiprofissional"

        alertas.append(
            "Sinais de desregulação sensorial."
        )

        interpretacoes.append(
            "Paciente apresenta associação entre irritabilidade elevada e crises sensoriais."
        )

    # ------------------------
    # Alimentação
    # ------------------------

    if (
        getattr(ultimo, "seletividade_alimentar", None)
        in (
            "MODERADA",
            "INTENSA",
        )
        and getattr(ultimo, "aceitou_alimento_novo", True) is False
    ):

        alertas.append(
            "Persistência de seletividade alimentar."
        )

        interpretacoes.append(
            "Observa-se manutenção da restrição alimentar com baixa aceitação de novos alimentos."
        )

    # ------------------------
    # Intestinal
    # ------------------------

    if (
        getattr(ultimo, "consistencia_fezes", None)
        in (
            1,
            2,
            6,
            7,
        )
    ):

        alertas.append(
            "Alteração do padrão intestinal."
        )

        interpretacoes.append(
            "Registro compatível com alteração gastrointestinal."
        )

    return {

        "alertas": alertas,

        "prioridade": prioridade,

        "protocolo": protocolo,

        "interpretacao": " ".join(interpretacoes),

        "eixo_dominante": eixo,

    }