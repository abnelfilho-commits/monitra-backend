from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class IntervencaoCreate(BaseModel):
    paciente_id: int
    tipo: str
    descricao: Optional[str] = None
    data_intervencao: datetime

