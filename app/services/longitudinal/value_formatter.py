import json


def normalizar_chave(valor):
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)

    return valor


def obter_label_opcao(opcoes, valor):
    if valor is None or not opcoes:
        return None

    if isinstance(opcoes, str):
        try:
            opcoes = json.loads(opcoes)
        except Exception:
            return None

    chave = normalizar_chave(valor)

    for opcao in opcoes:
        if opcao.get("valor") == chave:
            return opcao.get("label")

        if str(opcao.get("valor")) == str(chave):
            return opcao.get("label")

    return None


def formatar_valor_clinico(campo, valor, opcoes=None):
    if valor is None:
        return None

    label_opcao = obter_label_opcao(opcoes, valor)

    if label_opcao:
        return label_opcao

    if isinstance(valor, bool):
        return "Sim" if valor else "Não"

    if valor in ["Sim", "Não"]:
        return valor

    return valor