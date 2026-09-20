from app.services.daily_record.concurrency import lock_patient
from app.services.daily_record.adapters import is_daily, write_legacy_longitudinal
from app.models.modular import RegistroLongitudinal
from fastapi import APIRouter, Depends, HTTPException
from app.core.deps import get_usuario_atual
from app.services.care_lines.access import authorized_patient
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
    proteger_atendimento_canonico,
)

router = APIRouter(
    prefix="/registros-longitudinais",
    tags=["Registros Longitudinais"],
)


@router.post("/")
def criar_registro(
    payload: RegistroLongitudinalCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    authorized_patient(db, usuario, payload.paciente_id, payload.modulo_id, write=True)
    if is_daily(db, payload.formulario_id):
        result = write_legacy_longitudinal(db, payload, user_id=usuario.id)
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
    usuario=Depends(get_usuario_atual),
):
    record = db.query(RegistroLongitudinal).filter_by(id=registro_id).first()
    if record is None:
        raise HTTPException(404, 'Registro não encontrado.')
    authorized_patient(db, usuario, record.paciente_id, record.modulo_id)
    return obter_registro_longitudinal(db, registro_id)


@router.patch("/{registro_id}", response_model=RegistroLongitudinalOut)
def atualizar_registro(
    registro_id: int,
    payload: RegistroLongitudinalUpdate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    record = db.query(RegistroLongitudinal).filter_by(id=registro_id).first()
    if record is None:
        raise HTTPException(404, 'Registro não encontrado.')
    authorized_patient(db, usuario, record.paciente_id, record.modulo_id, write=True)
    if is_daily(db, record.formulario_id) or is_daily(db, payload.formulario_id):
        lock_patient(db, record.paciente_id)
    existing = proteger_atendimento_canonico(db, registro_id)
    if (record.paciente_id, record.modulo_id) != (payload.paciente_id, payload.modulo_id):
        raise HTTPException(400, 'Paciente e Linha são imutáveis.')
    if is_daily(db, payload.formulario_id) or (existing and is_daily(db, existing.formulario_id)):
        write_legacy_longitudinal(db, payload, registro_id, user_id=usuario.id)
        return obter_registro_longitudinal(db, registro_id)
    return atualizar_registro_longitudinal(db, registro_id, payload)