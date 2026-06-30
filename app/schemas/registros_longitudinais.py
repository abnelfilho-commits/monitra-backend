from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import date


class CampoResposta(BaseModel):
    campo_id: int
    valor: Optional[Any]


class RegistroLongitudinalCreate(BaseModel):
    paciente_id: int
    modulo_id: int
    formulario_id: int
    data_registro: date
    origem: str
    respostas: List[CampoResposta]


class RegistroLongitudinalUpdate(BaseModel):
    paciente_id: int
    modulo_id: int
    formulario_id: int
    data_registro: date
    origem: str
    respostas: List[CampoResposta]


class RegistroLongitudinalOut(BaseModel):
    id: int
    paciente_id: int
    modulo_id: int
    formulario_id: int
    data_registro: date
    origem: str
    respostas: Dict[str, Optional[Any]]