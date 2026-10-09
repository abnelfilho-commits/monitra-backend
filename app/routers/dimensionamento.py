from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.security import OAuth2PasswordBearer
from app.core.deps import get_usuario_atual
from app.services.dimensionamento import demand
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db

router = APIRouter(
    prefix="/dimensionamento",
    tags=["Dimensionamento"]
)


optional_token = OAuth2PasswordBearer(tokenUrl="/auth/login/", auto_error=False)


def transversal_access(linha: Optional[str] = Query(None), token=Depends(optional_token), db: Session = Depends(get_db)):
    # Existing modulo_id consumers retain their contract. New transversal reads
    # require the existing active-account authentication, not clinical grants.
    if linha is not None:
        if not token:
            raise HTTPException(401, 'Não autenticado', headers={'WWW-Authenticate':'Bearer'})
        return get_usuario_atual(token, db)


@router.get("/ocupacoes", dependencies=[Depends(transversal_access)])
def listar_dimensionamento_ocupacoes(
    modulo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    linha: Optional[str] = Query(None),
):
    if linha is not None:
        if modulo_id is not None:
            raise HTTPException(422, "Selecione linha ou modulo_id, não ambos.")
        return demand(db, linha)
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