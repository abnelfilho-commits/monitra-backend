from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.registros_longitudinais import RegistroLongitudinalCreate
from app.services.registros_longitudinais import criar_registro_longitudinal

router = APIRouter(prefix="/registros-longitudinais", tags=["Registros Longitudinais"])


@router.post("/")
def criar_registro(payload: RegistroLongitudinalCreate, db: Session = Depends(get_db)):
    registro = criar_registro_longitudinal(db, payload)
    return {"id": registro.id, "status": "ok"}
