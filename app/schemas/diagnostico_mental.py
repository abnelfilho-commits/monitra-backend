from typing import Optional

from datetime import datetime
from pydantic import ConfigDict, BaseModel, field_validator
from app.schemas.diagnostico import DiagnosticoBase


class DiagnosticoMentalCreate(DiagnosticoBase):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("descricao_clinica", "medico_nome")
    @classmethod
    def nonblank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Informe ao menos três caracteres.")
        return value


class DiagnosticoMentalOut(DiagnosticoBase):
    id: int
    pessoa_id: int
    contexto_assistencial_id: int
    modulo_id: int
    created_at: datetime
    registrador_usuario_id: Optional[int]
    registrador_profissional_id: Optional[int]


class DiagnosticosJornada(BaseModel):
    pode_registrar: bool
    itens: list[DiagnosticoMentalOut]
