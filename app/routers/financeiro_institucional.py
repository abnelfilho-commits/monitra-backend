"""HTTP boundary for the institutional financial preview."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import get_usuario_atual
from app.database import engine, get_db
from app.schemas.financeiro import (
    InstitutionalContextContract,
    InstitutionalContextInstitution,
    InstitutionalContextResult,
    InstitutionalPreviewRequest,
    InstitutionalPreviewResult,
)
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso
from app.models.financeiro import ContratoFinanceiro
from app.models.institucional import Instituicao
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


@router.get("/contexto", response_model=InstitutionalContextResult)
def contexto(
    db: Session = Depends(get_db),
    usuario=Depends(get_usuario_atual),
):
    if not usuario.ativo:
        raise HTTPException(
            status_code=409,
            detail={"code": "USER_INACTIVE"},
        )

    instituicoes_stmt = (
        select(Instituicao)
        .where(Instituicao.ativo.is_(True))
        .order_by(Instituicao.razao_social, Instituicao.id)
    )

    if usuario.perfil != "ADMIN":
        instituicoes_stmt = (
            instituicoes_stmt
            .join(
                UsuarioInstituicaoAcesso,
                UsuarioInstituicaoAcesso.instituicao_id == Instituicao.id,
            )
            .where(
                UsuarioInstituicaoAcesso.usuario_id == usuario.id,
                UsuarioInstituicaoAcesso.ativo.is_(True),
            )
        )

    instituicoes = tuple(db.scalars(instituicoes_stmt).all())
    instituicao_ids = tuple(item.id for item in instituicoes)

    contratos = ()
    if instituicao_ids:
        contratos_stmt = (
            select(ContratoFinanceiro)
            .where(
                ContratoFinanceiro.pagador_instituicao_id.in_(instituicao_ids),
                ContratoFinanceiro.estado == "PUBLISHED",
            )
            .order_by(
                ContratoFinanceiro.pagador_instituicao_id,
                ContratoFinanceiro.codigo,
                ContratoFinanceiro.edicao,
            )
        )
        contratos = tuple(db.scalars(contratos_stmt).all())

    return InstitutionalContextResult(
        instituicoes=tuple(
            InstitutionalContextInstitution(
                id=item.id,
                nome=item.nome_fantasia or item.razao_social,
            )
            for item in instituicoes
        ),
        contratos=tuple(
            InstitutionalContextContract(
                id=item.id,
                instituicao_id=item.pagador_instituicao_id,
                codigo=item.codigo,
                edicao=item.edicao,
                inicio=item.inicio,
                fim=item.fim,
            )
            for item in contratos
        ),
    )


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
