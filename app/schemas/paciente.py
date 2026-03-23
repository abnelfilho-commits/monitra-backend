from pydantic import BaseModel
from datetime import date
from typing import Optional


class PacienteBase(BaseModel):
    nome: str
    data_nascimento: date
    genero: Optional[str] = None
    responsavel_nome: Optional[str] = None
    responsavel_email: Optional[str] = None


class PacienteCreate(PacienteBase):
    clinica_id: Optional[int] = None
    profissional_id: Optional[int] = None


class PacienteUpdate(PacienteBase):
    clinica_id: Optional[int] = None
    profissional_id: Optional[int] = None


class PacienteResponse(PacienteBase):
    id: int
    clinica_id: Optional[int] = None
    profissional_id: Optional[int] = None
    idade: Optional[int] = None
    profissional_nome: Optional[str] = None
    clinica_nome: Optional[str] = None

    class Config:
        from_attributes = True
