from datetime import date, time
from typing import Optional, Literal
from pydantic import BaseModel, ConfigDict, Field
from app.schemas.sessao_assistencial import SessaoAssistencialResponse


class AtendimentoMental(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    narrativa: str = Field(min_length=1, max_length=20000)
    proximos_passos: list[str] = Field(default_factory=list, max_length=100)


class AcaoSessaoMental(BaseModel):
    model_config = ConfigDict(extra='forbid')
    acao: Literal['confirmar', 'iniciar', 'finalizar']


class SessaoMentalOut(SessaoAssistencialResponse):
    narrativa: Optional[str] = None
    proximos_passos: list[str] = Field(default_factory=list)
    autor_usuario_id: Optional[int] = None


class OcorrenciaMental(BaseModel):
    numero: int
    data: date
    hora_inicio: Optional[time] = None
    hora_fim: Optional[time] = None
    duracao_minutos: int


class CronogramaMentalOut(BaseModel):
    pessoa_id: int
    instituicao_id: int
    contexto_assistencial_id: int
    modulo_id: int = 3
    pts_id: int
    objetivo_id: int
    planejamento_id: int
    atividade: str
    ocupacao: str
    profissional: str
    quantidade_planejada: int
    quantidade_materializada: int
    pode_registrar: bool
    proposta: list[OcorrenciaMental]
    sessoes: list[SessaoMentalOut]
