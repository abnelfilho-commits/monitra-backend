from datetime import date, time
from typing import List, Optional

from pydantic import BaseModel, Field


class SessaoPropostaResponse(BaseModel):
    numero: int
    data: date
    duracao: int


class CronogramaPropostoResponse(BaseModel):
    agenda_id: int
    atividade: str
    profissional: Optional[str] = None
    cronograma: List[SessaoPropostaResponse]


class SessaoCronogramaConfirmacao(BaseModel):
    numero: int = Field(..., gt=0)
    data: date

    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None


class ConfirmarCronogramaRequest(BaseModel):
    cronograma: List[SessaoCronogramaConfirmacao]


class ConfirmarCronogramaResponse(BaseModel):
    mensagem: str
    total: int
    agenda_id: int