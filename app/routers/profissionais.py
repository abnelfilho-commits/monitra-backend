from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models.profissional import Profissional
from app.models.usuario import Usuario
from app.schemas.profissional import ProfissionalCreate, ProfissionalOut, ProfissionalUpdate

router = APIRouter(
    prefix="/profissionais",
    tags=["Profissionais"],
)


@router.get("/", response_model=list[ProfissionalOut])
def listar_profissionais(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    q = db.query(Profissional).filter(Profissional.ativo == True)

    if usuario.perfil != "admin":
        if usuario.clinica_id is None:
            raise HTTPException(status_code=403, detail="Usuário sem clínica vinculada")
        q = q.filter(Profissional.clinica_id == usuario.clinica_id)

    return q.order_by(Profissional.nome.asc()).all()


@router.get("/clinica/{clinica_id}", response_model=list[ProfissionalOut])
def listar_profissionais_por_clinica(
    clinica_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    if usuario.perfil != "admin" and usuario.clinica_id != clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return (
        db.query(Profissional)
        .filter(
            Profissional.clinica_id == clinica_id,
            Profissional.ativo == True,
        )
        .order_by(Profissional.nome.asc())
        .all()
    )


@router.get("/{profissional_id}", response_model=ProfissionalOut)
def obter_profissional(
    profissional_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    profissional = db.query(Profissional).filter(Profissional.id == profissional_id).first()
    if not profissional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    if usuario.perfil != "admin" and usuario.clinica_id != profissional.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    return profissional


@router.post("/", response_model=ProfissionalOut, status_code=status.HTTP_201_CREATED)
def criar_profissional(
    payload: ProfissionalCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    data = payload.dict()

    if usuario.perfil != "admin":
        if usuario.clinica_id is None:
            raise HTTPException(status_code=403, detail="Usuário sem clínica vinculada")
        data["clinica_id"] = usuario.clinica_id

    novo = Profissional(**data)
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return novo


@router.put("/{profissional_id}", response_model=ProfissionalOut)
def atualizar_profissional(
    profissional_id: int,
    payload: ProfissionalUpdate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    profissional = db.query(Profissional).filter(Profissional.id == profissional_id).first()
    if not profissional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    if usuario.perfil != "admin" and usuario.clinica_id != profissional.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    profissional.nome = payload.nome
    profissional.email = payload.email
    profissional.especialidade = payload.especialidade
    if usuario.perfil == "admin":
        profissional.clinica_id = payload.clinica_id
    profissional.ativo = payload.ativo if payload.ativo is not None else profissional.ativo

    db.commit()
    db.refresh(profissional)
    return profissional


@router.delete("/{profissional_id}")
def inativar_profissional(
    profissional_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    profissional = db.query(Profissional).filter(Profissional.id == profissional_id).first()
    if not profissional:
        raise HTTPException(status_code=404, detail="Profissional não encontrado")

    if usuario.perfil != "admin" and usuario.clinica_id != profissional.clinica_id:
        raise HTTPException(status_code=403, detail="Acesso negado")

    profissional.ativo = False
    db.commit()
    return {"ok": True}
