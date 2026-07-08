from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from passlib.context import CryptContext

from app.core.acl import is_admin_global
from app.database import get_db
from app.core.deps import get_usuario_atual

from app.models.profissional import Profissional
from app.models.profissional_modulo import ProfissionalModulo
from app.models.modular import ModuloClinico
from app.models.usuario import Usuario

from app.schemas.profissional import (
    ProfissionalCreate,
    ProfissionalOut,
    ProfissionalUpdate,
)


router = APIRouter(
    prefix="/profissionais",
    tags=["Profissionais"],
)


pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
)


def serializar_profissional(p: Profissional, db: Session):
    usuario_vinculado = (
        db.query(Usuario)
        .filter(Usuario.profissional_id == p.id)
        .first()
    )

    modulo_ids = [
        item.modulo_id
        for item in (
            db.query(ProfissionalModulo)
            .filter(ProfissionalModulo.profissional_id == p.id)
            .all()
        )
    ]

    return {
        "id": p.id,
        "nome": p.nome,
        "email": p.email,
        "especialidade": p.especialidade,
        "clinica_id": p.clinica_id,
        "clinica_nome": p.clinica.nome if p.clinica else None,
        "ativo": p.ativo,
        "modulo_ids": modulo_ids,
        "usuario_id": usuario_vinculado.id if usuario_vinculado else None,
        "usuario_ativo": usuario_vinculado.ativo if usuario_vinculado else None,
    }


@router.get("/", response_model=list[ProfissionalOut])
def listar_profissionais(
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_usuario_atual),
):
    query = db.query(Profissional).filter(Profissional.ativo == True)

    if not is_admin_global(usuario_atual):
        if not usuario_atual.clinica_id:
            raise HTTPException(
                status_code=403,
                detail="Usuário sem clínica vinculada",
            )

        query = query.filter(Profissional.clinica_id == usuario_atual.clinica_id)

    profissionais = query.order_by(Profissional.nome.asc()).all()

    return [serializar_profissional(p, db) for p in profissionais]


@router.get("/clinica/{clinica_id}", response_model=list[ProfissionalOut])
def listar_profissionais_por_clinica(
    clinica_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if not is_admin_global(usuario) and usuario.clinica_id != clinica_id:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado",
        )

    profissionais = (
        db.query(Profissional)
        .filter(
            Profissional.clinica_id == clinica_id,
            Profissional.ativo == True,
        )
        .order_by(Profissional.nome.asc())
        .all()
    )

    return [serializar_profissional(p, db) for p in profissionais]


@router.get("/{profissional_id}", response_model=ProfissionalOut)
def obter_profissional(
    profissional_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    profissional = (
        db.query(Profissional)
        .filter(Profissional.id == profissional_id)
        .first()
    )

    if not profissional:
        raise HTTPException(
            status_code=404,
            detail="Profissional não encontrado",
        )

    if not is_admin_global(usuario) and usuario.clinica_id != profissional.clinica_id:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado",
        )

    return serializar_profissional(profissional, db)


@router.post(
    "/",
    response_model=ProfissionalOut,
    status_code=status.HTTP_201_CREATED,
)
def criar_profissional(
    payload: ProfissionalCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if not payload.email:
        raise HTTPException(
            status_code=400,
            detail="E-mail é obrigatório para criar o acesso do profissional.",
        )

    if not payload.modulo_ids:
        raise HTTPException(
            status_code=400,
            detail="Selecione pelo menos um módulo de acesso.",
        )

    senha_bytes = payload.senha.encode("utf-8")

    if len(senha_bytes) > 72:
        raise HTTPException(
            status_code=400,
            detail="Senha muito longa (máx. 72 bytes).",
        )

    clinica_id = payload.clinica_id

    if not is_admin_global(usuario):
        if usuario.clinica_id is None:
            raise HTTPException(
                status_code=403,
                detail="Usuário sem clínica vinculada",
            )

        clinica_id = usuario.clinica_id

    email_normalizado = str(payload.email).strip().lower()

    profissional_existente = (
        db.query(Profissional)
        .filter(Profissional.email == email_normalizado)
        .first()
    )

    if profissional_existente:
        raise HTTPException(
            status_code=409,
            detail="Já existe um profissional com este e-mail.",
        )

    usuario_existente = (
        db.query(Usuario)
        .filter(Usuario.email == email_normalizado)
        .first()
    )

    if usuario_existente:
        raise HTTPException(
            status_code=409,
            detail="Já existe um usuário com este e-mail.",
        )

    modulo_ids_unicos = list(set(payload.modulo_ids))

    modulos = (
        db.query(ModuloClinico)
        .filter(
            ModuloClinico.id.in_(modulo_ids_unicos),
            ModuloClinico.ativo == True,
        )
        .all()
    )

    if len(modulos) != len(modulo_ids_unicos):
        raise HTTPException(
            status_code=400,
            detail="Um ou mais módulos informados são inválidos ou estão inativos.",
        )

    try:
        novo_profissional = Profissional(
            nome=payload.nome.strip(),
            email=email_normalizado,
            especialidade=payload.especialidade.strip()
            if payload.especialidade
            else None,
            clinica_id=clinica_id,
            ativo=True,
        )

        db.add(novo_profissional)
        db.flush()

        novo_usuario = Usuario(
            nome=payload.nome.strip(),
            email=email_normalizado,
            senha_hash=pwd_context.hash(payload.senha),
            perfil="PROFISSIONAL",
            clinica_id=clinica_id,
            profissional_id=novo_profissional.id,
            ativo=True,
        )

        db.add(novo_usuario)

        for modulo_id in modulo_ids_unicos:
            db.add(
                ProfissionalModulo(
                    profissional_id=novo_profissional.id,
                    modulo_id=modulo_id,
                )
            )

        db.commit()
        db.refresh(novo_profissional)

        return serializar_profissional(novo_profissional, db)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Não foi possível concluir o cadastro. Verifique se o e-mail ou os vínculos já existem.",
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar profissional: {e}",
        )


@router.put("/{profissional_id}", response_model=ProfissionalOut)
def atualizar_profissional(
    profissional_id: int,
    payload: ProfissionalUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    profissional = (
        db.query(Profissional)
        .filter(Profissional.id == profissional_id)
        .first()
    )

    if not profissional:
        raise HTTPException(
            status_code=404,
            detail="Profissional não encontrado",
        )

    if not is_admin_global(usuario) and usuario.clinica_id != profissional.clinica_id:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado",
        )

    if not payload.modulo_ids:
        raise HTTPException(
            status_code=400,
            detail="Selecione pelo menos um módulo de acesso.",
        )

    clinica_id = profissional.clinica_id

    if is_admin_global(usuario) and payload.clinica_id is not None:
        clinica_id = payload.clinica_id

    email_normalizado = (
        str(payload.email).strip().lower()
        if payload.email
        else None
    )

    if email_normalizado:
        profissional_email_existente = (
            db.query(Profissional)
            .filter(
                Profissional.email == email_normalizado,
                Profissional.id != profissional.id,
            )
            .first()
        )

        if profissional_email_existente:
            raise HTTPException(
                status_code=409,
                detail="Já existe outro profissional com este e-mail.",
            )

        usuario_email_existente = (
            db.query(Usuario)
            .filter(
                Usuario.email == email_normalizado,
                Usuario.profissional_id != profissional.id,
            )
            .first()
        )

        if usuario_email_existente:
            raise HTTPException(
                status_code=409,
                detail="Já existe outro usuário com este e-mail.",
            )

    modulo_ids_unicos = list(set(payload.modulo_ids))

    modulos = (
        db.query(ModuloClinico)
        .filter(
            ModuloClinico.id.in_(modulo_ids_unicos),
            ModuloClinico.ativo == True,
        )
        .all()
    )

    if len(modulos) != len(modulo_ids_unicos):
        raise HTTPException(
            status_code=400,
            detail="Um ou mais módulos informados são inválidos ou estão inativos.",
        )

    usuario_vinculado = (
        db.query(Usuario)
        .filter(Usuario.profissional_id == profissional.id)
        .first()
    )

    try:
        profissional.nome = payload.nome.strip()
        profissional.email = email_normalizado
        profissional.especialidade = (
            payload.especialidade.strip()
            if payload.especialidade
            else None
        )
        profissional.clinica_id = clinica_id
        profissional.ativo = (
            payload.ativo
            if payload.ativo is not None
            else profissional.ativo
        )

        if usuario_vinculado:
            usuario_vinculado.nome = profissional.nome
            usuario_vinculado.email = profissional.email
            usuario_vinculado.clinica_id = profissional.clinica_id
            usuario_vinculado.ativo = profissional.ativo
            usuario_vinculado.perfil = "PROFISSIONAL"

        db.query(ProfissionalModulo).filter(
            ProfissionalModulo.profissional_id == profissional.id
        ).delete(synchronize_session=False)

        for modulo_id in modulo_ids_unicos:
            db.add(
                ProfissionalModulo(
                    profissional_id=profissional.id,
                    modulo_id=modulo_id,
                )
            )

        db.commit()
        db.refresh(profissional)

        return serializar_profissional(profissional, db)

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Não foi possível atualizar o profissional. Verifique se o e-mail ou os vínculos já existem.",
        )

    except HTTPException:
        db.rollback()
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao atualizar profissional: {e}",
        )


@router.delete("/{profissional_id}")
def inativar_profissional(
    profissional_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    profissional = (
        db.query(Profissional)
        .filter(Profissional.id == profissional_id)
        .first()
    )

    if not profissional:
        raise HTTPException(
            status_code=404,
            detail="Profissional não encontrado",
        )

    if not is_admin_global(usuario) and usuario.clinica_id != profissional.clinica_id:
        raise HTTPException(
            status_code=403,
            detail="Acesso negado",
        )

    profissional.ativo = False

    usuario_vinculado = (
        db.query(Usuario)
        .filter(Usuario.profissional_id == profissional.id)
        .first()
    )

    if usuario_vinculado:
        usuario_vinculado.ativo = False

    db.commit()

    return {"ok": True}