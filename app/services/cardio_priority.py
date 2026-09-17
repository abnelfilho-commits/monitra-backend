"""Approved Cardio operational policy. No clinical reclassification or score."""
ORDER = ('RISCO_CLINICO_CRITICO', 'RISCO_CLINICO_ALTO', 'CONTINUIDADE_CRITICA',
         'RISCO_CLINICO_MODERADO', 'CONTINUIDADE_ATENCAO')
RISK_SIGNALS = {'critico': ORDER[0], 'alto': ORDER[1], 'moderado': ORDER[3]}
CONTINUITY_SIGNALS = {'CRITICA': ORDER[2], 'ATENCAO': ORDER[4]}


def prioritize(patients):
    consolidated = {}
    for patient in patients:
        pid = patient['id']
        signals = {RISK_SIGNALS.get(patient['risco']),
                   CONTINUITY_SIGNALS.get(patient['continuidade']['classification'])} - {None}
        if not signals:
            continue
        if pid in consolidated:
            signals.update(consolidated[pid]['sinais'])
        ordered = [signal for signal in ORDER if signal in signals]
        consolidated[pid] = {**patient, 'sinais': ordered, 'motivo_principal': ordered[0]}
    return sorted(consolidated.values(), key=lambda p: (
        ORDER.index(p['motivo_principal']), p['nome'].casefold(), p['id']))
