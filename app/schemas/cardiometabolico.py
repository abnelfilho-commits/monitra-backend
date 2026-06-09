from pydantic import BaseModel

from typing import Optional

class RegistroDiarioCardio(BaseModel):

    paciente_id: int

    glicemia_jejum: Optional[float] = None
    glicemia_pos_prandial: Optional[float] = None

    pressao_sistolica: Optional[float] = None
    pressao_diastolica: Optional[float] = None

    peso: Optional[float] = None

    altura: Optional[float] = None

    ingestao_hidrica: Optional[float] = None

    atividade_fisica: Optional[str] = None

    humor: Optional[str] = None
    sono: Optional[str] = None

    fadiga: Optional[bool] = False
    dor: Optional[bool] = False

    uso_medicacao: Optional[bool] = False
    adesao_alimentar: Optional[bool] = False

    tontura: Optional[bool] = False
    cefaleia: Optional[bool] = False

    observacoes: Optional[str] = None
    
class IntervencaoCreate(BaseModel):
    tipo: str
    descricao: str
    prioridade: str = "moderada"
