from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.registro_diario import RegistroDiarioCreate, RegistroDiarioOut
from app.models.registro_diario import RegistroDiario
from app.core.security import get_current_user  # ajuste
from app.models.usuario import Usuario  # ajuste

router = APIRouter(prefix="/registros-diarios", tags=["Registros Diários"])

@router.post("/", response_model=RegistroDiarioOut)
def criar_registro_diario(
    payload: RegistroDiarioCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
):
    obj = RegistroDiario(
        paciente_id=payload.paciente_id,
        profissional_id=usuario.id,
        data_registro=payload.data_registro,
        descricao=payload.descricao,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj
