"""Contextual DTOs over canonical PTS fields; identity comes from authorized ancestry."""
from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.pts import PTSResponse, PTSObjetivoCreate, PTSObjetivoUpdate


class PTSMentalCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    data_inicio: date
    objetivo_geral: str = Field(min_length=1)
    observacoes: Optional[str] = None


class PTSMentalUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    objetivo_geral: str = Field(min_length=1)
    observacoes: Optional[str] = None


class ObjetivoMentalCreate(PTSObjetivoCreate):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    descricao: str = Field(min_length=1)
    prioridade: Optional[str] = Field(default=None, max_length=30)


class ObjetivoMentalUpdate(PTSObjetivoUpdate):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    descricao: Optional[str] = Field(default=None, min_length=1)
    prioridade: Optional[str] = Field(default=None, max_length=30)
    status: Optional[str] = Field(default=None, min_length=1, max_length=30)


class PTSMentalOut(PTSResponse):
    pessoa_id: int
    contexto_assistencial_id: int
    instituicao_id: int
    criado_por_usuario_id: Optional[int]


class PTSMentalJornada(BaseModel):
    pode_registrar: bool
    itens: list[PTSMentalOut]
