from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, EmailStr


class ResponsavelBase(BaseModel):
    nome: str
    email: EmailStr
    telefone: Optional[str] = None


class ResponsavelCreate(ResponsavelBase):
    senha: str


class ResponsavelOut(ResponsavelBase):
    id: int
    ativo: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ResponsavelLogin(BaseModel):
    username: EmailStr
    password: str


class ResponsavelPacienteVinculoCreate(BaseModel):
    responsavel_id: int
    paciente_id: int
    parentesco: Optional[str] = None
    principal: bool = False


class ResponsavelPacienteResumo(BaseModel):
    id: int
    nome: str
    data_nascimento: Optional[date] = None
    idade: Optional[int] = None
    profissional_nome: Optional[str] = None
    clinica_nome: Optional[str] = None

    class Config:
        from_attributes = True


class ResponsavelMeOut(BaseModel):
    id: int
    nome: str
    email: EmailStr
    telefone: Optional[str] = None
    ativo: bool

    class Config:
        from_attributes = True
