from fastapi import Depends, HTTPException

from app.core.deps import get_usuario_atual


def exigir_admin(usuario=Depends(get_usuario_atual)):
    if usuario.perfil != "ADMIN":
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito ao administrador."
        )

    return usuario


def exigir_admin_ou_profissional(usuario=Depends(get_usuario_atual)):
    if usuario.perfil not in ["ADMIN", "PROFISSIONAL", "ADMIN_CLINICA"]:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito."
        )

    return usuario


def exigir_visualizacao(usuario=Depends(get_usuario_atual)):
    if usuario.perfil not in ["ADMIN", "PROFISSIONAL", "ADMIN_CLINICA", "SUPORTE"]:
        raise HTTPException(
            status_code=403,
            detail="Acesso restrito."
        )

    return usuario