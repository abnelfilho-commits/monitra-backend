from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


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
    status: str
    criado_por_usuario_id: int
    criado_em: datetime
    atualizado_em: datetime
