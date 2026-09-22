"""Cardio journey composition over institutional reading, continuity and Timeline."""
from datetime import date
from app.services.care_lines import CARDIO
from app.services.care_lines.access import authorized_patient
from app.services.clinical_reading import ClinicalReadingService
from app.services.continuity_service import continuity_signal
from app.services.cardio_priority import prioritize
from app.services.cardio_evolution import evolution
from app.services.patient_line_service import list_patients
from app.services.timeline.models import TimelineQuery, TimelineScope
from app.services.timeline_service import TimelineService
from app.services.timeline.sources import daily_records, generic_interventions, cardio_interventions, diagnoses

CARDIO_TIMELINE_SOURCES = (daily_records, generic_interventions, cardio_interventions, diagnoses)


def event_response(event):
    # Explicit presentation, no clinical classification or synthetic clinical date.
    return {'id': event.source_type.value + ':' + str(event.source_id),
            'patient_id': event.patient_id, 'care_line': event.care_line.code,
            'tipo': event.title, 'event_type': event.event_type.value,
            'data': event.reference_date.isoformat() if event.reference_date else None,
            'created_at': event.created_at.isoformat() if event.created_at else None,
            'reference_time': event.reference_time.isoformat() if event.reference_time else None,
            'descricao': event.summary, 'origem': event.origin, 'actor': event.actor,
            'metadata': event.metadata}


def patient_response(patient, reading, observation, today):
    if observation.get('record_id') != reading.metadata.get('record_id'):
        observation = {'imc_availability': 'unavailable_observation_changed'}
    measurements = reading.metadata.get('measurements', {})
    systolic, diastolic = measurements.get('pressao_sistolica'), measurements.get('pressao_diastolica')
    return {'id': patient.id, 'nome': patient.nome, 'care_line': reading.care_line.code,
            'data_nascimento': patient.data_nascimento,
            'risco': reading.risk, 'tendencia': reading.trend, 'leitura_clinica': reading.summary,
            'resumo': reading.summary, 'score_clinico': reading.metadata.get('score'),
            'score': reading.metadata.get('score'), 'protocolo': reading.metadata.get('protocol'),
            'protocolo_label': reading.metadata.get('protocol'),
            'ultima_atualizacao': reading.reference_date,
            'glicemia': measurements.get('glicemia_jejum'),
            'pressao': f'{systolic:g}x{diastolic:g}' if systolic is not None and diastolic is not None else None,
            'peso': measurements.get('peso'), 'altura': observation.get('altura'),
            'imc': observation.get('imc'), 'imc_availability': observation.get('imc_availability', 'no_record'),
            'continuidade': continuity_signal(reading.reference_date, today),
            'clinical_reading': {'patient_id': reading.patient_id, 'care_line': reading.care_line.code,
                'reference_date': reading.reference_date, 'risk': reading.risk, 'trend': reading.trend,
                'summary': reading.summary, 'clinical_state': reading.clinical_state,
                'evidence': reading.evidence, 'alerts': reading.alerts, 'metadata': reading.metadata}}


def patient_detail(db, user, patient_id):
    patient, line = authorized_patient(db, user, patient_id, 'CARDIO')
    reading = ClinicalReadingService().get_reading(db, patient_id, line.code)
    observations = evolution(db, [patient_id], line.module_id, latest_only=True)
    return patient_response(patient, reading, observations[0] if observations else {}, date.today())


def patient_timeline(db, user, patient_id):
    _, line = authorized_patient(db, user, patient_id, 'CARDIO')
    return [event_response(e) for e in TimelineService.get_events(db,
            TimelineQuery(patient_id, scope=TimelineScope.CARE_LINE, requested_care_line=line.code), sources=CARDIO_TIMELINE_SOURCES)]


def population(db, user, today=None):
    patients = list_patients(db, user, 'CARDIO')
    ids = [p.id for p in patients]
    readings = ClinicalReadingService().get_readings(db, ids, 'CARDIO')
    observations = {r['patient_id']: r for r in evolution(db, ids, CARDIO.module_id, latest_only=True)}
    return [patient_response(p, readings[p.id], observations.get(p.id, {}), today or date.today()) for p in patients]


def cockpit(db, user, offset=0, limit=20, today=None):
    patients = population(db, user, today)
    distribution = {key: 0 for key in ('critico', 'alto', 'moderado', 'baixo', 'indisponivel')}
    continuity = {key: 0 for key in ('NAO_INICIADA', 'REGULAR', 'ATENCAO', 'CRITICA')}
    for p in patients:
        distribution[p['risco'] if p['risco'] is not None else 'indisponivel'] += 1
        continuity[p['continuidade']['classification']] += 1
    priorities = prioritize(patients)
    names = {p['id']: p['nome'] for p in patients}
    recent = [{**event_response(e), 'nome': names[e.patient_id]} for e in
              TimelineService.get_recent_events(db, list(names), CARDIO, limit=10, sources=CARDIO_TIMELINE_SOURCES)]
    return {'care_line': CARDIO.code, 'indicadores': {'total_pacientes': len(patients),
            'critico': distribution['critico'], 'alto_risco': distribution['alto'],
            'moderado': distribution['moderado'], 'baixo': distribution['baixo'],
            'indisponivel': distribution['indisponivel']}, 'distribuicao_risco': distribution,
            'continuidade': continuity, 'pacientes_criticos': priorities[offset:offset + limit],
            'pagination': {'offset': offset, 'limit': limit, 'total': len(priorities)},
            'recent_activity': recent,
            'evolution': {'com_registro': sum(p['ultima_atualizacao'] is not None for p in patients),
                          'sem_registro': sum(p['ultima_atualizacao'] is None for p in patients)},
            'capabilities': {k: v.value for k, v in CARDIO.capabilities.items()}}


def risk_map(db, user):
    """Current institutional readings, grouped by authorized clinic; no snapshot reads."""
    patients = list_patients(db, user, CARDIO.code)
    readings = ClinicalReadingService().get_readings(db, [p.id for p in patients], CARDIO.code)
    groups = {}
    for patient in patients:
        reading = readings[patient.id]
        group = groups.setdefault(patient.clinica_id, {
            'clinica': patient.clinica.nome if patient.clinica else 'Clínica não informada',
            'total': 0, 'critico': 0, 'alto': 0, 'moderado': 0, 'baixo': 0,
            'indisponivel': 0, 'scores': [], 'pacientes_criticos': [],
        })
        group['total'] += 1
        group[reading.risk if reading.risk is not None else 'indisponivel'] += 1
        score = reading.metadata.get('score')
        if score is not None:
            group['scores'].append(score)
        group['pacientes_criticos'].append({
            'id': patient.id, 'nome': patient.nome, 'score': score,
            'risco': reading.risk, 'protocolo': reading.metadata.get('protocol'),
        })
    result = []
    for group in groups.values():
        scores = group.pop('scores')
        group['score_medio'] = round(sum(scores) / len(scores), 1) if scores else None
        # Preserve top-three score presentation; absent scores follow available scores.
        group['pacientes_criticos'] = sorted(group['pacientes_criticos'], key=lambda p: (
            p['score'] is None, -(p['score'] if p['score'] is not None else 0), p['nome'], p['id']))[:3]
        result.append(group)
    return sorted(result, key=lambda group: (-group['alto'], group['clinica']))
