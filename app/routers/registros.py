from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.registro import RegistroDiario
from app.services.care_lines.access import authorized_patient
from app.schemas.registro import RegistroDiarioCreate, RegistroDiarioOut

router = APIRouter(
    prefix="/registros",
    tags=["Registros Diários"],
    dependencies=[Depends(get_usuario_atual)],
)


def _unavailable():
    return HTTPException(status_code=404, detail="Registro não disponível.")


def _authorize(db, usuario, paciente_id, *, write=False):
    # Queries must not flush pending state while deciding access.
    with db.no_autoflush:
        try:
            authorized_patient(db, usuario, paciente_id, "NEURO", write=write)
        except HTTPException as exc:
            if exc.status_code in (400, 403, 404):
                raise _unavailable() from None
            raise


def _record(db, usuario, registro_id, *, write=False):
    with db.no_autoflush:
        identity = db.query(RegistroDiario.id, RegistroDiario.paciente_id).filter(
            RegistroDiario.id == registro_id).first()
        if identity is None:
            raise _unavailable()
        _authorize(db, usuario, identity.paciente_id, write=write)
        return db.query(RegistroDiario).filter(RegistroDiario.id == identity.id).first()


@router.post("/", response_model=RegistroDiarioOut, status_code=status.HTTP_201_CREATED)
def criar_registro(
    registro: RegistroDiarioCreate,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    _authorize(db, usuario, registro.paciente_id, write=True)

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
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    _authorize(db, usuario, paciente_id)

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
    usuario=Depends(get_usuario_atual),
):
    existente = _record(db, usuario, registro_id, write=True)
    if registro.paciente_id != existente.paciente_id:
        raise _unavailable()

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
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    return _record(db, usuario, registro_id)

@router.delete("/{registro_id}")
def excluir_registro(
    registro_id: int,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    registro = _record(db, usuario, registro_id, write=True)

    db.delete(registro)
    db.commit()
    return {"ok": True}
