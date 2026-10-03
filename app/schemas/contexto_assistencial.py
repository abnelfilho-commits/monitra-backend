"""Structural commands only: no identity inference or clinical permissions."""
from datetime import date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContextoCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    paciente_instituicao_id: int = Field(gt=0, strict=True)
    data_inicio: date
    data_fim: Optional[date] = None

    @model_validator(mode='after')
    def valid_period(self):
        if self.data_fim is not None and self.data_fim < self.data_inicio:
            raise ValueError('INVALID_PERIOD')
        return self


class ContextoClose(BaseModel):
    model_config = ConfigDict(extra='forbid')
    data_fim: date


class ContextoLinhaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    contexto_assistencial_id: int = Field(gt=0, strict=True)
    modulo_id: int = Field(gt=0, strict=True)
