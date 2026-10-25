from typing import Literal
from datetime import timezone
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, StrictBool, field_validator

class AuthorizationCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    origem: Literal['PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO']
    obtida_em: AwareDatetime
    # Opaque locator in the institution's evidence repository; never content or URL credentials.
    referencia_evidencia: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9._:-]{7,199}$')
    evidencia_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    evidencia_verificada: StrictBool

    @field_validator('obtida_em')
    @classmethod
    def utc(cls, value):
        return value.astimezone(timezone.utc)

    @field_validator('evidencia_verificada')
    @classmethod
    def verified(cls, value):
        if value is not True: raise ValueError('Evidence verification required')
        return value

class AuthorizationRevoke(BaseModel):
    model_config = ConfigDict(extra='forbid')
    motivo: Literal['SOLICITACAO_TITULAR','ERRO_REGISTRO']
