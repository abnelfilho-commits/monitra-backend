from pydantic import BaseModel
from typing import Optional
from datetime import date

# ------------------------
# PACIENTE
# ------------------------
class PacienteCreate(BaseModel):
    nome: str
    clinica_id: int


# ------------------------
# REGISTRO DIÁRIO
# ------------------------
class RegistroDiarioCreate(BaseModel):
    paciente_id: int
    data: date

    sono_qualidade: Optional[str] = None
    evacuacao: Optional[bool] = None
    consistencia_fezes: Optional[str] = None
    irritabilidade: Optional[str] = None
    crise_sensorial: Optional[bool] = None

    observacao: Optional[str] = None


# ------------------------
# INTERVENÇÃO CLÍNICA
# ------------------------
class IntervencaoCreate(BaseModel):
    paciente_id: int
    data: date
    tipo: str
    descricao: Optional[str] = None

