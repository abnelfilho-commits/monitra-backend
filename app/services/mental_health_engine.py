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
    factual, comparisons = [], []
    for key, (label, options) in DIMENSIONS.items():
        values = [value for value, _ in options]
        labels = dict(options)
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
        value = latest.respostas.get(key)
        if value in labels:
            factual.append(f"{label}: {labels[value].lower()}")
        if len(records) >= 2:
            comparisons.append(f"{label}: {DESCRIPTIONS[state]}")
    for record in records:
        if record.respostas.get("pedido_ajuda") == "SIM":
            evidence["help_requests"].append({"record_id": record.id, "date": record.data_hora.isoformat()})
        if record.respostas.get("evento_relevante") == "SIM":
            evidence["relevant_events"].append({"record_id": record.id, "date": record.data_hora.isoformat(),
                                                "description": record.respostas.get("evento_descricao")})
    summary = ("Primeiro registro de Bem-Estar disponível neste contexto. " if len(records) == 1
               else f"Leitura descritiva de {len(records)} Check-ins de Bem-Estar neste contexto. ")
    summary += ("No Check-in mais recente, " + "; ".join(factual) + ". " if factual
                else "O Check-in mais recente não contém dimensões comparáveis. ")
    summary += ("Ainda não há histórico suficiente para avaliar tendência." if len(records) == 1
                else "Comparação por dimensão: " + "; ".join(comparisons) + ".")
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
        "titulo": "Momento observado" if len(records) == 1 else "Leitura longitudinal descritiva" if comparable else "Dados insuficientes para comparação",
        "descricao": "Relato de bem-estar por dimensão; não representa diagnóstico ou classificação de risco."})
    # A single global trend would collapse distinct dimensions; evidence holds each comparison.
    return result
