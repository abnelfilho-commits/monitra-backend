"""Public management-only contract. No individual identifiers are accepted."""
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


Quality = Literal['CONCLUSIVO', 'ESTIMADO', 'INCOMPLETO', 'INCONSISTENTE']
Reason = Literal['DEMANDA_NAO_CALCULAVEL', 'CAPACIDADE_NAO_CONCLUSIVA', 'CAPACIDADE_ZERO']


class PublicModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class ManagementIssue(PublicModel):
    origem: Literal['DEMANDA', 'CAPACIDADE']
    codigo: str = Field(pattern=r'^[A-Z][A-Z0-9_]*$')
    quantidade: int = Field(gt=0)


class UnavailableReasons(PublicModel):
    demanda_mensal_projetada: List[Reason]
    capacidade_mensal_equivalente: List[Reason]
    saldo_mensal: List[Reason]
    utilizacao_percentual: List[Reason]


class MonthlyIndicators(PublicModel):
    unidade: Literal['MINUTOS_MENSAIS']
    demanda_mensal_projetada: Optional[int] = Field(ge=0)
    demanda_persistida_conhecida: int = Field(ge=0)
    demanda_estimada_conhecida: int = Field(ge=0)
    demanda_subtotal_parcial: bool
    capacidade_mensal_conhecida: str = Field(pattern=r'^\d+\.\d{2}$')
    capacidade_mensal_equivalente: Optional[str] = Field(pattern=r'^\d+\.\d{2}$')
    capacidade_subtotal_parcial: bool
    saldo_mensal: Optional[str] = Field(pattern=r'^-?\d+\.\d{2}$')
    utilizacao_percentual: Optional[str] = Field(pattern=r'^\d+\.\d{2}$')
    motivo_utilizacao_nula: Optional[Reason]
    qualidade: Quality
    qualidade_demanda: Quality
    qualidade_capacidade: Literal['CONCLUSIVO', 'INCOMPLETO', 'INCONSISTENTE']
    conclusivo: bool
    pendencias: List[ManagementIssue]
    motivos_nao_calculaveis: UnavailableReasons


class OccupationIndicators(MonthlyIndicators):
    ocupacao_id: int = Field(gt=0)


class MonthlyManagementResponse(MonthlyIndicators):
    instituicao_id: int = Field(gt=0)
    mes_referencia: str = Field(pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$')
    ocupacao_id: Optional[int] = Field(gt=0)
    ocupacoes: List[OccupationIndicators]
    base_historica: Literal['ESTADO_CADASTRAL_ATUAL_SEM_RECONSTRUCAO']


class AuthenticationErrorResponse(PublicModel):
    detail: str


class ManagementErrorDetail(PublicModel):
    code: Literal['ADMIN_REQUIRED', 'INVALID_MONTHLY_PARAMETERS',
                  'CAPACITY_INSTITUTION_NOT_FOUND', 'CAPACITY_INSTITUTION_INACTIVE',
                  'MONTHLY_CONSOLIDATION_FAILED', 'MONTHLY_CONSOLIDATION_UNAVAILABLE']


class ManagementErrorResponse(PublicModel):
    detail: ManagementErrorDetail
