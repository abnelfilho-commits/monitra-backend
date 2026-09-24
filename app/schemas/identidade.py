"""Separate human roles from legacy digital accounts. No access payloads."""
from typing import Literal, Optional, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator
from app.schemas.pessoa import PessoaCreate, normalize_cpf


class CpfConsulta(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cpf: StrictStr

    @field_validator("cpf")
    @classmethod
    def cpf_valido(cls, value):
        value = normalize_cpf(value)
        if value is None:
            raise ValueError("CPF obrigatório")
        return value


class IdentidadeComando(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chave_idempotencia: UUID
    pessoa: PessoaCreate
    motivo: str = Field(min_length=1, max_length=1000)

    @field_validator("motivo")
    @classmethod
    def motivo_valido(cls, value):
        if not value.strip():
            raise ValueError("Motivo obrigatório")
        return value.strip()


class AdicionarPapel(IdentidadeComando):
    papel: Literal["PACIENTE", "PROFISSIONAL", "RESPONSAVEL"]
    especialidade: Optional[str] = Field(default=None, max_length=200)
    ocupacao_id: Optional[int] = Field(default=None, gt=0)
    contexto_clinica_id: Optional[int] = Field(default=None, gt=0)


class AssociacaoBase(IdentidadeComando):
    registro_id: int = Field(gt=0)
    tipo_evidencia: str = Field(min_length=1, max_length=100)
    referencia_evidencia: str = Field(min_length=1, max_length=500)
    contexto_clinica_id: Optional[int] = Field(default=None, gt=0)
    divergencias_confirmadas: List[Literal["nome", "data_nascimento"]] = Field(default_factory=list)

    @field_validator("tipo_evidencia", "referencia_evidencia")
    @classmethod
    def evidencia_valida(cls, value):
        if not value.strip():
            raise ValueError("Evidência obrigatória")
        return value.strip()


class AssociarPapelLegado(AssociacaoBase):
    papel: Literal["PACIENTE", "PROFISSIONAL", "RESPONSAVEL"]


class AssociarContaLegada(AssociacaoBase):
    """Only association of an existing Usuario; no account provisioning."""
