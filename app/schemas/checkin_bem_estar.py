from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, StrictStr


class CheckinCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    paciente_id: int = Field(strict=True, gt=0, le=2147483647)
    modulo_id: Literal[3]
    formulario_id: int = Field(strict=True, gt=0, le=2147483647)
    respostas: dict[str, StrictStr]


class CampoCheckin(BaseModel):
    id: int
    nome_campo: str
    label: str
    tipo_campo: str
    obrigatorio: bool
    opcoes: list[dict[str,str]]


class FormularioCheckin(BaseModel):
    id: int
    campos: list[CampoCheckin]


class CheckinOut(BaseModel):
    id: int
    data_hora: datetime
    baseline: bool
    respondente_pessoa_id: int
    registrador_profissional_id: Optional[int]
    canal: str
    modalidade: str
    respostas: dict[str, str]


class BemEstarJornada(BaseModel):
    pode_registrar: bool
    formulario: Optional[FormularioCheckin] = None
    checkins: list[CheckinOut]
