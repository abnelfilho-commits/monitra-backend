from pydantic import BaseModel, EmailStr
from typing import Optional, List


class ProfissionalBase(BaseModel):
    nome: str
    email: Optional[EmailStr] = None
    especialidade: Optional[str] = None
    clinica_id: int


class ProfissionalCreate(ProfissionalBase):
    senha: str
    modulo_ids: List[int]


class ProfissionalUpdate(BaseModel):
    nome: str
    email: Optional[EmailStr] = None
    especialidade: Optional[str] = None
    clinica_id: int
    ativo: Optional[bool] = True
    modulo_ids: List[int]


class ProfissionalOut(ProfissionalBase):
    id: int
    ativo: bool
    clinica_nome: Optional[str] = None

    modulo_ids: List[int] = []

    usuario_id: Optional[int] = None
    usuario_ativo: Optional[bool] = None

    class Config:
        from_attributes = True