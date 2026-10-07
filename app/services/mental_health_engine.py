"""Factual, per-dimension ordinal comparisons; no global score or diagnosis."""
from app.services.checkin_contract import OPTIONS, INTENSITY

DIMENSIONS = {
    "humor": ("Humor", OPTIONS),
    "ansiedade": ("Ansiedade/tensão", list(reversed(INTENSITY))),
    "estresse": ("Estresse percebido", list(reversed(INTENSITY))),
    "sono": ("Sono", OPTIONS),
    "energia": ("Energia", OPTIONS),
    "funcionamento": ("Funcionamento", OPTIONS),
    "trabalho": ("Bem-estar relacionado ao trabalho", OPTIONS),
}
DESCRIPTIONS = {
    "MELHORA_OBSERVACIONAL": "melhora observacional",
    "PIORA_OBSERVACIONAL": "piora observacional",
    "ESTABILIDADE_OBSERVACIONAL": "respostas sem variação observada",
    "OSCILACAO": "oscilação observada",
    "INSUFICIENTE": "dados insuficientes para comparação",
}
EMPTY = "Ainda não há Check-ins de Bem-Estar suficientes para produzir uma leitura clínica longitudinal neste contexto."


def _join_labels(dimensions):
    labels = [dimension["label"].lower() for dimension in dimensions]
    return " e ".join(labels) if len(labels) < 3 else ", ".join(labels[:-1]) + " e " + labels[-1]


def _narrative(count, evidence):
    """Present existing dimension states, without weighting or a global trend."""
    if count == 1:
        return ("Momento inicial do acompanhamento",
                "O primeiro Check-in descreve um momento observado do bem-estar. "
                "Ainda não há histórico suficiente para avaliar tendência ou persistência das respostas. "
                "Novos registros permitirão acompanhar mudanças ao longo do tempo.")
    groups = {state: [] for state in DESCRIPTIONS}
    for dimension in evidence["dimensions"].values():
        groups[dimension["state"]].append(dimension)
    improving = groups["MELHORA_OBSERVACIONAL"]
    worsening = groups["PIORA_OBSERVACIONAL"]
    oscillating = groups["OSCILACAO"]
    stable = groups["ESTABILIDADE_OBSERVACIONAL"]
    missing = groups["INSUFICIENTE"]
    comparable = len(evidence["dimensions"]) - len(missing)
    if not comparable:
        return ("Evidências insuficientes para leitura longitudinal",
                f"Há {count} Check-ins, mas as respostas disponíveis não permitem uma comparação longitudinal contínua. "
                "Ausências, respostas não comparáveis e “Não se aplica” permanecem como lacunas; "
                "não indicam melhora, piora ou estabilidade.")
    if oscillating:
        title = "Oscilação observada do bem-estar"
    elif improving and worsening:
        title = "Movimentos distintos nas dimensões do bem-estar"
    elif worsening:
        title = "Piora observacional em dimensões do bem-estar"
    elif improving:
        title = "Melhora observacional em dimensões do bem-estar"
    else:
        title = "Respostas estáveis nas dimensões acompanhadas"
    parts = [f"A comparação dos {count} Check-ins disponíveis mostra"]
    findings = []
    for group, phrase in ((oscillating, "alternância entre respostas mais e menos favoráveis"),
                          (worsening, "mudança para respostas menos favoráveis"),
                          (improving, "mudança para respostas mais favoráveis"),
                          (stable, "manutenção das respostas")):
        if group:
            scope = "nas dimensões comparáveis" if len(group) == len(evidence["dimensions"]) else "em " + _join_labels(group)
            findings.append(phrase + " " + scope)
    parts.append("; ".join(findings) + ".")
    if oscillating or (improving and worsening):
        parts.append("Esses movimentos não sustentam uma direção única para o conjunto do bem-estar.")
    if worsening or oscillating:
        parts.append("As mudanças observadas merecem acompanhamento nos próximos registros para verificar sua persistência.")
    elif improving:
        parts.append("A mudança observada não permite concluir recuperação ou manutenção da melhora nos próximos registros.")
    else:
        parts.append("Respostas sem variação não significam, por si só, bem-estar favorável ou ausência de necessidade de cuidado.")
    if missing:
        parts.append("A leitura é parcial: há dimensões sem comparação contínua por respostas ausentes ou não comparáveis. Essas lacunas não foram preenchidas.")
    parts.append("A síntese descreve os relatos disponíveis, sem conclusão diagnóstica ou causal.")
    return title, " ".join(parts)


def describe_checkins(checkins):
    records = sorted(checkins, key=lambda r: (r.data_hora, r.id))
    evidence = {"dimensions": {}, "help_requests": [], "relevant_events": []}
    result = dict(reference_date=None, risk=None, trend=None, summary=EMPTY,
                  clinical_state={"status": "SEM_DADOS", "titulo": "Sem leitura clínica",
                                  "descricao": "Ainda não há evidência observada neste contexto."},
                  metadata={"source": "BEM_ESTAR_V1", "total_registros": len(records),
                            "record_ids": [r.id for r in records]}, evidence=evidence, alerts=[])
    if not records:
        return result
    latest = records[-1]
    result["reference_date"] = latest.data_hora.date()
    for key, (label, options) in DIMENSIONS.items():
        values = [value for value, _ in options]
        observed = [r.respostas.get(key) for r in records]
        # Missing/NA/unknown values remain missing; never bridge a gap.
        valid = all(value in values for value in observed)
        state = "INSUFICIENTE"
        if len(records) >= 2 and valid:
            signs = { (values.index(b) > values.index(a)) - (values.index(b) < values.index(a))
                      for a, b in zip(observed, observed[1:]) } - {0}
            state = ("OSCILACAO" if len(signs) == 2 else "MELHORA_OBSERVACIONAL" if signs == {1}
                     else "PIORA_OBSERVACIONAL" if signs == {-1} else "ESTABILIDADE_OBSERVACIONAL")
        evidence["dimensions"][key] = {
            "label": label, "state": state,
            "observations": [{"record_id": r.id, "date": r.data_hora.isoformat(),
                              "value": value if value in values else None,
                              "reported_value": value} for r, value in zip(records, observed)]}
    for record in records:
        if record.respostas.get("pedido_ajuda") == "SIM":
            evidence["help_requests"].append({"record_id": record.id, "date": record.data_hora.isoformat()})
        if record.respostas.get("evento_relevante") == "SIM":
            evidence["relevant_events"].append({"record_id": record.id, "date": record.data_hora.isoformat(),
                                                "description": record.respostas.get("evento_descricao")})
    title, summary = _narrative(len(records), evidence)
    if latest.respostas.get("pedido_ajuda") == "SIM":
        alert = "Há solicitação explícita de apoio registrada no Check-in mais recente, recomendando atenção da equipe assistencial."
        result["alerts"].append(alert)
        summary += " " + alert
    elif evidence["help_requests"]:
        summary += " Há solicitação explícita de apoio em registro anterior; não há informação de resolução nesta leitura."
    if evidence["relevant_events"]:
        summary += " Foi registrado evento relevante no período, sem inferência de relação causal com as respostas."
    comparable = any(d["state"] != "INSUFICIENTE" for d in evidence["dimensions"].values())
    result.update(summary=summary, clinical_state={
        "status": "MOMENTO_OBSERVADO" if len(records) == 1 else "LEITURA_DESCRITIVA" if comparable else "INSUFICIENTE",
        "titulo": title,
        "descricao": "Relato de bem-estar por dimensão; não representa diagnóstico ou classificação de risco."})
    # A single global trend would collapse distinct dimensions; evidence holds each comparison.
    return result
