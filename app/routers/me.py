from fastapi import APIRouter, Depends
from app.core.deps import get_usuario_atual
from app.models.usuario import Usuario

router = APIRouter()

@router.get("/me")
def me(usuario_atual: Usuario = Depends(get_usuario_atual)):
    return {
        "id": usuario_atual.id,
        "nome": usuario_atual.nome,
        "email": usuario_atual.email,
        "perfil": usuario_atual.perfil,
        "clinica_id": usuario_atual.clinica_id,
        "clinica_nome": usuario_atual.clinica.nome if usuario_atual.clinica else None,
    }

