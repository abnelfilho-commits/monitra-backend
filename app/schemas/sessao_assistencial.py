from datetime import date, datetime, time
from typing import Optional

from pydantic import BaseModel, Field


STATUS_SESSAO_VALIDOS = {
    "AGENDADA",
    "CONFIRMADA",
    "REALIZADA",
    "FALTOU",
    "REAGENDADA",
    "CANCELADA",
}


class SessaoAssistencialBase(BaseModel):
    profissional_id: Optional[int] = None

    data_agendada: date

    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None

    duracao_minutos: int = Field(
        ...,
        gt=0,
        description="Duração prevista da sessão em minutos.",
    )

    observacoes: Optional[str] = None


class SessaoAssistencialCreate(
    SessaoAssistencialBase
):
    agenda_cuidado_id: int
    paciente_id: int
    numero_sessao: int = Field(..., gt=0)


class SessaoAssistencialUpdate(BaseModel):
    profissional_id: Optional[int] = None

    data_agendada: Optional[date] = None

    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None

    duracao_minutos: Optional[int] = Field(
        default=None,
        gt=0,
    )

    observacoes: Optional[str] = None


class SessaoAssistencialStatusUpdate(BaseModel):
    status: str

    data_realizacao: Optional[date] = None

    hora_inicio_real: Optional[time] = None
    hora_fim_real: Optional[time] = None

    observacoes: Optional[str] = None

    motivo_falta: Optional[str] = None
    motivo_cancelamento: Optional[str] = None
    motivo_reagendamento: Optional[str] = None


class SessaoAssistencialResponse(BaseModel):
    id: int

    agenda_cuidado_id: int
    paciente_id: int
    profissional_id: Optional[int]

    numero_sessao: int

    data_agendada: date

    hora_inicio: Optional[time]
    hora_fim: Optional[time]

    duracao_minutos: int

    status: str

    data_realizacao: Optional[date]

    hora_inicio_real: Optional[time]
    hora_fim_real: Optional[time]

    observacoes: Optional[str]

    motivo_falta: Optional[str]
    motivo_cancelamento: Optional[str]
    motivo_reagendamento: Optional[str]

    sessao_origem_id: Optional[int]
    registro_longitudinal_id: Optional[int]

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True