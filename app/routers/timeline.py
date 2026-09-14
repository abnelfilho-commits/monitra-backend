from app.services.timeline_service import TimelineService
from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db

from app.services.longitudinal.service import longitudinal_service

from app.services.timeline_event_service import (
    TimelineEventService,
)

def iso_timestamp_utc(valor):
    """
    Normaliza timestamps técnicos da aplicação para UTC explícito.

    Timestamps sem timezone são tratados como UTC, pois foram
    gerados pelo servidor/banco nesse padrão.
    """
    if valor is None:
        return None

    if not isinstance(valor, datetime):
        valor = datetime.combine(valor, time.min)

    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)

    return valor.astimezone(timezone.utc).isoformat()

router = APIRouter(
    prefix="/timeline",
    tags=["Timeline"]
)


@router.get("/pacientes/{paciente_id}")
def obter_timeline_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    return TimelineService.get_neuro_legacy_timeline(db, paciente_id)


listar_timeline_paciente = obter_timeline_paciente

@router.get("/eventos/{tipo}/{evento_id}")
def visualizar_evento(
    tipo: str,
    evento_id: int,
    db: Session = Depends(get_db)
):
    return longitudinal_service.visualizar(
        db,
        tipo,
        evento_id
    )
