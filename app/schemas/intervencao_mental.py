"""Contextual intervention: authenticated authorship, explicit clinical time."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime


class IntervencaoMentalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    tipo: str = Field(min_length=1, max_length=100)
    descricao: str = Field(min_length=1, max_length=4000)
    data_intervencao: AwareDatetime


class IntervencaoMentalOut(BaseModel):
    id: int
    pessoa_id: int
    contexto_assistencial_id: int
    modulo_id: int
    tipo: str
    descricao: Optional[str]
    data_intervencao: datetime
    created_at: datetime
    registrador_usuario_id: Optional[int]
    registrador_profissional_id: Optional[int]
    registrador_nome: Optional[str]


class IntervencoesJornada(BaseModel):
    pode_registrar: bool
    total: int
    itens: list[IntervencaoMentalOut]
