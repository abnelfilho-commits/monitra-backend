"""Thin global-ADMIN boundary for explicit institutional authorizations."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.schemas.autorizacao_institucional import AcessoCreate, PerfilChange, AcessoResponse
from app.services.autorizacao_institucional import AutorizacaoInstitucionalService, AutorizacaoInstitucionalErro


class AuthorizationRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {'code': 'INVALID_PAYLOAD'}) from None
        return handle


router = APIRouter(prefix='/admin/autorizacoes-institucionais',
                   tags=['Autorizações institucionais administrativas'], route_class=AuthorizationRoute)
service = AutorizacaoInstitucionalService()
ERROR_STATUS = {
    'ADMIN_REQUIRED': 403,
    'USER_NOT_FOUND': 404, 'INSTITUTION_NOT_FOUND': 404, 'ACCESS_NOT_FOUND': 404,
    'ACCESS_CONFLICT': 409, 'CONCURRENT_ACCESS_CONFLICT': 409,
    'USER_INACTIVE': 409, 'INSTITUTION_INACTIVE': 409,
    'EXPLICIT_INSTITUTION_REQUIRED': 422,
}


def respond(db, operation, *, write=False, many=False):
    try:
        result = operation()
        output = ([AcessoResponse.model_validate(row) for row in result] if many
                  else AcessoResponse.model_validate(result))
        if write:
            db.commit()
        return output
    except AutorizacaoInstitucionalErro as exc:
        db.rollback()
        status = ERROR_STATUS.get(exc.code, 500)
        code = exc.code if status != 500 else 'AUTHORIZATION_OPERATION_FAILED'
        raise HTTPException(status, {'code': code}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'AUTHORIZATION_OPERATION_FAILED'}) from None


@router.post('/', response_model=AcessoResponse)
def create(payload: AcessoCreate, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.create(db, payload, actor_id=admin.id), write=True)


@router.get('/', response_model=list[AcessoResponse])
def list_access(instituicao_id: int = Query(..., gt=0), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.list(db, instituicao_id=instituicao_id, actor_id=admin.id), many=True)


@router.get('/{instituicao_id}/{usuario_id}', response_model=AcessoResponse)
def get(instituicao_id: int = Path(..., gt=0), usuario_id: int = Path(..., gt=0),
        db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.get(db, usuario_id, instituicao_id, actor_id=admin.id))


@router.patch('/{instituicao_id}/{usuario_id}/perfil', response_model=AcessoResponse)
def profile(payload: PerfilChange, instituicao_id: int = Path(..., gt=0), usuario_id: int = Path(..., gt=0),
            db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.change_profile(db, usuario_id, instituicao_id, payload, actor_id=admin.id), write=True)


@router.post('/{instituicao_id}/{usuario_id}/ativar', response_model=AcessoResponse)
def activate(instituicao_id: int = Path(..., gt=0), usuario_id: int = Path(..., gt=0),
             db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.activate(db, usuario_id, instituicao_id, actor_id=admin.id), write=True)


@router.post('/{instituicao_id}/{usuario_id}/desativar', response_model=AcessoResponse)
def deactivate(instituicao_id: int = Path(..., gt=0), usuario_id: int = Path(..., gt=0),
               db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.deactivate(db, usuario_id, instituicao_id, actor_id=admin.id), write=True)
