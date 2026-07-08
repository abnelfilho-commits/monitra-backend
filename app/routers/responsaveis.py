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
    tags=["Responsáveis"],
)


@router.post("/", response_model=ResponsavelOut)
def criar_responsavel(
    payload: ResponsavelCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    email_normalizado = str(payload.email).strip().lower()

    existente = (
        db.query(Responsavel)
        .filter(Responsavel.email == email_normalizado)
        .first()
    )

    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já existe responsável com este e-mail.",
        )

    if is_admin_global(usuario):
        if not payload.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe a clínica do responsável.",
            )

        clinica_id = payload.clinica_id

    else:
        if not usuario.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário sem clínica vinculada.",
            )

        clinica_id = usuario.clinica_id

    responsavel = Responsavel(
        nome=payload.nome.strip(),
        email=email_normalizado,
        telefone=payload.telefone.strip()
        if payload.telefone
        else None,
        senha_hash=hash_senha(payload.senha),
        clinica_id=clinica_id,
        ativo=True,
    )

    db.add(responsavel)
    db.commit()
    db.refresh(responsavel)

    return responsavel


@router.get("/", response_model=list[ResponsavelOut])
def listar_responsaveis(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    query = (
        db.query(Responsavel)
        .filter(Responsavel.ativo == True)
    )

    if not is_admin_global(usuario):
        if not usuario.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário sem clínica vinculada.",
            )

        query = query.filter(
            Responsavel.clinica_id == usuario.clinica_id
        )

    return (
        query
        .order_by(Responsavel.nome.asc())
        .all()
    )


@router.post("/vinculos")
def vincular_responsavel_paciente(
    payload: ResponsavelPacienteVinculoCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    responsavel = (
        db.query(Responsavel)
        .filter(Responsavel.id == payload.responsavel_id)
        .first()
    )

    if not responsavel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Responsável não encontrado.",
        )

    paciente = (
        db.query(Paciente)
        .filter(Paciente.id == payload.paciente_id)
        .first()
    )

    if not paciente:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Paciente não encontrado.",
        )

    if not is_admin_global(usuario):
        if not usuario.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário sem clínica vinculada.",
            )

        if responsavel.clinica_id != usuario.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Responsável não pertence à sua clínica.",
            )

        if paciente.clinica_id != usuario.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Paciente não pertence à sua clínica.",
            )

    if responsavel.clinica_id != paciente.clinica_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Responsável e paciente pertencem a clínicas diferentes.",
        )

    existente = (
        db.query(ResponsavelPaciente)
        .filter(
            ResponsavelPaciente.responsavel_id == payload.responsavel_id,
            ResponsavelPaciente.paciente_id == payload.paciente_id,
        )
        .first()
    )

    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vínculo já existe.",
        )

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
    usuario=Depends(get_usuario_atual),
):
    query = (
        db.query(
            ResponsavelPaciente,
            Responsavel,
            Paciente,
        )
        .join(
            Responsavel,
            Responsavel.id == ResponsavelPaciente.responsavel_id,
        )
        .join(
            Paciente,
            Paciente.id == ResponsavelPaciente.paciente_id,
        )
    )

    if not is_admin_global(usuario):
        if not usuario.clinica_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário sem clínica vinculada.",
            )

        query = query.filter(
            Responsavel.clinica_id == usuario.clinica_id,
            Paciente.clinica_id == usuario.clinica_id,
        )

    vinculos = query.all()

    return [
        {
            "id": vinculo.id,
            "paciente_id": paciente.id,
            "paciente_nome": paciente.nome,
            "responsavel_id": responsavel.id,
            "responsavel_nome": responsavel.nome,
            "parentesco": vinculo.parentesco,
            "principal": vinculo.principal,
            "ativo": vinculo.ativo,
        }
        for vinculo, responsavel, paciente in vinculos
    ]