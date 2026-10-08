from pydantic import BaseModel, ConfigDict, field_validator
from app.services.cbi_contract import FIELDS
from app.schemas.phq9 import PHQ9Out, PHQ9Jornada


class CBICreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    respostas: dict[str, str]

    @field_validator('respostas')
    @classmethod
    def complete(cls, answers):
        if set(answers) != {name for name, _, _ in FIELDS} or any(v not in {'0','1','2','3','4'} for v in answers.values()):
            raise ValueError('Responda às 19 questões com uma alternativa válida.')
        return answers


class CBIOut(PHQ9Out):
    """Same persisted framework result and authenticated provenance contract."""


class CBIJornada(PHQ9Jornada):
    dominios: list[dict]
    itens: list[CBIOut]
