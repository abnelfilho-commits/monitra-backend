from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.registro import RegistroDiario
from app.models.paciente import Paciente
from app.schemas.registro import RegistroDiarioCreate, RegistroDiarioOut

router = APIRouter(
    prefix="/registros",
    tags=["Registros Diários"],
    dependencies=[Depends(get_usuario_atual)],
)


@router.post("/", response_model=RegistroDiarioOut, status_code=status.HTTP_201_CREATED)
def criar_registro(
    registro: RegistroDiarioCreate,
    db: Session = Depends(get_db)
):
    paciente = db.query(Paciente).filter(Paciente.id == registro.paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    novo = RegistroDiario(
        paciente_id=registro.paciente_id,
        data=registro.data,
        sono_qualidade=registro.sono_qualidade,
        evacuacao=registro.evacuacao,
        consistencia_fezes=registro.consistencia_fezes,
        irritabilidade=registro.irritabilidade,
        crise_sensorial=registro.crise_sensorial,
        observacao=registro.observacao,
        alimentacao=registro.alimentacao,
    )

    db.add(novo)
    try:
        db.commit()
        db.refresh(novo)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe registro para este paciente nesta data."
        )

    return novo


@router.get("/paciente/{paciente_id}", response_model=list[RegistroDiarioOut])
def listar_registros(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    registros = (
        db.query(RegistroDiario)
        .filter(RegistroDiario.paciente_id == paciente_id)
        .order_by(RegistroDiario.data.desc())
        .all()
    )
    return registros

@router.put("/{registro_id}", response_model=RegistroDiarioOut)
def atualizar_registro(
    registro_id: int,
    registro: RegistroDiarioCreate,
    db: Session = Depends(get_db),
):
    existente = (
        db.query(RegistroDiario)
        .filter(RegistroDiario.id == registro_id)
        .first()
    )
    if not existente:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    paciente = db.query(Paciente).filter(Paciente.id == registro.paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    existente.paciente_id = registro.paciente_id
    existente.data = registro.data
    existente.sono_qualidade = registro.sono_qualidade
    existente.evacuacao = registro.evacuacao
    existente.consistencia_fezes = registro.consistencia_fezes
    existente.irritabilidade = registro.irritabilidade
    existente.crise_sensorial = registro.crise_sensorial
    existente.observacao = registro.observacao
    existente.alimentacao = registro.alimentacao

    try:
        db.commit()
        db.refresh(existente)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Já existe registro para este paciente nesta data."
        )

    return existente

@router.get("/{registro_id}", response_model=RegistroDiarioOut)
def obter_registro(
    registro_id: int,
    db: Session = Depends(get_db)
):
    registro = (
        db.query(RegistroDiario)
        .filter(RegistroDiario.id == registro_id)
        .first()
    )
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    return registro

@router.delete("/{registro_id}")
def excluir_registro(
    registro_id: int,
    db: Session = Depends(get_db)
):
    registro = db.query(RegistroDiario).filter(RegistroDiario.id == registro_id).first()
    if not registro:
        raise HTTPException(status_code=404, detail="Registro não encontrado.")

    db.delete(registro)
    db.commit()
    return {"ok": True}
