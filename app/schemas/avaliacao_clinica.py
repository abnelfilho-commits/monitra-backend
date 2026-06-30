from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any

from pydantic import BaseModel


class AvaliacaoClinicaBase(BaseModel):
    registro_id: int
    paciente_id: int
    modulo_id: int

    formulario_id: Optional[int] = None

    instrumento: str
    versao: Optional[str] = None

    score: Optional[Decimal] = None
    score_texto: Optional[str] = None

    classificacao: Optional[str] = None
    classificacao_codigo: Optional[str] = None

    conduta: Optional[str] = None
    interpretacao: Optional[str] = None

    resultado: Optional[Dict[str, Any]] = None

    engine_version: Optional[str] = None

    profissional_id: Optional[int] = None

    status: Optional[str] = "CONCLUIDA"


class AvaliacaoClinicaCreate(AvaliacaoClinicaBase):
    pass


class AvaliacaoClinicaResponse(AvaliacaoClinicaBase):
    id: int
    executado_em: datetime
    created_at: datetime

    class Config:
        from_attributes = True