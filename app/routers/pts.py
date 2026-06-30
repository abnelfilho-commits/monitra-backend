from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.pts import PTS, PTSObjetivo
from app.schemas.pts import (
    PTSCreate,
    PTSResponse,
    PTSObjetivoCreate,
    PTSObjetivoResponse,
    PTSObjetivoUpdate,
)

router = APIRouter(
    prefix="/pts",
    tags=["PTS"]
)

@router.post("", response_model=PTSResponse)
def criar_pts(
    payload: PTSCreate,
    db: Session = Depends(get_db)
):
    pts_ativo = (
        db.query(PTS)
        .filter(
            PTS.paciente_id == payload.paciente_id,
            PTS.modulo_id == payload.modulo_id,
            PTS.status == "ATIVO"
        )
        .first()
    )

    if pts_ativo:
        raise HTTPException(
            status_code=400,
            detail="Já existe um PTS ativo para este paciente."
        )

    pts = PTS(
        paciente_id=payload.paciente_id,
        modulo_id=payload.modulo_id,
        data_inicio=payload.data_inicio,
        objetivo_geral=payload.objetivo_geral,
        observacoes=payload.observacoes,
    )

    db.add(pts)
    db.commit()
    db.refresh(pts)

    return pts

@router.get(
    "/paciente/{paciente_id}",
    response_model=list[PTSResponse]
)
def listar_pts_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    return (
        db.query(PTS)
        .filter(
            PTS.paciente_id == paciente_id
        )
        .order_by(
            PTS.id.desc()
        )
        .all()
    )

@router.post(
    "/{pts_id}/objetivos",
    response_model=PTSObjetivoResponse
)
def criar_objetivo_pts(
    pts_id: int,
    payload: PTSObjetivoCreate,
    db: Session = Depends(get_db)
):
    pts = db.query(PTS).filter(PTS.id == pts_id).first()

    if not pts:
        raise HTTPException(
            status_code=404,
            detail="PTS não encontrado."
        )

    objetivo = PTSObjetivo(
        pts_id=pts_id,
        descricao=payload.descricao,
        prioridade=payload.prioridade,
    )

    db.add(objetivo)
    db.commit()
    db.refresh(objetivo)

    return objetivo


@router.get(
    "/{pts_id}/objetivos",
    response_model=list[PTSObjetivoResponse]
)
def listar_objetivos_pts(
    pts_id: int,
    db: Session = Depends(get_db)
):
    pts = db.query(PTS).filter(PTS.id == pts_id).first()

    if not pts:
        raise HTTPException(
            status_code=404,
            detail="PTS não encontrado."
        )

    return (
        db.query(PTSObjetivo)
        .filter(PTSObjetivo.pts_id == pts_id)
        .order_by(PTSObjetivo.id.asc())
        .all()
    )


@router.put(
    "/objetivos/{objetivo_id}",
    response_model=PTSObjetivoResponse
)
def atualizar_objetivo_pts(
    objetivo_id: int,
    payload: PTSObjetivoUpdate,
    db: Session = Depends(get_db)
):
    objetivo = (
        db.query(PTSObjetivo)
        .filter(PTSObjetivo.id == objetivo_id)
        .first()
    )

    if not objetivo:
        raise HTTPException(
            status_code=404,
            detail="Objetivo do PTS não encontrado."
        )

    if payload.descricao is not None:
        objetivo.descricao = payload.descricao

    if payload.prioridade is not None:
        objetivo.prioridade = payload.prioridade

    if payload.status is not None:
        objetivo.status = payload.status

    db.commit()
    db.refresh(objetivo)

    return objetivo

@router.put("/{pts_id}/encerrar", response_model=PTSResponse)
def encerrar_pts(
    pts_id: int,
    db: Session = Depends(get_db)
):
    pts = db.query(PTS).filter(PTS.id == pts_id).first()

    if not pts:
        raise HTTPException(status_code=404, detail="PTS não encontrado.")

    pts.status = "ENCERRADO"
    pts.data_fim = date.today()

    db.commit()
    db.refresh(pts)

    return pts

@router.put("/{pts_id}/reabrir", response_model=PTSResponse)
def reabrir_pts(
    pts_id: int,
    db: Session = Depends(get_db)
):
    pts = db.query(PTS).filter(PTS.id == pts_id).first()

    if not pts:
        raise HTTPException(status_code=404, detail="PTS não encontrado.")

    pts_ativo = (
        db.query(PTS)
        .filter(
            PTS.paciente_id == pts.paciente_id,
            PTS.modulo_id == pts.modulo_id,
            PTS.status == "ATIVO",
            PTS.id != pts.id
        )
        .first()
    )

    if pts_ativo:
        raise HTTPException(
            status_code=400,
            detail="Já existe outro PTS ativo para este paciente."
        )

    pts.status = "ATIVO"
    pts.data_fim = None

    db.commit()
    db.refresh(pts)

    return pts