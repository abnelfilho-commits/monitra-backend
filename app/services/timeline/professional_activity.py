"""Neuro's existing recent-activity presentation over institutional collectors.

Bounded candidates, creation-time policy, newest event per patient. Clinical dates
remain separately exposed; creation timestamps are not relabeled clinical dates.
"""
from datetime import datetime, time, timezone
from functools import partial
from . import sources
from .models import SourceType as S

COLLECTORS = (partial(sources.daily_records, recent_activity=True),
              partial(sources.generic_interventions, recent_activity=True),
              sources.assessments, partial(sources.sessions, recent_activity=True), partial(sources.diagnoses, recent_activity=True))
TYPES = {S.LONGITUDINAL_RECORD:'REGISTRO_DIARIO', S.GENERIC_INTERVENTION:'INTERVENCAO',
         S.CLINICAL_ASSESSMENT:'AVALIACAO_CLINICA', S.ASSISTENTIAL_SESSION:'SESSAO_REALIZADA', S.DIAGNOSIS:'DIAGNOSTICO'}


def recent_neuro_activity(db, patients, line, registry, limit=5):
    names = {p.id:p.nome for p in patients}
    if not names:
        return []
    events = []
    for collect in COLLECTORS:
        events.extend(collect(db, list(names), registry, module_id=line.module_id, limit=max(limit*3,15)))
    candidates = []
    for event in events:
        if event.care_line is None or event.care_line.module_id != line.module_id:
            continue
        kind = event.source_type
        day = event.reference_date
        stamp = event.created_at if kind in (S.LONGITUDINAL_RECORD,S.GENERIC_INTERVENTION,S.CLINICAL_ASSESSMENT) else None
        if kind == S.ASSISTENTIAL_SESSION:
            day = day or event.metadata.get('scheduled_date')
        if stamp is None and day is not None:
            clock = event.reference_time or (event.metadata.get('completion_time') if kind == S.ASSISTENTIAL_SESSION else None)
            stamp = datetime.combine(day, clock or time.min)
        if stamp is None:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        description = event.summary
        if kind == S.LONGITUDINAL_RECORD:
            observations = [a['values'].get('valor_texto') for a in event.metadata['answers'] if a['name']=='observacao']
            description = max((v for v in observations if v is not None), default=None)
        elif kind == S.DIAGNOSIS:
            description = '{} {}'.format(event.metadata.get('cid') or '', event.summary or '').strip()
        elif kind == S.CLINICAL_ASSESSMENT:
            m = event.metadata
            description = 'Aplicação do {}. Score {}. Classificação: {}.'.format(m['instrument'],m['score'],m['classification'])
        elif kind == S.ASSISTENTIAL_SESSION:
            description = 'Sessão {} de {} realizada.'.format(event.metadata['session_number'],event.metadata['activity_name'])
        candidates.append({'id':event.source_id, 'source_type':kind.value, 'care_line':line.code,
            'paciente_id':event.patient_id,'paciente_nome':names[event.patient_id],
            'tipo':TYPES[kind],'tipo_evento':TYPES[kind],'data':stamp.astimezone(timezone.utc).isoformat(),
            'reference_date':event.reference_date,'created_at':event.created_at,
            'descricao':description,'origem':event.origin or {S.CLINICAL_ASSESSMENT:'FRAMEWORK',S.ASSISTENTIAL_SESSION:'ASSISTENCIAL',S.DIAGNOSIS:'ASSISTENCIAL'}.get(kind,'PROFISSIONAL')})
    candidates.sort(key=lambda e:e['data'],reverse=True)
    seen=set(); result=[]
    for event in candidates:
        if event['paciente_id'] not in seen:
            seen.add(event['paciente_id']); result.append(event)
        if len(result)==limit:
            break
    return result
