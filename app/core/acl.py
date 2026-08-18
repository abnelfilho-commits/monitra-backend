from fastapi import HTTPException
from app.models.usuario import Usuario

from typing import Optional

def assert_clinica_access(usuario: Usuario, resource_clinica_id: Optional[int]):
    if str(usuario.perfil).upper() == "ADMIN":
        return

    # Usuário comum precisa estar vinculado a uma clínica
    if usuario.clinica_id is None:
        raise HTTPException(status_code=403, detail="Usuário sem clínica vinculada")

    # Recurso precisa pertencer à mesma clínica
    if resource_clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado (clínica diferente)")

def is_admin(usuario) -> bool:
    perfil = (usuario.perfil or "").strip().upper()
    return perfil in {"ADMIN", "ADMIN_CLINICA", "ADMINISTRADOR"}

def is_admin_global(usuario) -> bool:
    perfil = (usuario.perfil or "").strip().upper()
    return perfil in {"ADMIN", "ADMINISTRADOR"}