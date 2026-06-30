from typing import Optional, List
from pydantic import BaseModel


class OcupacaoProfissionalCreate(BaseModel):
    nome: str


class OcupacaoProfissionalResponse(BaseModel):
    id: int
    nome: str
    ativo: bool

    class Config:
        from_attributes = True


class AtividadeTerapeuticaCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    duracao_minutos: Optional[int] = None
    modulo_id: Optional[int] = None

class AtividadeTerapeuticaResponse(BaseModel):
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