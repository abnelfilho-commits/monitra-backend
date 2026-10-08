"""Lossless presentation of already-authorized persisted assessment applications.

No SQL, instrument engine, narrative, classification or cross-instrument synthesis.
The assistential boundary supplies DTOs returned by each canonical scoped reader.
"""
from copy import deepcopy

INSTRUMENTS = {'phq9': ('PHQ9', 27), 'gad7': ('GAD7', 21), 'cbi': ('CBI', None)}


def assessment_evidence(*, pessoa_id, contexto_assistencial_id, instituicao_id, applications):
    if set(applications) - INSTRUMENTS.keys():
        raise ValueError('Unsupported assessment source.')
    evidence = {}
    for key, (instrument, maximum) in INSTRUMENTS.items():
        history = []
        for application in sorted(applications.get(key, ()), key=lambda a: (a.data_hora, a.id), reverse=True):
            result = application.resultado
            if (result.get('instrumento') != instrument or
                    result.get('metadata', {}).get('contexto_assistencial_id') != contexto_assistencial_id):
                raise ValueError('Assessment differs from contextual source.')
            item = dict(instrument=instrument, application_id=application.id,
                        record_id=application.registro_id, recorded_at=application.data_hora.isoformat(),
                        pessoa_id=pessoa_id, contexto_assistencial_id=contexto_assistencial_id,
                        instituicao_id=instituicao_id, modulo_id=3,
                        author=dict(usuario_id=application.registrador_usuario_id,
                                    profissional_id=application.registrador_profissional_id),
                        result=deepcopy(result))
            # Instrument range is fixed metadata, not recalculated clinical evidence.
            # CBI has only its persisted per-domain ranges; never a global maximum.
            if maximum is not None:
                item['score_max'] = maximum
            history.append(item)
        evidence[key] = dict(applications=history, latest=deepcopy(history[0]) if history else None)
    return evidence
