from app.core.acl import is_admin
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.clinica import Clinica
from app.models.paciente import Paciente
from app.models.usuario import Usuario
from app.services.risk_analytics import (
    analisar_mapa_risco_clinica,
    analisar_risco_paciente,
    obter_evolucao_paciente,
)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics Clínico"],
)


@router.get("/pacientes/{paciente_id}/risco")
def obter_risco_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    if not is_admin(usuario):
        if usuario.clinica_id is None or usuario.clinica_id != paciente.clinica_id:
            raise HTTPException(status_code=403, detail="Acesso negado.")

    return analisar_risco_paciente(db, paciente)


@router.get("/clinicas/{clinica_id}/mapa-risco")
def obter_mapa_risco_clinica(
    clinica_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    clinica = db.query(Clinica).filter(Clinica.id == clinica_id).first()
    if not clinica:
        raise HTTPException(status_code=404, detail="Clínica não encontrada.")

    if not is_admin(usuario):
        if usuario.clinica_id is None or usuario.clinica_id != clinica_id:
            raise HTTPException(status_code=403, detail="Acesso negado.")

    return analisar_mapa_risco_clinica(db, clinica_id)


@router.get("/pacientes/{paciente_id}/evolucao")
def obter_evolucao_clinica_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    if not is_admin(usuario):
        if usuario.clinica_id is None or usuario.clinica_id != paciente.clinica_id:
            raise HTTPException(status_code=403, detail="Acesso negado.")

    return {
        "paciente_id": paciente.id,
        "nome": paciente.nome,
        "serie": obter_evolucao_paciente(db, paciente),
    }
