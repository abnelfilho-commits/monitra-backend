"""Read persisted Neuro sessions only. No scheduling, money or clinical writes."""
from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import or_, select
from app.models.agenda_cuidado import AgendaCuidado as Agenda
from app.models.pts import PTS, PTSObjetivo
from app.models.paciente import Paciente
from app.models.sessao_assistencial import SessaoAssistencial as Sessao
from app.services.care_lines.registry import NEURO


@dataclass(frozen=True)
class PlannedSession:
    sessao_id: int
    agenda_id: int
    pts_id: int
    objetivo_id: int
    atividade_id: int
    ocupacao_id: int
    profissional_id: Optional[int]
    data_economica: date
    duracao_minutos: int
    duracao_agenda: int


@dataclass(frozen=True)
class NeuroPlan:
    sessions: tuple[PlannedSession, ...]
    agendas_without_sessions: tuple[int, ...]


def read_neuro(db, request):
    if db.scalar(select(Paciente.id).where(Paciente.id == request.paciente_id)) is None:
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
        .where(PTS.modulo_id == NEURO.module_id,
               or_(PTS.paciente_id == request.paciente_id, Sessao.paciente_id == request.paciente_id),
               Sessao.status.in_(('AGENDADA', 'CONFIRMADA')),
               Sessao.data_agendada.between(request.data_inicio, request.data_fim))
        .order_by(Sessao.data_agendada, Sessao.id)
    )
    sessions = []
    for row in db.execute(statement).mappings():
        if (row['paciente_id'] != request.paciente_id or row['pts_paciente_id'] != request.paciente_id
                or row['objetivo_pts_id'] != row['pts_id']):
            raise ValueError('Ancestralidade assistencial inconsistente; preview recusado')
        sessions.append(PlannedSession(
            sessao_id=row['id'], agenda_id=row['agenda_id'], pts_id=row['pts_id'],
            objetivo_id=row['objetivo_id'], atividade_id=row['atividade_id'],
            ocupacao_id=row['ocupacao_id'], profissional_id=row['profissional_id'],
            data_economica=row['data_agendada'], duracao_minutos=row['duracao_minutos'],
            duracao_agenda=row['duracao_agenda']))
    # Gap evidence is bounded by agenda dates. It never generates financial quantity.
    agendas = db.execute(
        select(Agenda.id, Agenda.pts_id, PTSObjetivo.pts_id.label('objetivo_pts_id'))
        .join(PTS, Agenda.pts_id == PTS.id)
        .outerjoin(PTSObjetivo, Agenda.objetivo_id == PTSObjetivo.id)
        .where(PTS.paciente_id == request.paciente_id, PTS.modulo_id == NEURO.module_id,
               Agenda.data_inicio <= request.data_fim,
               or_(Agenda.data_fim.is_(None), Agenda.data_fim >= request.data_inicio))
        .order_by(Agenda.id)).all()
    if any(row.pts_id != row.objetivo_pts_id for row in agendas):
        raise ValueError('Ancestralidade assistencial inconsistente; preview recusado')
    considered = {s.agenda_id for s in sessions}
    return NeuroPlan(tuple(sessions), tuple(row.id for row in agendas if row.id not in considered))
