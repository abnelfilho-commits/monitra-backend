import os
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.usuario import Usuario
from app.core.security import hash_senha


def main() -> None:
    admin_email = os.getenv("ADMIN_EMAIL", "admin@sentinela.com")
    admin_senha = os.getenv("ADMIN_SENHA", "Senha@123")
    admin_nome = os.getenv("ADMIN_NOME", "Admin Sistema")
    admin_perfil = os.getenv("ADMIN_PERFIL", "ADMIN_CLINICA")

    db: Session = SessionLocal()
    try:
        existente = db.query(Usuario).filter(Usuario.email == admin_email).first()
        if existente:
            print("OK: admin já existe (seed idempotente).")
            return

        admin = Usuario(
            nome=admin_nome,
            email=admin_email,
            senha_hash=hash_senha(admin_senha),
            perfil=admin_perfil,
            clinica_id=None,
            ativo=True,
        )
        db.add(admin)
        db.commit()
        print("OK: admin criado.")
    finally:
        db.close()


if __name__ == "__main__":
    main()

