from datetime import date, datetime
from typing import Optional, List

from pydantic import BaseModel


class PTSObjetivoCreate(BaseModel):
    descricao: str
    prioridade: Optional[str] = None


class PTSObjetivoResponse(BaseModel):
    id: int
    descricao: str
    prioridade: Optional[str]
    status: str

    class Config:
        from_attributes = True


class PTSCreate(BaseModel):
    paciente_id: int
    modulo_id: Optional[int] = None
    data_inicio: date
    objetivo_geral: Optional[str] = None
    observacoes: Optional[str] = None


class PTSUpdate(BaseModel):
    status: Optional[str] = None
    data_fim: Optional[date] = None
    objetivo_geral: Optional[str] = None
    observacoes: Optional[str] = None


class PTSResponse(BaseModel):
    id: int
    paciente_id: int
    modulo_id: Optional[int]
    data_inicio: date
    data_fim: Optional[date]
    status: str
    objetivo_geral: Optional[str]
    observacoes: Optional[str]
    created_at: datetime

    objetivos: List[PTSObjetivoResponse] = []

    class Config:
        from_attributes = True


class PTSObjetivoUpdate(BaseModel):
    descricao: Optional[str] = None
    prioridade: Optional[str] = None
    status: Optional[str] = None