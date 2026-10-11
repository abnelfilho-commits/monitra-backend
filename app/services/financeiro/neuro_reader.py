"""Read persisted eligible care sessions only. No scheduling, money or clinical writes."""

from sqlalchemy import or_, select
from app.models.agenda_cuidado import AgendaCuidado as Agenda
from app.models.pts import PTS, PTSObjetivo
from app.models.paciente import Paciente
from app.models.sessao_assistencial import SessaoAssistencial as Sessao
from app.services.care_lines.registry import NEURO, MENTAL_HEALTH
from app.models.contexto_assistencial import ContextoAssistencial, ContextoAssistencialLinha


from app.services.financeiro.contracts import PlannedSession, NeuroPlan


def read_neuro(db, request):
    return read_neuro_batch(db, (request.paciente_id,), request)[request.paciente_id]


def read_neuro_batch(db, patient_ids, request):
    # Preserve the legacy Neuro boundary, including the objective's ancestry.
    return _read_batch(db, patient_ids, request, (
        PTS.contexto_assistencial_id.is_(None),
        ~PTSObjetivo.pts.has(PTS.contexto_assistencial_id.is_not(None)),
        PTS.modulo_id == NEURO.module_id,
    ))


def read_mental_health_batch(db, patient_ids, request):
    # EXISTS avoids multiplying sessions; foreign contexts and inactive lines
    # produce neither financial items nor gaps. No legacy institution inference.
    eligible_context = select(ContextoAssistencial.id).join(
        ContextoAssistencialLinha,
        ContextoAssistencialLinha.contexto_assistencial_id == ContextoAssistencial.id,
    ).where(
        ContextoAssistencial.id == PTS.contexto_assistencial_id,
        ContextoAssistencial.paciente_id == PTS.paciente_id,
        ContextoAssistencial.instituicao_id == request.instituicao_id,
        ContextoAssistencialLinha.modulo_id == MENTAL_HEALTH.module_id,
        ContextoAssistencialLinha.ativo.is_(True),
    ).exists()
    return _read_batch(db, patient_ids, request, (
        PTS.modulo_id == MENTAL_HEALTH.module_id,
        PTS.contexto_assistencial_id.is_not(None), eligible_context,
    ))


def _read_batch(db, patient_ids, request, eligibility):
    patient_ids = tuple(sorted(set(patient_ids)))
    if not patient_ids:
        return {}

    found = set(db.scalars(select(Paciente.id).where(Paciente.id.in_(patient_ids))))
    if found != set(patient_ids):
        raise ValueError('Paciente inexistente')
    # Select scalars, not cached ORM entities. The caller supplies a consistent snapshot.
    statement = (
        select(Sessao.id, Sessao.paciente_id, Sessao.profissional_id,
               Sessao.data_agendada, Sessao.duracao_minutos,
               Agenda.id.label('agenda_id'), Agenda.pts_id, Agenda.objetivo_id,
               Agenda.atividade_id, Agenda.ocupacao_id,
               Agenda.duracao_minutos.label('duracao_agenda'),
               PTS.paciente_id.label('pts_paciente_id'), PTSObjetivo.pts_id.label('objetivo_pts_id'))
        .join(Agenda, Sessao.agenda_cuidado_id == Agenda.id)
        .join(PTS, Agenda.pts_id == PTS.id)
        .outerjoin(PTSObjetivo, Agenda.objetivo_id == PTSObjetivo.id)
        .where(*eligibility,
               or_(PTS.paciente_id.in_(patient_ids), Sessao.paciente_id.in_(patient_ids)),
               Sessao.status.in_(('AGENDADA', 'CONFIRMADA')),
               Sessao.data_agendada.between(request.data_inicio, request.data_fim))
        .order_by(Sessao.data_agendada, Sessao.id)
    )
    sessions = {pid: [] for pid in patient_ids}
    for row in db.execute(statement).mappings():
        if (row['paciente_id'] != row['pts_paciente_id'] or row['paciente_id'] not in sessions
                or row['objetivo_pts_id'] != row['pts_id']):
            raise ValueError('Ancestralidade assistencial inconsistente; preview recusado')
        sessions[row['paciente_id']].append(PlannedSession(
            sessao_id=row['id'], agenda_id=row['agenda_id'], pts_id=row['pts_id'],
            objetivo_id=row['objetivo_id'], atividade_id=row['atividade_id'],
            ocupacao_id=row['ocupacao_id'], profissional_id=row['profissional_id'],
            data_economica=row['data_agendada'], duracao_minutos=row['duracao_minutos'],
            duracao_agenda=row['duracao_agenda']))
    # Gap evidence is bounded by agenda dates. It never generates financial quantity.
    agendas = db.execute(
        select(Agenda.id, Agenda.pts_id, PTS.paciente_id, PTSObjetivo.pts_id.label('objetivo_pts_id'))
        .join(PTS, Agenda.pts_id == PTS.id)
        .outerjoin(PTSObjetivo, Agenda.objetivo_id == PTSObjetivo.id)
        .where(*eligibility, PTS.paciente_id.in_(patient_ids),
               Agenda.data_inicio <= request.data_fim,
               or_(Agenda.data_fim.is_(None), Agenda.data_fim >= request.data_inicio))
        .order_by(Agenda.id)).all()
    if any(row.pts_id != row.objetivo_pts_id for row in agendas):
        raise ValueError('Ancestralidade assistencial inconsistente; preview recusado')
    considered = {s.agenda_id for values in sessions.values() for s in values}
    gaps = {pid: [] for pid in patient_ids}
    for row in agendas:
        if row.id not in considered:
            gaps[row.paciente_id].append(row.id)
    return {pid: NeuroPlan(tuple(sessions[pid]), tuple(gaps[pid])) for pid in patient_ids}
