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
