from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


class IntervencaoCreate(BaseModel):
    paciente_id: int
    profissional_id: int
    tipo: str
    descricao: Optional[str] = None
    data_intervencao: datetime


class RegistroDiarioCreate(BaseModel):
    paciente_id: int
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None
    observacao: Optional[str] = None
    alimentacao: Optional[str] = None


class RegistroDiarioOut(BaseModel):
    id: int
    paciente_id: int
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None
    observacao: Optional[str] = None
    alimentacao: Optional[str] = None

    class Config:
        from_attributes = True


class RegistroDiarioResponsavelCreate(BaseModel):
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None
    alimentacao: Optional[str] = None
    observacao: Optional[str] = None


class RegistroDiarioResponsavelOut(BaseModel):
    id: int
    paciente_id: int
    data: date
    sono_qualidade: Optional[int] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[int] = None
    irritabilidade: Optional[int] = None
    crise_sensorial: Optional[int] = None
    alimentacao: Optional[str] = None
    observacao: Optional[str] = None
    origem: Optional[str] = None
    responsavel_id: Optional[int] = None
    criado_por_tipo: Optional[str] = None
    criado_por_id: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True
