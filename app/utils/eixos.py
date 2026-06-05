from __future__ import annotations

from typing import Any


TERMOS_EIXO = {
    "intestinal": [
        "intestino",
        "intestinal",
        "fezes",
        "constipacao",
        "constipação",
        "diarreia",
        "digestivo",
        "digestiva",
        "gastrointestinal",
        "evacuacao",
        "evacuação",
        "dor abdominal",
        "abdome",
        "barriga",
    ],
    "sensorial": [
        "sensorial",
        "sobrecarga sensorial",
        "hipersensibilidade",
        "hipossensibilidade",
        "estimulo",
        "estímulo",
        "barulho",
        "ruido",
        "ruído",
        "luz",
        "toque",
        "crise sensorial",
    ],
    "sono": [
        "sono",
        "insonia",
        "insônia",
        "noite ruim",
        "acordou",
        "despertou",
        "dormiu mal",
        "pouco sono",
    ],
    "comportamental": [
        "agitado",
        "agitação",
        "agressividade",
        "irritabilidade",
        "desorganizado",
        "desorganização",
        "desregulação",
        "desregulacao",
        "comportamento",
        "oposicao",
        "oposição",
        "crise de comportamento",
    ],
}


def normalizar_texto(texto: str | None) -> str:
    if not texto:
        return ""

    texto = texto.lower().strip()
    substituicoes = {
        "á": "a",
        "à": "a",
        "ã": "a",
        "â": "a",
        "é": "e",
        "ê": "e",
        "í": "i",
        "ó": "o",
        "ô": "o",
        "õ": "o",
        "ú": "u",
        "ç": "c",
    }
    for origem, destino in substituicoes.items():
        texto = texto.replace(origem, destino)

    return " ".join(texto.split())


def inicializar_scores() -> dict[str, int]:
    return {
        "intestinal": 0,
        "sensorial": 0,
        "sono": 0,
        "comportamental": 0,
    }


def inicializar_justificativas() -> dict[str, list[str]]:
    return {
        "intestinal": [],
        "sensorial": [],
        "sono": [],
        "comportamental": [],
    }


def pontuar_texto_observacao(
    observacao: str | None,
    scores: dict[str, int],
    justificativas: dict[str, list[str]],
) -> None:
    texto = normalizar_texto(observacao)

    if not texto:
        return

    for eixo, termos in TERMOS_EIXO.items():
        for termo in termos:
            termo_norm = normalizar_texto(termo)
            if termo_norm in texto:
                scores[eixo] += 1
                justificativas[eixo].append(f"Observação menciona '{termo}'")


def pontuar_registro(
    registro: Any,
    scores: dict[str, int],
    justificativas: dict[str, list[str]],
) -> None:
    sono_qualidade = getattr(registro, "sono_qualidade", None)
    irritabilidade = getattr(registro, "irritabilidade", None)
    crise_sensorial = getattr(registro, "crise_sensorial", None)
    consistencia_fezes = getattr(registro, "consistencia_fezes", None)
    evacuacao = getattr(registro, "evacuacao", None)
    observacao = getattr(registro, "observacao", None)

    # Sono
    if sono_qualidade is not None and sono_qualidade <= 2:
        scores["sono"] += 2
        justificativas["sono"].append("Sono de baixa qualidade em registro recente")

    # Comportamental
    if irritabilidade is not None and irritabilidade >= 3:
        scores["comportamental"] += 2
        justificativas["comportamental"].append("Irritabilidade elevada em registro recente")

    # Sensorial
    if crise_sensorial is not None and crise_sensorial >= 2:
        scores["sensorial"] += 2
        justificativas["sensorial"].append("Crise sensorial recorrente/intensa em registro recente")

    # Intestinal
    if consistencia_fezes is not None and (consistencia_fezes <= 2 or consistencia_fezes >= 6):
        scores["intestinal"] += 2
        justificativas["intestinal"].append("Consistência das fezes fora da faixa esperada")

    # Intestinal - regra conservadora
    # Ajuste aqui se no seu domínio 'evacuacao=False' tiver leitura clínica relevante
    if evacuacao is False:
        scores["intestinal"] += 1
        justificativas["intestinal"].append("Alteração de evacuação no período")

    pontuar_texto_observacao(observacao, scores, justificativas)


def deduplicar(lista: list[str]) -> list[str]:
    vistos = set()
    resultado = []
    for item in lista:
        if item not in vistos:
            vistos.add(item)
            resultado.append(item)
    return resultado


def calcular_eixo_dominante(registros: list[Any]) -> dict[str, Any]:
    """
    Calcula uma leitura observacional simples por eixo com base
    nos registros mais recentes do paciente.
    """
    if not registros:
        return {
            "eixo_dominante": None,
            "eixo_dominante_label": None,
            "confianca_eixo": "baixa",
            "base_sustentacao": [],
            "scores_eixos": {},
        }

    scores = inicializar_scores()
    justificativas = inicializar_justificativas()

    # Usa até 7 registros mais recentes
    registros_ordenados = sorted(
        registros,
        key=lambda r: getattr(r, "data", None) or getattr(r, "created_at", None),
        reverse=True,
    )[:7]

    for registro in registros_ordenados:
        pontuar_registro(registro, scores, justificativas)

    eixo_ordenado = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    eixo_top, score_top = eixo_ordenado[0]
    score_segundo = eixo_ordenado[1][1] if len(eixo_ordenado) > 1 else 0

    # Evidência mínima para exibir
    if score_top < 3:
        return {
            "eixo_dominante": None,
            "eixo_dominante_label": None,
            "confianca_eixo": "baixa",
            "base_sustentacao": [],
            "scores_eixos": scores,
        }

    # Confiança simples
    if score_top >= 6 and (score_top - score_segundo) >= 2:
        confianca = "alta"
    elif score_top >= 4:
        confianca = "media"
    else:
        confianca = "baixa"

    labels = {
        "intestinal": "Intestinal",
        "sensorial": "Sensorial",
        "sono": "Sono",
        "comportamental": "Comportamental",
    }

    base_sustentacao = deduplicar(justificativas[eixo_top])[:3]

    return {
        "eixo_dominante": eixo_top,
        "eixo_dominante_label": labels[eixo_top],
        "confianca_eixo": confianca,
        "base_sustentacao": base_sustentacao,
        "scores_eixos": scores,
    }
