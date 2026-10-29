from datetime import datetime, time
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class WhatsAppConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    telefone: str = Field(min_length=8, max_length=32)


class WhatsAppState(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    contexto_assistencial_id: int
    paciente_id: int
    telefone: str
    consentimento_status: str
    consentido_em: Optional[datetime]
    revogado_em: Optional[datetime]
    frequencia: str
    proximo_envio_em: Optional[datetime]
    dia_semana: Optional[int] = None
    horario_local: Optional[time] = None
    programacao_ativa: bool = False
    configurado_por_usuario_id: Optional[int] = None
    status: str
    criado_por_usuario_id: int
    criado_em: datetime
    atualizado_em: datetime


class WhatsAppProgramacao(BaseModel):
    model_config = ConfigDict(extra='forbid')
    # Python weekday: Monday=0, Sunday=6. Civil time, never an offset.
    dia_semana: int = Field(ge=0, le=6, strict=True)
    horario_local: time
    programacao_ativa: bool = Field(strict=True)

    @field_validator('horario_local', mode='before')
    @classmethod
    def civil_time(cls, value):
        if not isinstance(value, (str, time)):
            raise ValueError('Use a civil time in HH:MM format')
        return value

    @field_validator('horario_local')
    @classmethod
    def minute_precision(cls, value):
        if value.tzinfo is not None or value.second or value.microsecond:
            raise ValueError('Use a civil time without timezone or seconds')
        return value
