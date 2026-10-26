"""Read projections: communication evidence is never a clinical measurement."""
from typing import Literal, Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AutoriaComunicacao(BaseModel):
    tipo: Literal['PESSOA','PROFISSIONAL']
    pessoa_id: Optional[int] = None
    usuario_id: Optional[int] = None


class EventoComunicacao(BaseModel):
    id: int
    tipo: Literal['COMUNICACAO_WHATSAPP_INTERROMPIDA','COMUNICACAO_WHATSAPP_REATIVADA']
    acompanhamento_id: int
    pessoa_id: int
    contexto_assistencial_id: int
    instituicao_id: int
    ocorrido_em: datetime
    origem: Literal['WHATSAPP','PROFISSIONAL']
    autoria: AutoriaComunicacao
    referencia_auditoria: str


class EstadoComunicacao(BaseModel):
    estado: Literal['AUSENTE','WHATSAPP_INTERROMPIDO','SEM_INTERRUPCAO_REGISTRADA']
    acompanhamento_id: Optional[int]
    interrompido_pela_pessoa: bool = False
    ocorrido_em: Optional[datetime] = None
    bloqueio_preventivo: bool = False
    acompanhamento_assistencial_independente: bool = True
    eventos: list[EventoComunicacao] = Field(default_factory=list)
