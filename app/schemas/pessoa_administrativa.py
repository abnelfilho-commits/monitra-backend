"""Allowlisted administrative reads: no credentials or clinical content."""
from datetime import date
from typing import Optional
from pydantic import BaseModel
from app.schemas.autorizacao_institucional import AcessoResponse


class ContaPessoaOut(BaseModel):
    id: int
    email: str
    ativo: bool


class AutorizacaoPessoaOut(AcessoResponse):
    instituicao_nome: str
    instituicao_ativa: bool


class PessoaAcessosOut(BaseModel):
    pessoa_id: int
    usuario: Optional[ContaPessoaOut]
    autorizacoes: list[AutorizacaoPessoaOut]


class VinculoPessoaOut(BaseModel):
    id: int
    instituicao_id: int
    instituicao_nome: str
    instituicao_ativa: bool
    data_inicio: date
    data_fim: Optional[date]
    ativo: bool


class VinculoPacienteOut(VinculoPessoaOut):
    paciente_id: int
    tipo_vinculo: str


class VinculoProfissionalOut(VinculoPessoaOut):
    profissional_id: int
    ocupacao_id: int


class PessoaVinculosOut(BaseModel):
    pessoa_id: int
    paciente_id: Optional[int]
    profissional_id: Optional[int]
    profissional_ativo: Optional[bool]
    pacientes: list[VinculoPacienteOut]
    profissionais: list[VinculoProfissionalOut]
