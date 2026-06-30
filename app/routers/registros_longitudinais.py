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
    return atualizar_registro_longitudinal(db, registro_id, payload)