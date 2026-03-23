import os
import subprocess
from sqlalchemy.orm import Session

from app.core.security import hash_senha
from app.database import SessionLocal
from app.models.usuario import Usuario
from app.models.clinica import Clinica


def ensure_default_clinica(db: Session) -> Clinica:
    nome = os.getenv("DEFAULT_CLINICA_NOME", "Clínica NeuroVida")
    email = os.getenv("DEFAULT_CLINICA_EMAIL")

    clinica = db.query(Clinica).filter(Clinica.nome == nome).first()
    if clinica:
        changed = False
        if clinica.ativa is False:
            clinica.ativa = True
            changed = True
        if email and not clinica.email:
            clinica.email = email
            changed = True
        if changed:
            db.commit()
            db.refresh(clinica)
        return clinica

    clinica = Clinica(nome=nome, email=email, ativa=True)
    db.add(clinica)
    db.commit()
    db.refresh(clinica)
    return clinica


def ensure_admin_user(db: Session, clinica: Clinica) -> Usuario:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@neurovida.local")
    admin_nome = os.getenv("ADMIN_NOME", "Admin NeuroVida")
    admin_senha = os.getenv("ADMIN_SENHA", "Admin@123")

    user = db.query(Usuario).filter(Usuario.email == admin_email).first()
    if user:
        changed = False

        if user.perfil != "ADMIN_CLINICA":
            user.perfil = "ADMIN_CLINICA"
            changed = True

        if user.ativo is False:
            user.ativo = True
            changed = True

        if user.clinica_id != clinica.id:
            user.clinica_id = clinica.id
            changed = True

        # opcional: força reset de senha via env
        if os.getenv("ADMIN_FORCE_RESET_PASSWORD", "false").lower() == "true":
            user.senha_hash = hash_senha(admin_senha)
            changed = True

        if changed:
            db.commit()
            db.refresh(user)

        return user

    user = Usuario(
        nome=admin_nome,
        email=admin_email,
        senha_hash=hash_senha(admin_senha),
        perfil="ADMIN_CLINICA",
        clinica_id=clinica.id,
        ativo=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def main():
    # 1) aplica migrações
    subprocess.check_call(["alembic", "upgrade", "head"])

    # 2) seed idempotente
    db = SessionLocal()
    try:
        clinica = ensure_default_clinica(db)
        ensure_admin_user(db, clinica)
    finally:
        db.close()


if __name__ == "__main__":
    main()
