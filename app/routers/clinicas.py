from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.clinica import Clinica

router = APIRouter(
    prefix="/clinicas",
    tags=["Clínicas"],
    dependencies=[Depends(get_usuario_atual)]
)


class ClinicaCreate(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None


class ClinicaUpdate(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    ativa: Optional[bool] = True

@router.get("/")
def listar_clinicas(
    db: Session = Depends(get_db),
    usuario_atual=Depends(get_usuario_atual),
):
    query = db.query(Clinica).filter(Clinica.ativa == True)

    if usuario_atual.perfil == "ADMIN":
        return query.order_by(Clinica.nome.asc()).all()

    if usuario_atual.perfil in ["ADMIN_CLINICA", "PROFISSIONAL"]:
        return (
            query
            .filter(Clinica.id == usuario_atual.clinica_id)
            .order_by(Clinica.nome.asc())
            .all()
        )

    if usuario_atual.perfil == "SUPORTE":
        return query.order_by(Clinica.nome.asc()).all()

    return []

@router.get("/{clinica_id}")
def obter_clinica(
    clinica_id: int,
    db: Session = Depends(get_db),
    usuario_atual=Depends(get_usuario_atual),
):
    clinica = (
        db.query(Clinica)
        .filter(Clinica.id == clinica_id)
        .first()
    )

    if not clinica:
        raise HTTPException(
            status_code=404,
            detail="Clínica não encontrada"
        )

    if usuario_atual.perfil == "ADMIN":
        return clinica

    if usuario_atual.perfil in ["ADMIN_CLINICA", "PROFISSIONAL"]:
        if clinica.id != usuario_atual.clinica_id:
            raise HTTPException(
                status_code=403,
                detail="Acesso negado"
            )

    return clinica
    
@router.post("/")
def criar_clinica(clinica: ClinicaCreate, db: Session = Depends(get_db)):
    nova = Clinica(**clinica.dict())
    db.add(nova)
    db.commit()
    db.refresh(nova)
    return nova


@router.put("/{clinica_id}")
def atualizar_clinica(
    clinica_id: int,
    payload: ClinicaUpdate,
    db: Session = Depends(get_db),
):
    clinica = db.query(Clinica).filter(Clinica.id == clinica_id).first()
    if not clinica:
        raise HTTPException(status_code=404, detail="Clínica não encontrada")

    clinica.nome = payload.nome
    clinica.cnpj = payload.cnpj
    clinica.email = payload.email
    clinica.telefone = payload.telefone
    clinica.ativa = payload.ativa if payload.ativa is not None else clinica.ativa

    db.commit()
    db.refresh(clinica)
    return clinica


@router.delete("/{clinica_id}")
def inativar_clinica(clinica_id: int, db: Session = Depends(get_db)):
    clinica = db.query(Clinica).filter(Clinica.id == clinica_id).first()
    if not clinica:
        raise HTTPException(status_code=404, detail="Clínica não encontrada")

    clinica.ativa = False
    db.commit()
    return {"ok": True}
