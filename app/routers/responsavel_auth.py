from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.responsavel import Responsavel
from app.schemas.responsavel import ResponsavelMeOut
from app.core.security import verificar_senha, criar_access_token
from app.core.deps import get_responsavel_atual

router = APIRouter(
    prefix="/auth/responsavel",
    tags=["Auth Responsável"]
)


@router.post("/login")
def login_responsavel(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    responsavel = (
        db.query(Responsavel)
        .filter(Responsavel.email == form_data.username)
        .first()
    )

    if not responsavel or not verificar_senha(form_data.password, responsavel.senha_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not responsavel.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Responsável inativo."
        )

    access_token = criar_access_token(
        data={
            "sub": str(responsavel.id),
            "tipo": "responsavel",
        }
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "responsavel": {
            "id": responsavel.id,
            "nome": responsavel.nome,
            "email": responsavel.email,
        },

    }


@router.get("/me", response_model=ResponsavelMeOut)
def me_responsavel(
    responsavel: Responsavel = Depends(get_responsavel_atual),
):
    return responsavel
