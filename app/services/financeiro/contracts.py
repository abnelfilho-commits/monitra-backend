"""Immutable assistential inputs; no economic or authorization inference."""
from dataclasses import dataclass
from datetime import date
from typing import Optional

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
