from datetime import date
from typing import Optional
from pydantic import BaseModel


class RegistroCardioResponsavelCreate(BaseModel):
    data: date

    glicemia_jejum: Optional[float] = None
    pressao_sistolica: Optional[float] = None
    pressao_diastolica: Optional[float] = None
    peso: Optional[float] = None

    sono: Optional[str] = None
    humor: Optional[str] = None
    observacoes: Optional[str] = None