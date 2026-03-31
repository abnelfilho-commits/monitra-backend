from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models import Paciente, Intervencao, RegistroDiario  # ajuste imports conforme seu projeto

router = APIRouter(tags=["Timeline"])


TipoEvento = Literal["INTERVENCAO", "REGISTRO_DIARIO"]


class TimelineItemOut(BaseModel):
    id: int
    paciente_id: int
    tipo_evento: TipoEvento
    data: datetime
    descricao: str
    usuario_id: Optional[int] = None
    origem: Optional[str] = None


@router.get(
    "/pacientes/{paciente_id}/timeline",
    response_model=List[TimelineItemOut],
)
def listar_timeline_paciente(
    paciente_id: int,
    db: Session = Depends(get_db),
    usuario_atual=Depends(get_usuario_atual),
):
    paciente = db.query(Paciente).filter(Paciente.id == paciente_id).first()
    if not paciente:
        raise HTTPException(status_code=404, detail="Paciente não encontrado.")

    # ==========================================
    # ACL / regra de acesso
    # ==========================================
    # Se o seu projeto já tem validação por clínica, mantenha aqui.
    # Exemplo:
    #
    # if not getattr(usuario_atual, "is_admin", False):
    #     if getattr(usuario_atual, "clinica_id", None) != paciente.clinica_id:
    #         raise HTTPException(
    #             status_code=403,
    #             detail="Usuário sem permissão para acessar este paciente."
    #         )

    sql = text("""
        SELECT
            id,
            paciente_id,
            tipo_evento,
            data,
            descricao,
            usuario_id,
            origem
        FROM vw_timeline_paciente
        WHERE paciente_id = :paciente_id
        ORDER BY data DESC, id DESC
    """)

    rows = db.execute(sql, {"paciente_id": paciente_id}).mappings().all()

    items = [
        TimelineItemOut(
            id=row["id"],
            paciente_id=row["paciente_id"],
            tipo_evento=row["tipo_evento"],
            data=row["data"],
            descricao=row["descricao"],
            usuario_id=row.get("usuario_id"),
            origem=row.get("origem"),
        )
        for row in rows
    ]

    return items
