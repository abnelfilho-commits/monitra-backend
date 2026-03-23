from fastapi import APIRouter, Depends
from app.core.deps import get_usuario_atual
from app.models.usuario import Usuario

router = APIRouter(tags=["Auth"])

@router.get("/me")
def me(usuario: Usuario = Depends(get_usuario_atual)):
    return {
        "id": usuario.id,
        "nome": usuario.nome,
        "email": usuario.email,
        "perfil": usuario.perfil,
        "clinica_id": usuario.clinica_id,
        "ativo": usuario.ativo,
    }

