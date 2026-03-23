from fastapi import APIRouter, Depends
from app.core.deps import get_usuario_atual
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.database import get_db
from app.models.vinculo import ProfissionalPaciente

router = APIRouter(
    prefix="/vinculos",
    tags=["Vínculos"],
    dependencies=[Depends(get_usuario_atual)]
)

class VinculoCreate(BaseModel):
    profissional_id: int
    paciente_id: int

@router.post("/profissional-paciente")
def criar_vinculo(vinculo: VinculoCreate, db: Session = Depends(get_db)):
    novo = ProfissionalPaciente(**vinculo.dict())
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo

