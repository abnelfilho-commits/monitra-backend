from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import date


class CampoResposta(BaseModel):
    campo_id: int
    valor: Optional[Any]


class RegistroLongitudinalCreate(BaseModel):
    paciente_id: int
    modulo_id: int
    formulario_id: int
    data_registro: date
    origem: str  # PROFISSIONAL | RESPONSAVEL
    respostas: List[CampoResposta]
