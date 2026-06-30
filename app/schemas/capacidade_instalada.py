from decimal import Decimal
from typing import Optional
from datetime import datetime

from pydantic import BaseModel


class CapacidadeInstaladaBase(BaseModel):
    modulo_id: int
    ocupacao_id: int
    quantidade_profissionais: int
    horas_semanais_por_profissional: Decimal


class CapacidadeInstaladaCreate(CapacidadeInstaladaBase):
    pass


class CapacidadeInstaladaUpdate(BaseModel):
    quantidade_profissionais: Optional[int] = None
    horas_semanais_por_profissional: Optional[Decimal] = None
    ativo: Optional[bool] = None


class CapacidadeInstaladaResponse(CapacidadeInstaladaBase):
    id: int
    ativo: bool
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True