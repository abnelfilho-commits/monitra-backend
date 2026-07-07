from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.usuario import Usuario
from app.core.permissoes import exigir_admin

router = APIRouter(
    prefix="/usuarios",
    tags=["Usuários"],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -------- SCHEMAS --------
class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    perfil: str = "PROFISSIONAL"
    clinica_id: Optional[int] = None


class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[EmailStr] = None
    perfil: Optional[str] = None
    clinica_id: Optional[int] = None
    ativo: Optional[bool] = None


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: str
    perfil: str
    clinica_id: Optional[int] = None
    ativo: bool

    class Config:
        from_attributes = True


# -------- ENDPOINTS --------
@router.post("/", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    usuario: UsuarioCreate,
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
):
    senha_bytes = usuario.senha.encode("utf-8")

    if len(senha_bytes) > 72:
        raise HTTPException(
            status_code=400,
            detail="Senha muito longa (máx 72 bytes).",
        )

    try:
        novo = Usuario(
            nome=usuario.nome,
            email=usuario.email,
            senha_hash=pwd_context.hash(usuario.senha),
            perfil=usuario.perfil,
            clinica_id=usuario.clinica_id,
            ativo=True,
        )

        db.add(novo)
        db.commit()
        db.refresh(novo)

        return novo

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="E-mail já cadastrado.",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar usuário: {e}",
        )


@router.get("/", response_model=list[UsuarioOut])
def listar_usuarios(
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
):
    return (
        db.query(Usuario)
        .order_by(Usuario.nome.asc())
        .all()
    )


@router.get("/{usuario_id}", response_model=UsuarioOut)
def obter_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
):
    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == usuario_id)
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado.",
        )

    return usuario


@router.put("/{usuario_id}", response_model=UsuarioOut)
def atualizar_usuario(
    usuario_id: int,
    dados: UsuarioUpdate,
    db: Session = Depends(get_db),
    admin=Depends(exigir_admin),
):
    usuario = (
        db.query(Usuario)
        .filter(Usuario.id == usuario_id)
        .first()
    )

    if not usuario:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado.",
        )

    payload = dados.model_dump(exclude_unset=True)

    try:
        for campo, valor in payload.items():
            setattr(usuario, campo, valor)

        db.commit()
        db.refresh(usuario)

        return usuario

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="E-mail já cadastrado.",
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao atualizar usuário: {e}",
        )