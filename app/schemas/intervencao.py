from pydantic import BaseModel
from typing import Optional, Union
from datetime import datetime


class IntervencaoUpdate(BaseModel):
    paciente_id: int
    tipo: str
    descricao: Optional[str] = None
    data_intervencao: datetime


class IntervencaoCreate(IntervencaoUpdate):
    requested_care_line: Optional[Union[str, int]] = None
