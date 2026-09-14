from app.services.daily_record.adapters import is_daily, write_legacy_longitudinal
from app.models.modular import RegistroLongitudinal
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.registros_longitudinais import (
    RegistroLongitudinalCreate,
    RegistroLongitudinalUpdate,
    RegistroLongitudinalOut,
)
from app.services.registros_longitudinais import (
    criar_registro_longitudinal,
    obter_registro_longitudinal,
    atualizar_registro_longitudinal,
)

router = APIRouter(
    prefix="/registros-longitudinais",
    tags=["Registros Longitudinais"],
)


@router.post("/")
def criar_registro(
    payload: RegistroLongitudinalCreate,
    db: Session = Depends(get_db),
):
    if is_daily(db, payload.formulario_id):
        result = write_legacy_longitudinal(db, payload)
        return {"id": result.record_id, "status": "ok"}
    registro = criar_registro_longitudinal(db, payload)

    return {
        "id": registro.id,
        "status": "ok"
    }


@router.get("/{registro_id}", response_model=RegistroLongitudinalOut)
def obter_registro(
    registro_id: int,
    db: Session = Depends(get_db),
):
    return obter_registro_longitudinal(db, registro_id)


@router.patch("/{registro_id}", response_model=RegistroLongitudinalOut)
def atualizar_registro(
    registro_id: int,
    payload: RegistroLongitudinalUpdate,
    db: Session = Depends(get_db),
):
    existing = db.query(RegistroLongitudinal).filter(RegistroLongitudinal.id == registro_id).first()
    if is_daily(db, payload.formulario_id) or (existing and is_daily(db, existing.formulario_id)):
        write_legacy_longitudinal(db, payload, registro_id)
        return obter_registro_longitudinal(db, registro_id)
    return atualizar_registro_longitudinal(db, registro_id, payload)