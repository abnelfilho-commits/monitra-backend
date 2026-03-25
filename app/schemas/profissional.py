from pydantic import BaseModel
from typing import Optional


class ProfissionalBase(BaseModel):
    nome: str
    email: Optional[str] = None
    especialidade: Optional[str] = None
    clinica_id: int


class ProfissionalCreate(ProfissionalBase):
    pass


class ProfissionalUpdate(BaseModel):
    nome: str
    email: Optional[str] = None
    especialidade: Optional[str] = None
    clinica_id: int
    ativo: Optional[bool] = True


class ProfissionalOut(ProfissionalBase):
    id: int
    ativo: bool
    clinica_nome: Optional[str] = None

    class Config:
        from_attributes = True
