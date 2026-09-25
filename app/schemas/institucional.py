"""Domain input contracts; no implicit permission or legacy synchronization."""
import re
from datetime import date, datetime
from typing import Optional, Literal
from pydantic import BaseModel, validator, root_validator


def normalize_cnpj(value):
    if value is None:
        return None
    if not re.fullmatch(r'[0-9./\-\s]+', value):
        raise ValueError('CNPJ inválido')
    digits = re.sub(r'\D', '', value)
    if len(digits) != 14 or len(set(digits)) == 1:
        raise ValueError('CNPJ inválido')
    for size, weights in ((12, (5,4,3,2,9,8,7,6,5,4,3,2)), (13, (6,5,4,3,2,9,8,7,6,5,4,3,2))):
        remainder = sum(int(n)*w for n,w in zip(digits[:size], weights)) % 11
        if int(digits[size]) != (0 if remainder < 2 else 11-remainder):
            raise ValueError('CNPJ inválido')
    return digits


class InstituicaoCreate(BaseModel):
    razao_social: str
    nome_fantasia: Optional[str] = None
    cnpj: Optional[str] = None
    tipo_instituicao: Literal['CLINICA','UNIDADE_SAUDE','OPERADORA_SAUDE','GOVERNO_SECRETARIA','EMPRESA','INSTITUTO_ASSOCIACAO','OUTRO']
    instituicao_pai_id: Optional[int] = None
    ativo: bool = True

    _cnpj = validator('cnpj', allow_reuse=True)(normalize_cnpj)

    @validator('razao_social')
    def official_name(cls, value):
        if not value.strip():
            raise ValueError('Denominação institucional obrigatória')
        return value.strip()


class PapelCreate(BaseModel):
    instituicao_id: int
    papel: Literal['CONTRATANTE', 'ASSISTENCIAL']
    ativo: bool = True


class TemporalCreate(BaseModel):
    model_config = {'extra': 'forbid'}
    data_inicio: date
    data_fim: Optional[date] = None
    ativo: Literal[True] = True

    @root_validator(skip_on_failure=True)
    def period(cls, values):
        if values.get('data_fim') and values['data_fim'] < values['data_inicio']:
            raise ValueError('data_fim anterior a data_inicio')
        return values


class PacienteInstituicaoCreate(TemporalCreate):
    paciente_id: int
    instituicao_id: int
    tipo_vinculo: Literal['BENEFICIARIO','ASSISTENCIAL','COLABORADOR','ASSOCIADO','OUTRO']
    identificador_externo: Optional[str] = None


class ProfissionalInstituicaoCreate(TemporalCreate):
    profissional_id: int
    instituicao_id: int
    ocupacao_id: int


class PacienteProfissionalCreate(TemporalCreate):
    paciente_id: int
    paciente_instituicao_id: int
    profissional_instituicao_id: int


# HTTP transport only: domain CREATE contracts above remain unchanged.
class MotivoInstitucional(BaseModel):
    model_config = {'extra': 'forbid'}
    motivo: str

    @validator('motivo')
    def required_reason(cls, value):
        if not value.strip():
            raise ValueError('Motivo obrigatório')
        return value


class PacienteInstituicaoRequest(PacienteInstituicaoCreate, MotivoInstitucional):
    pass


class ProfissionalInstituicaoRequest(ProfissionalInstituicaoCreate, MotivoInstitucional):
    pass


class PacienteProfissionalRequest(PacienteProfissionalCreate, MotivoInstitucional):
    pass


class CloseInstitucionalRequest(MotivoInstitucional):
    data_fim: date


class VinculoInstitucionalResponse(BaseModel):
    model_config = {'from_attributes': True}
    id: int
    data_inicio: date
    data_fim: Optional[date]
    ativo: bool
    criado_em: datetime
    atualizado_em: datetime


class PacienteInstituicaoResponse(VinculoInstitucionalResponse):
    paciente_id: int
    instituicao_id: int
    tipo_vinculo: str
    identificador_externo: Optional[str]


class ProfissionalInstituicaoResponse(VinculoInstitucionalResponse):
    profissional_id: int
    instituicao_id: int
    ocupacao_id: int


class PacienteProfissionalResponse(VinculoInstitucionalResponse):
    paciente_id: int
    paciente_instituicao_id: Optional[int]
    profissional_instituicao_id: int
