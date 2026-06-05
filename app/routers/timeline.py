from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db

router = APIRouter(
    prefix="/timeline",
    tags=["Timeline"]
)

@router.get("/pacientes/{paciente_id}")
def obter_timeline_paciente(
    paciente_id: int,
    db: Session = Depends(get_db)
):
    rows = db.execute(
        text("""
            SELECT
                id,
                paciente_id,
                tipo_evento,
                data,
                descricao,
                origem,
                sono_qualidade,
                irritabilidade,
                crise_sensorial
            FROM vw_timeline_paciente
            WHERE paciente_id = :paciente_id
            AND tipo_evento != 'REGISTRO_CARDIO'
            ORDER BY data DESC
        """),
        {"paciente_id": paciente_id}
    ).fetchall()

    return [
        {
            "id": r.id,
            "paciente_id": r.paciente_id,
            "tipo_evento": r.tipo_evento,
            "data": r.data,
            "descricao": r.descricao,
            "origem": r.origem,
            "sono_qualidade": r.sono_qualidade,
            "irritabilidade": r.irritabilidade,
            "crise_sensorial": r.crise_sensorial,
        }
        for r in rows
    ]

listar_timeline_paciente = obter_timeline_paciente
