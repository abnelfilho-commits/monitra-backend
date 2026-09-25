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


# Gate B: in-memory contracts only; no persistence or access grant.
class PreviewRequest(Command):
    paciente_id: PositiveInt
    contrato_id: PositiveInt
    instituicao_id: PositiveInt
    data_inicio: date
    data_fim: date

    @model_validator(mode='after')
    def horizon(self):
        if self.data_fim < self.data_inicio:
            raise ValueError('data_fim must be >= data_inicio')
        return self


PendingCode = Literal[
    'NO_CONTRACT', 'NO_ECONOMIC_SERVICE_MAPPING',
    'INCOMPATIBLE_ECONOMIC_SERVICE_MAPPING',
    'NO_APPLICABLE_PRICE_TABLE_VERSION', 'NO_PRICE',
]


class PreviewValue(BaseModel):
    model_config = {'extra': 'forbid', 'frozen': True}


class PreviewItem(PreviewValue):
    sessao_id: int
    agenda_id: int
    pts_id: int
    objetivo_id: int
    atividade_id: int
    ocupacao_id: int
    profissional_id: Optional[int]
    data_economica: date
    quantidade: Literal[1] = 1
    duracao_minutos: int
    mapeamento_id: Optional[int] = None
    servico_id: Optional[int] = None
    servico_codigo: Optional[str] = None
    tabela_id: Optional[int] = None
    versao_id: Optional[int] = None
    versao_numero: Optional[int] = None
    vigente_desde: Optional[date] = None
    preco_id: Optional[int] = None
    codigo_externo: Optional[str] = None
    moeda: Literal['BRL'] = 'BRL'
    estado: Literal['CALCULADO', 'PENDENTE']
    pendencia: Optional[PendingCode] = None
    preco_unitario: Optional[Decimal] = None
    subtotal: Optional[Decimal] = None

    @model_validator(mode='after')
    def monetary_state(self):
        if self.estado == 'PENDENTE':
            if self.pendencia is None or self.preco_unitario is not None or self.subtotal is not None:
                raise ValueError('Pending items require a reason and null monetary values')
        elif (self.pendencia is not None or self.preco_unitario is None or self.subtotal is None
              or any(x is None for x in (self.servico_id, self.tabela_id, self.versao_id, self.preco_id))):
            raise ValueError('Calculated items require complete economic provenance')
        return self


class PreviewTotal(PreviewValue):
    quantidade_considerada: int
    quantidade_precificada: int
    quantidade_pendente: int
    subtotal_precificado: Optional[Decimal]


class ServiceTotal(PreviewTotal):
    servico_id: int


class MonthTotal(PreviewTotal):
    mes: str


class PreviewCoverage(PreviewValue):
    sessoes_elegiveis: int
    sessoes_mapeadas: int
    sessoes_precificadas: int
    sessoes_pendentes: int
    agendas_sem_sessoes_elegiveis: tuple[int, ...]
    aplicabilidade: Literal['APLICAVEL', 'N/A']


class PreviewPending(PreviewValue):
    sessao_id: int
    codigo: PendingCode


class PreviewResponse(PreviewValue):
    paciente_id: int
    contrato_id: int
    instituicao_id: int
    data_inicio: date
    data_fim: date
    moeda: Literal['BRL'] = 'BRL'
    itens: tuple[PreviewItem, ...]
    totais_por_servico: tuple[ServiceTotal, ...]
    totais_por_mes: tuple[MonthTotal, ...]
    subtotal_precificado: Optional[Decimal]
    cobertura: PreviewCoverage
    pendencias: tuple[PreviewPending, ...]
