"""Legacy HTTP contracts over the institutional Care Plan boundary."""
from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.schemas.pts import (PTSCreate, PTSResponse, PTSObjetivoCreate,
                             PTSObjetivoResponse, PTSObjetivoUpdate)
from app.services.care_plan_service import CarePlanService, call

router = APIRouter(prefix="/pts", tags=["PTS"])
service = CarePlanService()

@router.post("", response_model=PTSResponse)
def criar_pts(payload: PTSCreate, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.create(db, payload, usuario))

@router.get("/paciente/{paciente_id}", response_model=list[PTSResponse])
def listar_pts_paciente(paciente_id: int, modulo_id: Optional[int] = None,
                        db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.list_plans(db, paciente_id, usuario, modulo_id))

@router.post("/{pts_id}/objetivos", response_model=PTSObjetivoResponse)
def criar_objetivo_pts(pts_id: int, payload: PTSObjetivoCreate,
                       db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.create_objective(db, pts_id, payload, usuario))

@router.get("/{pts_id}/objetivos", response_model=list[PTSObjetivoResponse])
def listar_objetivos_pts(pts_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.list_objectives(db, pts_id, usuario))

@router.put("/objetivos/{objetivo_id}", response_model=PTSObjetivoResponse)
def atualizar_objetivo_pts(objetivo_id: int, payload: PTSObjetivoUpdate,
                           db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.update_objective(db, objetivo_id, payload, usuario))

@router.put("/{pts_id}/encerrar", response_model=PTSResponse)
def encerrar_pts(pts_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.set_closed(db, pts_id, usuario, True))

@router.put("/{pts_id}/reabrir", response_model=PTSResponse)
def reabrir_pts(pts_id: int, db: Session = Depends(get_db), usuario=Depends(get_usuario_atual)):
    return call(lambda: service.set_closed(db, pts_id, usuario, False))
