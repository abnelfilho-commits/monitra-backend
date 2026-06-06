from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.responsavel import Responsavel
from app.models.responsavel_paciente import ResponsavelPaciente
from app.models.paciente import Paciente
from app.schemas.responsavel import (
    ResponsavelCreate,
    ResponsavelOut,
    ResponsavelPacienteVinculoCreate,
)
from app.core.security import hash_senha
from app.core.deps import get_usuario_atual
from app.core.acl import is_admin_global

router = APIRouter(
    prefix="/responsaveis",
    tags=["Responsáveis"]
)


@router.post("/", response_model=ResponsavelOut)
def criar_responsavel(
    payload: ResponsavelCreate,
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    existente = (
        db.query(Responsavel)
        .filter(Responsavel.email == payload.email)
        .first()
    )
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe responsável com este e-mail."
        )

    responsavel = Responsavel(
        nome=payload.nome,
        email=payload.email,
        telefone=payload.telefone,
        senha_hash=hash_senha(payload.senha),
        ativo=True,
    )

    db.add(responsavel)
    db.commit()
    db.refresh(responsavel)
    return responsavel


@router.get("/", response_model=list[ResponsavelOut])
def listar_responsaveis(
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):

    if is_admin_global(usuario):
        return (
            db.query(Responsavel)
            .order_by(Responsavel.nome.asc())
            .all()
        )

    if not usuario.clinica_id:
        raise HTTPException(
            status_code=403,
            detail="Usuário sem clínica vinculada"
        )

    responsaveis = (
        db.query(Responsavel)
        .join(
            ResponsavelPaciente,
            Responsavel.id == ResponsavelPaciente.responsavel_id
        )
        .join(
            Paciente,
            Paciente.id == ResponsavelPaciente.paciente_id
        )
        .filter(
            Paciente.clinica_id == usuario.clinica_id
        )
        .distinct()
        .order_by(Responsavel.nome.asc())
        .all()
    )

    return responsaveis

@router.post("/vinculos")
def vincular_responsavel_paciente(
    payload: ResponsavelPacienteVinculoCreate,
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    responsavel = (
        db.query(Responsavel)
        .filter(Responsavel.id == payload.responsavel_id)
        .first()
    )
    if not responsavel:
        raise HTTPException(status_code=404, detail="Responsável não encontrado.")

    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == payload.paciente_id)
        .first()
    )
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    existente = (
        db.query(ResponsavelPaciente)
        .filter(
            ResponsavelPaciente.responsavel_id == payload.responsavel_id,
            ResponsavelPaciente.paciente_id == payload.paciente_id,
        )
        .first()
    )
    if existente:
        raise HTTPException(status_code=400, detail="Vínculo já existe.")

    vinculo = ResponsavelPaciente(
        responsavel_id=payload.responsavel_id,
        paciente_id=payload.paciente_id,
        parentesco=payload.parentesco,
        principal=payload.principal,
        ativo=True,
    )

    db.add(vinculo)
    db.commit()
    db.refresh(vinculo)

    return {
        "message": "Vínculo criado com sucesso.",
        "id": vinculo.id,
    }

@router.get("/vinculos")
def listar_vinculos(
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    vinculos = (
        db.query(
            ResponsavelPaciente,
            Responsavel,
            Paciente
        )
        .join(
            Responsavel,
            Responsavel.id == ResponsavelPaciente.responsavel_id
        )
        .join(
            Paciente,
            Paciente.id == ResponsavelPaciente.paciente_id
        )
        if not is_admin_global(usuario):
            vinculos = vinculos.filter(
                Paciente.clinica_id == usuario.clinica_id
            )
        .all()
    )

    return [
        {
            "id": v.id,
            "paciente_id": p.id,
            "paciente_nome": p.nome,
            "responsavel_id": r.id,
            "responsavel_nome": r.nome,
            "parentesco": v.parentesco,
            "principal": v.principal,
            "ativo": v.ativo,
        }
        for v, r, p in vinculos
    ]