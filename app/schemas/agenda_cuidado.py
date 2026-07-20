from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class AgendaCuidadoCreate(BaseModel):
    pts_id: int
    objetivo_id: int

    atividade_id: int
    ocupacao_id: int

    frequencia_semanal: int
    duracao_minutos: int

    data_inicio: date
    data_fim: Optional[date] = None

    observacoes: Optional[str] = None

    profissional_id: Optional[int] = None
    quantidade_sessoes: Optional[int] = None

class AgendaCuidadoUpdate(BaseModel):
    frequencia_semanal: Optional[int] = None
    duracao_minutos: Optional[int] = None

    data_inicio: Optional[date] = None
    data_fim: Optional[date] = None

    status: Optional[str] = None

    observacoes: Optional[str] = None

    status_execucao: Optional[str] = None
    data_realizacao: Optional[date] = None
    observacao_execucao: Optional[str] = None

    profissional_id: Optional[int] = None
    quantidade_sessoes: Optional[int] = None

class AgendaCuidadoResponse(BaseModel):
    id: int

    pts_id: int
    objetivo_id: int

    atividade_id: int
    ocupacao_id: int

    atividade_nome: Optional[str] = None
    ocupacao_nome: Optional[str] = None

    frequencia_semanal: int
    duracao_minutos: int

    data_inicio: date
    data_fim: Optional[date]

    status: str
    
    status_execucao: Optional[str] = None

    data_realizacao: Optional[date] = None

    observacao_execucao: Optional[str] = None

    observacoes: Optional[str]

    profissional_id: Optional[int] = None
    profissional_nome: Optional[str] = None

    quantidade_sessoes: Optional[int] = None

    created_at: datetime

    class Config:
        from_attributes = True
        
class AgendaFrequenciaUpdate(BaseModel):
    status_execucao: str
    data_realizacao: Optional[date] = None
    observacao_execucao: Optional[str] = None