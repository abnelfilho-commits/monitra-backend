"""Minimal contextual read models; no clinical event or onboarding payload."""
from datetime import date
from typing import Literal, Optional
from pydantic import BaseModel


class InstituicaoDisponivel(BaseModel):
    id: int
    nome: str


class JornadaMental(BaseModel):
    pessoa_id: int
    nome_completo: str
    nome_social: Optional[str]
    paciente_id: int
    instituicao_id: int
    instituicao_nome: str
    paciente_instituicao_id: int
    contexto_assistencial_id: int
    data_inicio: date
    data_fim: Optional[date]
    contexto_estado: Literal['ABERTO', 'ENCERRADO', 'PROGRAMADO']
    modulo_id: int
    linha_estado: Literal['ATIVA', 'INATIVA', 'AUSENTE']


class PessoasMentais(BaseModel):
    itens: list[JornadaMental]
    tem_mais: bool
