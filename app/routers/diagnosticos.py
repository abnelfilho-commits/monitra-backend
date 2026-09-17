"""Explicit line-scoped diagnosis API; every diagnosis has a persisted line."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models.diagnostico import Diagnostico
from app.schemas.diagnostico import DiagnosticoCreate, DiagnosticoUpdate, DiagnosticoResponse
from app.services.diagnostico_service import DiagnosticoService
from app.services.care_lines.access import authorized_patient

router = APIRouter(prefix="/diagnosticos", tags=["Diagnósticos"])


def scoped_record(db, user, identity, care_line, write=False):
    row = db.query(Diagnostico).filter_by(id=identity).first()
    if row is None:
        raise HTTPException(404, "Diagnóstico não encontrado.")
    _, line = authorized_patient(db, user, row.paciente_id, care_line, write)
    if row.modulo_id != line.module_id:
        raise HTTPException(404, "Diagnóstico não encontrado nesta linha.")
    return row


@router.post("", response_model=DiagnosticoResponse, status_code=201)
def criar_diagnostico(payload: DiagnosticoCreate, db: Session = Depends(get_db),
                      usuario=Depends(get_usuario_atual)):
    _, line = authorized_patient(db, usuario, payload.paciente_id, payload.care_line, True)
    return DiagnosticoService.criar(db, payload, module_id=line.module_id)


@router.get("/paciente/{paciente_id}", response_model=List[DiagnosticoResponse])
def listar_diagnosticos_paciente(paciente_id: int, care_line: str = Query(...),
                                 db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    _, line = authorized_patient(db, usuario, paciente_id, care_line)
    return db.query(Diagnostico).filter_by(paciente_id=paciente_id, modulo_id=line.module_id).order_by(
        Diagnostico.data_diagnostico.desc(), Diagnostico.id.desc()).all()


@router.get("/{diagnostico_id}", response_model=DiagnosticoResponse)
def buscar_diagnostico(diagnostico_id: int, care_line: str = Query(...),
                       db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return scoped_record(db, usuario, diagnostico_id, care_line)


@router.put("/{diagnostico_id}", response_model=DiagnosticoResponse)
def atualizar_diagnostico(diagnostico_id: int, payload: DiagnosticoUpdate,
                          care_line: str = Query(...), db: Session = Depends(get_db),
                          usuario=Depends(get_usuario_atual)):
    scoped_record(db, usuario, diagnostico_id, care_line, True)
    return DiagnosticoService.atualizar(db, diagnostico_id, payload)


@router.patch("/{diagnostico_id}/cancelar", response_model=DiagnosticoResponse)
def cancelar_diagnostico(diagnostico_id: int, care_line: str = Query(...),
                         db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    scoped_record(db, usuario, diagnostico_id, care_line, True)
    return DiagnosticoService.cancelar(db, diagnostico_id)


@router.patch("/{diagnostico_id}/revisar", response_model=DiagnosticoResponse)
def revisar_diagnostico(diagnostico_id: int, care_line: str = Query(...),
                        db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    scoped_record(db, usuario, diagnostico_id, care_line, True)
    return DiagnosticoService.revisar(db, diagnostico_id)
