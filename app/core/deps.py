from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.models.responsavel import Responsavel
from app.core.security import SECRET_KEY, ALGORITHM

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login/")
oauth2_scheme_responsavel = OAuth2PasswordBearer(tokenUrl="/auth/responsavel/login")


def get_usuario_atual(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
):
    cred_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não autenticado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        sub = payload.get("sub")
        if not sub:
            raise cred_exc
        user_id = int(sub)
    except (JWTError, ValueError, TypeError):
        raise cred_exc

    usuario = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not usuario or not usuario.ativo:
        raise cred_exc

    return usuario


def get_responsavel_atual(
    token: str = Depends(oauth2_scheme_responsavel),
    db: Session = Depends(get_db),
) -> Responsavel:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais do responsável.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        sub = payload.get("sub")
        tipo = payload.get("tipo")

        if not sub or tipo != "responsavel":
            raise credentials_exception

        responsavel_id = int(sub)

    except (JWTError, ValueError, TypeError):
        raise credentials_exception

    responsavel = (
        db.query(Responsavel)
        .filter(
            Responsavel.id == responsavel_id,
            Responsavel.ativo == True,
        )
        .first()
    )

    if not responsavel:
        raise credentials_exception

    return responsavel
