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


def _assessment_date(application):
    """Use the persisted timestamp; do not infer a clinical reference period."""
    value = application.get('recorded_at')
    return f" em {value[:10]}" if value else ''


def _comparable_results(current, previous):
    return (current.get('instrumento') == previous.get('instrumento')
            and current.get('versao') is not None
            and current.get('versao') == previous.get('versao'))


def summarize_sources(reading, diagnoses=(), interventions=()):
    """Derive only narrative/provenance from authorized, independently retained sources.

    No instrument calculation, weighting, clinical change threshold or causal inference.
    Check-in interpretation is consumed verbatim from describe_checkins.
    """
    sources = []
    parts = []
    if reading['metadata']['total_registros']:
        sources.append(dict(source='WELLBEING_CHECKIN', record_ids=list(reading['metadata']['record_ids'])))
        parts.append(reading['summary'])
    assessments = reading['evidence'].get('assessments', {})
    safety = []
    for key, label in (('phq9', 'PHQ-9'), ('gad7', 'GAD-7'), ('cbi', 'CBI')):
        group = assessments.get(key, {})
        latest = group.get('latest')
        if not latest:
            continue
        result = latest['result']
        history = group.get('applications', [])
        # Block A supplies deterministic descending date/id order.
        previous = next((a for a in history if a['application_id'] != latest['application_id']), None)
        comparable = previous and _comparable_results(result, previous['result'])
        used = [latest['application_id']]
        if key != 'cbi':
            parts.append(f"O {label} mais recente{_assessment_date(latest)} apresentou "
                         f"{result['score']}/{latest['score_max']}, na faixa {result['classificacao'].lower()} do instrumento.")
            if comparable:
                parts.append(f"Entre as duas aplicações mais recentes, o {label} passou de "
                             f"{previous['result']['score']}/{previous['score_max']} para "
                             f"{result['score']}/{latest['score_max']}; a diferença numérica não estabelece mudança clínica.")
                used.append(previous['application_id'])
        else:
            domains = result['dominios']
            values = '; '.join(f"{d['nome']}: {d['score']:g}/{d['score_max']}" for d in domains)
            parts.append(f"No CBI mais recente{_assessment_date(latest)}, foram registrados {values}.")
            old_domains = {d['codigo']: d for d in previous['result']['dominios']} if comparable else {}
            if old_domains and all(d['codigo'] in old_domains and d['itens'] == old_domains[d['codigo']]['itens']
                                   and d['score_max'] == old_domains[d['codigo']]['score_max'] for d in domains):
                changes = '; '.join(f"{d['nome']}: {old_domains[d['codigo']]['score']:g} para {d['score']:g}/{d['score_max']}" for d in domains)
                parts.append(f"Entre as duas aplicações mais recentes do CBI, {changes}; são diferenças numéricas por domínio, sem conclusão de resposta terapêutica.")
                used.append(previous['application_id'])
        if key == 'phq9':
            positive = [a for a in history if a['result'].get('metadata', {}).get('respostas', {}).get('phq9_9') in ('1', '2', '3')]
            if positive:
                signal = positive[0]
                safety.append(f"Houve resposta positiva ao item 9 do PHQ-9{_assessment_date(signal)}, que requer avaliação profissional específica de segurança; "
                              "essa resposta isolada não determina nível de risco. Não há informação de resolução nesta síntese.")
                if signal['application_id'] not in used:
                    used.append(signal['application_id'])
        sources.append(dict(source=result['instrumento'], application_ids=used))
    parts.extend(safety)
    active = sorted((d for d in diagnoses if d.status == 'ATIVO' and d.tipo == 'DIAGNOSTICO'),
                    key=lambda d: (d.data_diagnostico, d.id), reverse=True)
    if active:
        parts.append('Há diagnóstico ativo registrado por profissional nesta jornada.')
        sources.append(dict(source='DIAGNOSIS', ids=[d.id for d in active]))
    if interventions:
        latest_intervention = max(interventions, key=lambda i: (i.data_intervencao, i.id))
        parts.append(f"Há intervenção de {latest_intervention.tipo} registrada em {latest_intervention.data_intervencao.date().isoformat()} na jornada.")
        sources.append(dict(source='INTERVENTION', ids=[latest_intervention.id]))
    additional = any(s['source'] != 'WELLBEING_CHECKIN' for s in sources)
    if additional:
        parts.append('A síntese reúne evidências disponíveis para apoio à avaliação profissional, sem estabelecer causalidade, diagnóstico automático ou substituir julgamento clínico.')
    # With Check-ins only (or no source), preserve the prior narrative exactly.
    return (' '.join(parts) if additional else reading['summary']), sources
