from fastapi import APIRouter, Depends
from app.core.deps import get_usuario_atual
from app.models.usuario import Usuario

from app.database import SessionLocal
from app.models.profissional import Profissional
from app.models.modular import ModuloClinico
from app.models.profissional_modulo import ProfissionalModulo

router = APIRouter()


@router.get("/me")
def me(usuario_atual: Usuario = Depends(get_usuario_atual)):
    db = SessionLocal()

    modulos = []

    if usuario_atual.perfil == "PROFISSIONAL" and usuario_atual.profissional_id:

        modulos_db = (
            db.query(ModuloClinico)
            .join(
                ProfissionalModulo,
                ProfissionalModulo.modulo_id == ModuloClinico.id
            )
            .filter(
                ProfissionalModulo.profissional_id == usuario_atual.profissional_id
            )
            .filter(ModuloClinico.ativo == True)
            .all()
        )

        modulos = [
            {
                "id": m.id,
                "nome": m.nome,
                "slug": m.slug
            }
            for m in modulos_db
        ]

    else:
        modulos_db = (
            db.query(ModuloClinico)
            .filter(ModuloClinico.ativo == True)
            .all()
        )

        modulos = [
            {
                "id": m.id,
                "nome": m.nome,
                "slug": m.slug
            }
            for m in modulos_db
        ]

    return {
        "id": usuario_atual.id,
        "nome": usuario_atual.nome,
        "email": usuario_atual.email,
        "perfil": usuario_atual.perfil,
        "clinica_id": usuario_atual.clinica_id,
        "clinica_nome": usuario_atual.clinica.nome if usuario_atual.clinica else None,
        "profissional_id": usuario_atual.profissional_id,
        "modulos": modulos
    }

