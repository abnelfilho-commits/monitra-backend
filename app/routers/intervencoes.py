from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.core.deps import get_usuario_atual
from app.core.acl import assert_clinica_access

from app.models.usuario import Usuario
from app.models.paciente import Paciente
from app.models.intervencao import Intervencao

# Ajuste o import conforme seu projeto (você mencionou app.schemas)
# Ex: from app.schemas import IntervencaoCreate
from app.schemas.intervencao import IntervencaoCreate

router = APIRouter(
    prefix="/intervencoes",
    tags=["Intervenções"],
)

@router.post("/")
def criar_intervencao(
    intervencao: IntervencaoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == intervencao.paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    assert_clinica_access(usuario, paciente.clinica_id)

    data = intervencao.dict()
    data["profissional_id"] = usuario.id  # trava no usuário logado

    nova = Intervencao(**data)
    db.add(nova)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Dados inválidos para criar intervenção")

    db.refresh(nova)
    return nova


@router.get("/paciente/{paciente_id}")
def listar_por_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado")

    assert_clinica_access(usuario, paciente.clinica_id)

    return (
        db.query(Intervencao)
        .filter(Intervencao.paciente_id == paciente_id)
        .order_by(Intervencao.data_intervencao.desc())
        .all()
    )

@router.get("/{intervencao_id}")
def obter_intervencao(
    intervencao_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    intervencao = (
        db.query(Intervencao)
        .filter(Intervencao.id == intervencao_id)
        .first()
    )
    if not intervencao:
        raise HTTPException(status_code=404, detail="Intervenção não encontrada.")

    return intervencao
@router.put("/{intervencao_id}")
def atualizar_intervencao(
    intervencao_id: int,
    payload: IntervencaoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(get_usuario_atual),
):
    intervencao = (
        db.query(Intervencao)
        .filter(Intervencao.id == intervencao_id)
        .first()
    )
    if not intervencao:
        raise HTTPException(status_code=404, detail="Intervenção não encontrada.")

    paciente = db.query(Paciente).filter(Paciente.id == payload.paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    intervencao.paciente_id = payload.paciente_id
    intervencao.tipo = payload.tipo
    intervencao.descricao = payload.descricao
    intervencao.data_intervencao = payload.data_intervencao

    # mantém o profissional logado como responsável pela edição/registro
    if hasattr(intervencao, "profissional_id"):
        intervencao.profissional_id = usuario.id

    db.commit()
    db.refresh(intervencao)
    return intervencao

@router.delete("/{intervencao_id}")
def excluir_intervencao(
    intervencao_id: int,
    db: Session = Depends(get_db),
    usuario = Depends(get_usuario_atual),
):
    intervencao = db.query(Intervencao).filter(Intervencao.id == intervencao_id).first()
    if not intervencao:
        raise HTTPException(status_code=404, detail="Intervenção não encontrada.")

    db.delete(intervencao)
    db.commit()
    return {"ok": True}
