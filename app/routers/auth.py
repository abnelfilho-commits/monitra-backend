from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.usuario import Usuario
from app.core.security import verificar_senha, criar_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])

@router.post("/login", include_in_schema=True)
@router.post("/login/", include_in_schema=False)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    email = form_data.username
    senha = form_data.password

    user = db.query(Usuario).filter(Usuario.email == email).first()
    if not user or not verificar_senha(senha, user.senha_hash):
        raise HTTPException(status_code=401, detail="Credenciais inválidas")

    token = criar_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}
