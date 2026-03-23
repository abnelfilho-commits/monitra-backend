from fastapi import APIRouter, Depends, HTTPException, status
from app.core.deps import get_usuario_atual
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models.usuario import Usuario

router = APIRouter(
    prefix="/usuarios",
    tags=["Usuários"],
    dependencies=[Depends(get_usuario_atual)],
)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# -------- SCHEMAS --------
class UsuarioCreate(BaseModel):
    nome: str
    email: EmailStr
    senha: str
    perfil: str = "PROFISSIONAL"  # ADMIN_CLINICA | PROFISSIONAL | RESPONSAVEL
    clinica_id: Optional[int] = None


class UsuarioOut(BaseModel):
    id: int
    nome: str
    email: EmailStr
    perfil: str
    clinica_id: Optional[int] = None
    ativo: bool

    class Config:
        from_attributes = True  # pydantic v2 (ou orm_mode=True no v1)


# -------- ENDPOINT --------
@router.post("/", response_model=UsuarioOut, status_code=status.HTTP_201_CREATED)
def criar_usuario(usuario: UsuarioCreate, db: Session = Depends(get_db)):

    # ✅ validar senha ANTES do hash (bcrypt limita 72 bytes)
    senha_bytes = usuario.senha.encode("utf-8")
    if len(senha_bytes) > 72:
        raise HTTPException(
            status_code=400,
            detail="Senha muito longa (máx 72 bytes)")
    try:
        novo = Usuario(
            nome=usuario.nome,
            email=usuario.email,
            senha_hash=pwd_context.hash(usuario.senha),
            perfil=usuario.perfil,
            clinica_id=usuario.clinica_id,
       )
        db.add(novo)
        db.commit()
        db.refresh(novo)
        return novo

    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="E-mail já cadastrado.")

    except Exception as e:
        db.rollback()
        # melhor não vazar erro interno em produção; mas por enquanto ajuda
        raise HTTPException(status_code=500, detail=f"Erro ao criar usuário: {e}")

    return novo
