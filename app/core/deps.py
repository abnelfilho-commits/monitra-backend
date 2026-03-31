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

    if hasattr(usuario, "ativo") and not usuario.ativo:
        raise HTTPException(status_code=403, detail="Usuário inativo")

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

        if sub is None or tipo != "responsavel":
            raise credentials_exception

        responsavel = (
            db.query(Responsavel)
            .filter(Responsavel.id == int(sub))
            .first()
        )

        if responsavel is None:
            raise credentials_exception

    except (JWTError, ValueError):
        raise credentials_exception

    if not responsavel.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Responsável inativo."
        )

    return responsavel
