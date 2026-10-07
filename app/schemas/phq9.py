from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, field_validator
from app.schemas.checkin_bem_estar import FormularioCheckin


class PHQ9Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    respostas: dict[str, str]

    @field_validator('respostas')
    @classmethod
    def complete(cls, answers):
        if set(answers) != {f'phq9_{i}' for i in range(1,10)} or any(v not in {'0','1','2','3'} for v in answers.values()):
            raise ValueError('Responda às nove questões com uma alternativa válida.')
        return answers


class PHQ9Out(BaseModel):
    id: int
    registro_id: int
    data_hora: datetime
    registrador_usuario_id: int
    registrador_profissional_id: int
    resultado: dict


class PHQ9Jornada(BaseModel):
    pode_registrar: bool
    formulario: Optional[FormularioCheckin] = None
    instrucoes: str
    itens: list[PHQ9Out]
