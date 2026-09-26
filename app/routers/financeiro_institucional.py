"""HTTP boundary for the institutional financial preview."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.database import engine, get_db
from app.schemas.financeiro import (
    InstitutionalPreviewRequest,
    InstitutionalPreviewResult,
)
from app.services.autorizacao_institucional import (
    AutorizacaoInstitucionalErro,
    AutorizacaoInstitucionalService,
)
from app.services.financeiro.institutional_projection import (
    InstitutionalProjectionService,
)


router = APIRouter(
    prefix="/financeiro/institucional",
    tags=["Financeiro institucional"],
)

authorization = AutorizacaoInstitucionalService()
projection = InstitutionalProjectionService()

AUTH_ERROR_STATUS = {
    "USER_NOT_FOUND": 404,
    "INSTITUTION_NOT_FOUND": 404,
    "USER_INACTIVE": 409,
    "INSTITUTION_INACTIVE": 409,
    "EXPLICIT_INSTITUTION_REQUIRED": 422,
    "INSTITUTIONAL_ACCESS_DENIED": 403,
}


@router.post("/preview", response_model=InstitutionalPreviewResult)
def preview(
    payload: InstitutionalPreviewRequest,
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    try:
        authorization.authorize(
            db,
            usuario.id,
            payload.instituicao_id,
        )
    except AutorizacaoInstitucionalErro as exc:
        status = AUTH_ERROR_STATUS.get(exc.code, 500)
        code = exc.code if status != 500 else "INSTITUTIONAL_AUTHORIZATION_FAILED"
        raise HTTPException(status_code=status, detail={"code": code}) from None

    try:
        return projection.run(engine, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_INSTITUTIONAL_PREVIEW", "message": str(exc)},
        ) from None
