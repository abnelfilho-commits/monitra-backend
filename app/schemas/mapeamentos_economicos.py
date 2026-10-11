"""Administrative mapping projections without prices or clinical payloads."""
from datetime import date
from typing import Optional
from pydantic import BaseModel, PositiveInt
from app.schemas.financeiro import Command


class MapeamentoAlterar(Command):
    servico_id: PositiveInt


class AgendaEconomicaResponse(BaseModel):
    agenda_cuidado_id: int
    paciente_id: int
    paciente_nome: str
    atividade_id: int
    atividade_nome: str
    ocupacao_id: int
    ocupacao_nome: str
    duracao_minutos: int
    modulo_id: Optional[int]
    modulo_nome: Optional[str]
    contexto_assistencial_id: Optional[int]
    data_inicio: date
    data_fim: Optional[date]
    status: str
    mapeamento_id: Optional[int]
    servico_id: Optional[int]
    servico_codigo: Optional[str]
    servico_descricao: Optional[str]
    servico_ativo: Optional[bool]
