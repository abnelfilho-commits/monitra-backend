"""Explicit account provisioning; no clinical permission payloads."""
from pydantic import BaseModel, ConfigDict, EmailStr, SecretStr, StrictBool, PositiveInt, field_validator
from app.schemas.autorizacao_institucional import PerfilInstitucional, AcessoResponse


class AcessoPessoaCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: EmailStr
    senha_inicial: SecretStr
    instituicao_id: PositiveInt
    perfil_institucional: PerfilInstitucional
    ativo: StrictBool = False

    @field_validator('senha_inicial')
    @classmethod
    def password(cls, value):
        password = value.get_secret_value()
        if not password.strip() or len(password.encode('utf-8')) > 72:
            raise ValueError('INVALID_INITIAL_PASSWORD')
        return value


class AcessoPessoaOut(BaseModel):
    pessoa_id: PositiveInt
    usuario_id: PositiveInt
    email: EmailStr
    usuario_ativo: bool
    autorizacao: AcessoResponse
