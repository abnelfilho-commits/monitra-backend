from statistics import mean


def calcular_score(registro):

    score = 0

    glicemia = (
        registro.get("glicemia")
        or registro.get("glicemia_jejum")
        or 0
    )
   
    sistolica = (
        registro.get("pressao_sistolica")
        or 0
    )

    diastolica = (
        registro.get("pressao_diastolica")
        or 0
    )

    peso = (
        registro.get("peso")
        or 0
    )

    atividade = registro.get("atividade_fisica")
    sono = registro.get("sono")
    humor = registro.get("humor")

    # GLICEMIA

    if glicemia >= 250:
        score += 4
    elif glicemia >= 180:
        score += 3
    elif glicemia >= 140:
        score += 2
    elif glicemia >= 110:
        score += 1

    # PRESSÃO

    if sistolica >= 180 or diastolica >= 120:
        score += 4
    elif sistolica >= 160 or diastolica >= 100:
        score += 3
    elif sistolica >= 140 or diastolica >= 90:
        score += 2
    elif sistolica >= 130:
        score += 1

    # PESO

    if peso >= 140:
        score += 3
    elif peso >= 120:
        score += 2
    elif peso >= 100:
        score += 1

    # ATIVIDADE FÍSICA

    if atividade == "baixa":
        score += 1

    # SONO

    if sono == "ruim":
        score += 1

    # HUMOR

    if humor in ["ansioso", "deprimido"]:
        score += 1
    
    score = min(score, 10)

    return score


def classificar_risco(score):

    if score >= 10:
        return "critico"

    if score >= 6:
        return "alto"
    
    if score >= 3:
        return "moderado"

    return "baixo"


def definir_protocolo(score):

    if score >= 8:
        return "intensivo_cardiometabolico"

    if score >= 4:
        return "monitoramento_ativo"

    return "preventivo"


def gerar_leitura_clinica(registro, score):

    riscos = []

    glicemia = registro.get("glicemia_jejum") or 0
    sistolica = registro.get("pressao_sistolica") or 0
    peso = registro.get("peso") or 0

    if glicemia >= 180:
        riscos.append("hiperglicemia persistente")

    if sistolica >= 160:
        riscos.append("hipertensão importante")

    if peso >= 120:
        riscos.append("obesidade severa")

    if not riscos:
        return (
            "Paciente em acompanhamento longitudinal "
            "cardiometabólico preventivo."
        )

    texto = ", ".join(riscos)

    return (
        f"Paciente apresenta {texto}, "
        f"com necessidade de acompanhamento "
        f"longitudinal contínuo."
    )


def calcular_tendencia(registros):

    if len(registros) < 3:
        return "estável"

    scores = [r["score_clinico"] for r in registros]

    media_antiga = mean(scores[: len(scores)//2])
    media_recente = mean(scores[len(scores)//2 :])

    if media_recente > media_antiga:
        return "piora"

    if media_recente < media_antiga:
        return "melhora"

    return "estável"
