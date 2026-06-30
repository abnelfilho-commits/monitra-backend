from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db

router = APIRouter(
    prefix="/dimensionamento",
    tags=["Dimensionamento"]
)


@router.get("/ocupacoes")
def listar_dimensionamento_ocupacoes(
    modulo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db)
):
    resultado = db.execute(text("""
        SELECT
            modulo_id,
            ocupacao_id,
            ocupacao_nome,
            total_planejamentos,
            minutos_semanais,
            horas_semanais,
            horas_mensais,
            horas_anuais,
            ROUND(horas_semanais / 40.0, 2) AS fte
        FROM vw_dimensionamento_ocupacao
        WHERE (:modulo_id IS NULL OR modulo_id = :modulo_id)
        ORDER BY horas_semanais DESC
    """), {
        "modulo_id": modulo_id
    }).mappings().all()

    return list(resultado)