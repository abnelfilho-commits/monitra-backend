"""Six factual source collectors. No clinical engine, scoring or authorization."""
from datetime import date, datetime, time
from decimal import Decimal
from sqlalchemy import text
from .models import TimelineEvent, SourceType as S, EventType as E, CareLineAssociation as A, TemporalPrecision as P


def rows(db, sql, patient_id):
    return db.execute(text(sql), {'patient_id': patient_id}).mappings().all()


def as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else date.fromisoformat(value)


def as_datetime(value):
    return value if value is None or isinstance(value, datetime) else datetime.fromisoformat(value)


def as_time(value):
    return value if value is None or isinstance(value, time) else time.fromisoformat(value)


def scalar(value):
    return float(value) if isinstance(value, Decimal) else value


def actor(namespace, identity, name=None):
    if identity is None and name is None:
        return None
    return {'namespace': namespace, 'id': identity, 'name': name}


def daily_records(db, patient_id, registry):
    records = rows(db, '''SELECT r.id, r.modulo_id, r.formulario_id, r.data_registro,
        r.criado_em, r.origem, r.criado_por_usuario_id, r.criado_por_responsavel_id
        FROM registros_longitudinais r JOIN formularios_modulo f ON f.id=r.formulario_id
        WHERE r.paciente_id=:patient_id AND f.tipo='REGISTRO_DIARIO' AND f.modulo_id=r.modulo_id''', patient_id)
    answers = rows(db, '''SELECT a.registro_id, c.id AS field_id, c.nome_campo,
        a.valor_texto, a.valor_numero, a.valor_booleano, a.valor_data, a.valor_hora, a.valor_json
        FROM respostas_registro a JOIN registros_longitudinais r ON r.id=a.registro_id
        JOIN formularios_modulo f ON f.id=r.formulario_id
        JOIN campos_formulario c ON c.id=a.campo_id AND c.formulario_id=r.formulario_id
        WHERE r.paciente_id=:patient_id AND f.tipo='REGISTRO_DIARIO' AND f.modulo_id=r.modulo_id''', patient_id)
    grouped = {}
    for answer in answers:
        # Preserve duplicate answer rows as facts; never choose a MAX clinical truth.
        values = {key: scalar(answer[key]) for key in (
            'valor_texto', 'valor_numero', 'valor_booleano', 'valor_data', 'valor_hora', 'valor_json')
            if answer[key] is not None}
        grouped.setdefault(answer['registro_id'], []).append({
            'field_id': answer['field_id'], 'name': answer['nome_campo'], 'values': values})
    result = []
    for r in records:
        actors = [item for item in (actor('usuarios', r['criado_por_usuario_id']),
                                   actor('responsaveis', r['criado_por_responsavel_id'])) if item]
        metadata = {'module_id': r['modulo_id'], 'form_id': r['formulario_id'],
                    'answers': grouped.get(r['id'], [])}
        if len(actors) > 1:
            metadata['source_actors'] = actors
        result.append(TimelineEvent(S.LONGITUDINAL_RECORD, r['id'], patient_id,
            registry.get(r['modulo_id']), A.EXPLICIT, E.DAILY_RECORD, 'Registro diário',
            reference_date=as_date(r['data_registro']), temporal_precision=P.DATE,
            created_at=as_datetime(r['criado_em']), origin=r['origem'],
            actor=actors[0] if len(actors)==1 else None, metadata=metadata))
    return result


def generic_interventions(db, patient_id, registry):
    result = []
    for r in rows(db, '''SELECT id, modulo_id, profissional_id, tipo, descricao, data_intervencao, created_at
                        FROM intervencoes WHERE paciente_id=:patient_id''', patient_id):
        occurrence = as_datetime(r['data_intervencao'])
        result.append(TimelineEvent(S.GENERIC_INTERVENTION, r['id'], patient_id, registry.get(r['modulo_id']),
            A.EXPLICIT, E.INTERVENTION, 'Intervenção',
            reference_date=occurrence.date() if occurrence else None,
            reference_time=occurrence.timetz() if occurrence else None,
            temporal_precision=P.DATETIME if occurrence else None,
            created_at=as_datetime(r['created_at']), summary=r['descricao'],
            actor=actor('usuarios', r['profissional_id']), metadata={'type': r['tipo'], 'module_id': r['modulo_id']}))
    return result


def cardio_interventions(db, patient_id, registry):
    return [TimelineEvent(S.CARDIO_INTERVENTION, r['id'], patient_id, registry.get(r['modulo_id']), A.EXPLICIT,
        E.INTERVENTION, 'Intervenção', created_at=as_datetime(r['created_at']),
        summary=r['descricao'], actor=actor('intervencoes_cardiometabolicas.profissional_id', r['profissional_id']),
        metadata={'source_care_line':'cardiometabolico', 'type':r['tipo'], 'priority':r['prioridade']})
        for r in rows(db, '''SELECT id, modulo_id, profissional_id, tipo, descricao, prioridade, created_at
            FROM intervencoes_cardiometabolicas WHERE paciente_id=:patient_id''', patient_id)]


def assessments(db, patient_id, registry):
    return [TimelineEvent(S.CLINICAL_ASSESSMENT, r['id'], patient_id,
        registry.get(r['modulo_id']), A.EXPLICIT, E.ASSESSMENT, r['instrumento'],
        reference_date=as_date(r['data_registro']), temporal_precision=P.DATE if r['data_registro'] else None,
        created_at=as_datetime(r['created_at']), summary=r['interpretacao'],
        actor=actor('usuarios', r['profissional_id']),
        metadata={'module_id':r['modulo_id'], 'record_id':r['registro_id'],
                  'instrument':r['instrumento'], 'score':scalar(r['score']),
                  'classification':r['classificacao'], 'status':r['status'],
                  'executed_at':as_datetime(r['executado_em'])})
        for r in rows(db, '''SELECT a.id, a.modulo_id, a.registro_id, a.instrumento, a.score,
            a.classificacao, a.interpretacao, a.profissional_id, a.status, a.executado_em,
            a.created_at, r.data_registro FROM avaliacoes_clinicas a
            LEFT JOIN registros_longitudinais r ON r.id=a.registro_id AND r.paciente_id=a.paciente_id
            WHERE a.paciente_id=:patient_id''', patient_id)]


def sessions(db, patient_id, registry):
    result = []
    for r in rows(db, '''SELECT s.id, s.data_realizacao, s.hora_fim_real, s.created_at,
        s.numero_sessao, s.registro_longitudinal_id,
        COALESCE(s.profissional_id,g.profissional_id) AS profissional_id,
        p.modulo_id, p.paciente_id AS pts_patient_id
        FROM sessoes_assistenciais s LEFT JOIN agenda_cuidados g ON g.id=s.agenda_cuidado_id
        LEFT JOIN pts p ON p.id=g.pts_id
        WHERE s.paciente_id=:patient_id AND s.status='REALIZADA' ''', patient_id):
        module = r['modulo_id'] if r['pts_patient_id']==patient_id else None
        day = as_date(r['data_realizacao'])
        clock = as_time(r['hora_fim_real']) if day else None
        result.append(TimelineEvent(S.ASSISTENTIAL_SESSION, r['id'], patient_id,
            registry.get(module) if module is not None else None,
            A.DERIVED if module is not None else A.UNASSIGNED, E.SESSION_COMPLETED, 'Sessão realizada',
            reference_date=day, reference_time=clock,
            temporal_precision=(P.DATETIME if clock else P.DATE) if day else None,
            created_at=as_datetime(r['created_at']), actor=actor('profissionais', r['profissional_id']),
            metadata={'module_id':module, 'session_number':r['numero_sessao'],
                      'record_id':r['registro_longitudinal_id']}))
    return result


def diagnoses(db, patient_id, registry):
    return [TimelineEvent(S.DIAGNOSIS, r['id'], patient_id, registry.get(r['modulo_id']), A.EXPLICIT,
        E.DIAGNOSIS, 'Diagnóstico', reference_date=as_date(r['data_diagnostico']),
        temporal_precision=P.DATE, created_at=as_datetime(r['created_at']),
        summary=r['descricao_clinica'], actor=actor('authored_physician', None, r['medico_nome']),
        metadata={'cid':r['cid'], 'status':r['status']})
        for r in rows(db, '''SELECT id, modulo_id, data_diagnostico, created_at, descricao_clinica,
            medico_nome, cid, status FROM diagnosticos
            WHERE paciente_id=:patient_id AND status <> 'CANCELADO' ''', patient_id)]


SOURCES = (daily_records, generic_interventions, cardio_interventions, assessments, sessions, diagnoses)
