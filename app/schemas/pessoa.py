"""Identity input validation, without matching or legacy association."""
import re
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field, StrictStr, field_validator


def normalize_cpf(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("CPF deve ser texto")
    value = value.strip()
    if not value:
        return None
    if not re.fullmatch(r"(?:[0-9]{11}|[0-9]{3}\.[0-9]{3}\.[0-9]{3}-[0-9]{2})", value):
        raise ValueError("CPF inválido")
    digits = value.replace(".", "").replace("-", "")
    if len(set(digits)) == 1:
        raise ValueError("CPF inválido")
    for size in (9, 10):
        remainder = sum(int(digit) * weight for digit, weight in zip(digits[:size], range(size + 1, 1, -1))) % 11
        expected = 0 if remainder < 2 else 11 - remainder
        if int(digits[size]) != expected:
            raise ValueError("CPF inválido")
    return digits


class PessoaDados(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome_completo: StrictStr
    nome_social: Optional[StrictStr] = None
    data_nascimento: Optional[date] = None
    sexo: Optional[StrictStr] = Field(default=None, max_length=32)
    cpf: Optional[StrictStr] = None
    email: Optional[EmailStr] = None
    telefone: Optional[StrictStr] = Field(default=None, max_length=32)
    ativo: bool = True

    @field_validator("nome_completo")
    @classmethod
    def required_name(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Nome completo obrigatório")
        return value

    @field_validator("nome_social", "sexo", "email", "telefone", mode="before")
    @classmethod
    def optional_text(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("cpf", mode="before")
    @classmethod
    def valid_cpf(cls, value):
        return normalize_cpf(value)

    @field_validator("data_nascimento")
    @classmethod
    def birth_date(cls, value):
        if value is not None and value > date.today():
            raise ValueError("Data de nascimento futura")
        return value


class PessoaCreate(PessoaDados):
    cpf: StrictStr

    @field_validator("cpf")
    @classmethod
    def required_cpf(cls, value):
        if value is None:
            raise ValueError("CPF obrigatório para nova Pessoa")
        return value


class PessoaOut(PessoaDados):
    model_config = ConfigDict(from_attributes=True, extra="forbid")
    id: int
    criado_em: datetime
    atualizado_em: datetime
