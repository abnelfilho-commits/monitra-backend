from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanningPeriod(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    frequencia_semanal: int = Field(ge=1)
    duracao_minutos: int = Field(gt=0, le=1440)
    data_inicio: date
    data_fim: date
    quantidade_sessoes: Optional[int] = Field(default=None, gt=0)

    @model_validator(mode='after')
    def period(self):
        if self.data_fim < self.data_inicio:
            raise ValueError('Data final anterior à inicial.')
        if (self.data_fim-self.data_inicio).days > 3660:
            raise ValueError('Período máximo de planejamento: 3660 dias.')
        return self


class PlanningInput(PlanningPeriod):
    atividade_id: int = Field(gt=0)
    ocupacao_id: int = Field(gt=0)
    profissional_id: int = Field(gt=0)
    observacoes: Optional[str] = None


class PlanningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pts_id: int
    objetivo_id: int
    atividade_id: int
    atividade_nome: str
    ocupacao_id: int
    ocupacao_nome: str
    profissional_id: int
    profissional_nome: str
    frequencia_semanal: int
    duracao_minutos: int
    data_inicio: date
    data_fim: date
    quantidade_sessoes: int
    observacoes: Optional[str]
    status: str
