"""Aggregate-only institutional operations; no individual records in the contract."""
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class OperationalModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class IndicadoresGestaoMental(OperationalModel):
    instituicoes_ativas: int = Field(ge=0)
    profissionais_vinculados: int = Field(ge=0)
    atendimentos_programados: int = Field(ge=0)
    atendimentos_realizados: int = Field(ge=0)


class AtendimentosSemanais(OperationalModel):
    semana: date
    programados: int = Field(ge=0)
    realizados: int = Field(ge=0)


class EvolucaoAtendimentos(OperationalModel):
    semana: date
    realizados: int = Field(ge=0)


class MetadadosGestaoMental(OperationalModel):
    data_inicio: date
    data_fim: date
    data_consulta: date
    semanas: Literal[4, 8, 12]
    fuso: Literal['America/Cuiaba'] = 'America/Cuiaba'
    instituicao_ids: list[int]
    escopo: Literal['GLOBAL', 'INSTITUICOES_AUTORIZADAS']
    limitacoes: list[str]


class CockpitGestaoMentalOut(OperationalModel):
    indicadores: IndicadoresGestaoMental
    atendimentos_programados_realizados: list[AtendimentosSemanais]
    evolucao_atendimentos: list[EvolucaoAtendimentos]
    metadados: MetadadosGestaoMental
