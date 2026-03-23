from fastapi import HTTPException
from app.models.usuario import Usuario

from typing import Optional

def assert_clinica_access(usuario: Usuario, resource_clinica_id: Optional[int]):
    # Admin vê tudo
    if usuario.perfil == "admin":
        return

    # Usuário comum precisa estar vinculado a uma clínica
    if usuario.clinica_id is None:
        raise HTTPException(status_code=403, detail="Usuário sem clínica vinculada")

    # Recurso precisa pertencer à mesma clínica
    if resource_clinica_id != usuario.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado (clínica diferente)")
