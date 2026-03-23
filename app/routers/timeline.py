from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models import Paciente, Intervencao, RegistroDiario  # ajuste imports conforme seu projeto


router = APIRouter(tags=["Timeline"])


TipoEvento = Literal["INTERVENCAO", "REGISTRO_DIARIO"]


class TimelineItemOut(BaseModel):
    id: int
    tipo_evento: TipoEvento
    data: datetime
    descricao: str
    usuario_id: Optional[int] = None


@router.get("/pacientes/{paciente_id}/timeline", response_model=List[TimelineItemOut])
def listar_timeline_por_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_usuario_atual),
):
    # 1) valida paciente
    paciente = db.get(Paciente, paciente_id)
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    # 2) (futuro) isolamento por clinica
    # if paciente.clinica_id != user.clinica_id:
    #     raise HTTPException(status_code=403, detail="Acesso negado.")

    items: list[TimelineItemOut] = []

    # --- Intervenções
    intervencoes = db.execute(
        select(Intervencao).where(Intervencao.paciente_id == paciente_id)
    ).scalars().all()

    for itv in intervencoes:
        dt = getattr(itv, "data_intervencao", None) or getattr(itv, "data", None) or datetime.min
        desc = (
            getattr(itv, "descricao", None)
            or getattr(itv, "observacao", None)
            or getattr(itv, "texto", None)
            or "Intervenção registrada"
        )
        items.append(
            TimelineItemOut(
                id=itv.id,
                tipo_evento="INTERVENCAO",
                data=itv.data_intervencao,
                descricao=itv.descricao or f"Intervenção: {itv.tipo}",
                usuario_id=getattr(itv, "profissional_id", None),
            )       
        )
    # --- Registros diários (opcional)
    registros = db.execute(
        select(RegistroDiario).where(RegistroDiario.paciente_id == paciente_id)
    ).scalars().all()

    for rg in registros:
        dt = getattr(rg, "data_registro", None) or getattr(rg, "data", None) or datetime.min
        desc = (
            getattr(rg, "descricao", None)
            or getattr(rg, "texto", None)
            or "Registro diário"
        )
        items.append(
            TimelineItemOut(
                id=rg.id,
                tipo_evento="REGISTRO_DIARIO",
                data=dt,
                descricao=desc,
                usuario_id=getattr(rg, "usuario_id", None),
            )
        )

    items.sort(key=lambda x: x.data or datetime.min, reverse=True)
    return items
