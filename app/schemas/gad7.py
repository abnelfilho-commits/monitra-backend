from pydantic import BaseModel, ConfigDict, field_validator
from app.schemas.phq9 import PHQ9Out, PHQ9Jornada


class GAD7Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    respostas: dict[str, str]

    @field_validator('respostas')
    @classmethod
    def complete(cls, answers):
        if set(answers) != {f'gad7_{i}' for i in range(1,8)} or any(v not in {'0','1','2','3'} for v in answers.values()):
            raise ValueError('Responda às sete questões com uma alternativa válida.')
        return answers


class GAD7Out(PHQ9Out):
    """Same persisted framework result and authenticated provenance contract."""


class GAD7Jornada(PHQ9Jornada):
    itens: list[GAD7Out]
