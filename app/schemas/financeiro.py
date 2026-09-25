"""Strict configuration commands, without financial calculation or access grants."""
from datetime import date
from decimal import Decimal
from typing import Optional, Literal
from pydantic import BaseModel, Field, PositiveInt, StrictBool, model_validator


class Command(BaseModel):
    model_config = {'extra': 'forbid', 'str_strip_whitespace': True}


class ServicoCreate(Command):
    codigo: str = Field(min_length=1, max_length=64)
    descricao: str = Field(min_length=1)
    ocupacao_id: PositiveInt
    duracao_minutos: PositiveInt
    tipo_atendimento: Literal['INDIVIDUAL'] = 'INDIVIDUAL'
    unidade: Literal['SESSAO'] = 'SESSAO'
    ativo: StrictBool = True


class TabelaCreate(Command):
    proprietario_instituicao_id: PositiveInt
    codigo: str = Field(min_length=1, max_length=64)
    nome: str = Field(min_length=1)
    moeda: Literal['BRL'] = 'BRL'


class VersaoCreate(Command):
    tabela_id: PositiveInt
    numero: PositiveInt
    vigente_desde: date


class PrecoCreate(Command):
    versao_id: PositiveInt
    servico_id: PositiveInt
    valor_base: Decimal = Field(ge=0, max_digits=14, decimal_places=2, allow_inf_nan=False)
    codigo_externo: Optional[str] = Field(default=None, min_length=1, max_length=128)


class Periodo(Command):
    inicio: date
    fim: Optional[date] = None

    @model_validator(mode='after')
    def period(self):
        if self.fim is not None and self.fim < self.inicio:
            raise ValueError('INVALID_PERIOD')
        return self


class ContratoCreate(Periodo):
    pagador_instituicao_id: PositiveInt
    codigo: str = Field(min_length=1, max_length=64)
    edicao: PositiveInt
    tabela_preco_id: PositiveInt


class PacienteContratoCreate(Periodo):
    paciente_id: PositiveInt
    contrato_id: PositiveInt
    identificador_beneficiario: Optional[str] = Field(default=None, min_length=1, max_length=128)


class MapeamentoCreate(Command):
    agenda_cuidado_id: PositiveInt
    servico_id: PositiveInt
