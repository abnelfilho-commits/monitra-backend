"""Minimal domain commands; institutional profiles do not define granular rights."""
from typing import Literal, Optional
from pydantic import BaseModel, PositiveInt, StrictBool

PerfilInstitucional = Literal['GESTOR', 'PROFISSIONAL', 'SUPORTE']


class AcessoCreate(BaseModel):
    model_config = {'extra': 'forbid'}
    usuario_id: PositiveInt
    instituicao_id: PositiveInt
    perfil_institucional: PerfilInstitucional
    ativo: StrictBool = False


class PerfilChange(BaseModel):
    model_config = {'extra': 'forbid'}
    perfil_institucional: PerfilInstitucional


class AutorizacaoConfirmada(BaseModel):
    usuario_id: int
    instituicao_id: int
    admin_global: bool
    perfil_institucional: Optional[PerfilInstitucional] = None
