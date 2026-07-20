from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


TipoDiagnostico = Literal[
    "HIPOTESE",
    "DIAGNOSTICO",
    "REVISAO",
]

StatusDiagnostico = Literal[
    "ATIVO",
    "REVISADO",
    "CANCELADO",
]


class DiagnosticoBase(BaseModel):
    tipo: TipoDiagnostico = "DIAGNOSTICO"
    status: StatusDiagnostico = "ATIVO"

    cid: Optional[str] = Field(
        default=None,
        max_length=20,
    )

    descricao_clinica: str = Field(
        min_length=3,
    )

    data_diagnostico: date

    medico_nome: str = Field(
        min_length=3,
        max_length=200,
    )

    medico_especialidade: Optional[str] = Field(
        default=None,
        max_length=150,
    )

    medico_crm: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    medico_cpf: Optional[str] = Field(
        default=None,
        max_length=20,
    )

    observacoes: Optional[str] = None


class DiagnosticoCreate(DiagnosticoBase):
    paciente_id: int = Field(
        gt=0,
    )


class DiagnosticoUpdate(BaseModel):
    tipo: Optional[TipoDiagnostico] = None
    status: Optional[StatusDiagnostico] = None

    cid: Optional[str] = Field(
        default=None,
        max_length=20,
    )

    descricao_clinica: Optional[str] = Field(
        default=None,
        min_length=3,
    )

    data_diagnostico: Optional[date] = None

    medico_nome: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=200,
    )

    medico_especialidade: Optional[str] = Field(
        default=None,
        max_length=150,
    )

    medico_crm: Optional[str] = Field(
        default=None,
        max_length=50,
    )

    medico_cpf: Optional[str] = Field(
        default=None,
        max_length=20,
    )

    observacoes: Optional[str] = None


class DiagnosticoResponse(DiagnosticoBase):
    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    paciente_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None