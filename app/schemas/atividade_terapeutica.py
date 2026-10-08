from typing import Optional, List
from pydantic import BaseModel, Field, field_validator


class OcupacaoProfissionalCreate(BaseModel):
    nome: str


class OcupacaoProfissionalResponse(BaseModel):
    id: int
    nome: str
    ativo: bool

    class Config:
        from_attributes = True


class AtividadeLinhas(BaseModel):
    modulo_ids: list[int] = Field(min_length=1)

    @field_validator('modulo_ids')
    @classmethod
    def valid_lines(cls, values):
        if any(v <= 0 for v in values) or len(values) != len(set(values)):
            raise ValueError('Linhas devem ser positivas e não repetidas.')
        return sorted(values)


class AtividadeTerapeuticaCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    duracao_minutos: Optional[int] = None
    modulo_id: Optional[int] = None
    modulo_ids: Optional[list[int]] = None

class AtividadeTerapeuticaResponse(BaseModel):
    modulo_ids: list[int] = Field(default_factory=list)
    id: int
    nome: str
    descricao: Optional[str] = None
    duracao_minutos: Optional[int] = None
    modulo_id: Optional[int] = None
    ativo: bool

    class Config:
        from_attributes = True

class AtividadeOcupacaoCreate(BaseModel):
    ocupacao_id: int