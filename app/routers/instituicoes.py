"""Global-ADMIN institution register; no legacy clinic synchronization."""
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.schemas.institucional import InstituicaoCreate, InstituicaoUpdate, InstituicaoResponse
from app.services.institucional import InstitucionalService, InstitucionalErro


class InstitutionRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {'code': 'INVALID_PAYLOAD'}) from None
        return handle


router = APIRouter(prefix='/admin/instituicoes', tags=['Instituições administrativas'],
                   route_class=InstitutionRoute)
service = InstitucionalService()
ERROR_STATUS = {
    'ADMIN_REQUIRED': 403, 'INSTITUTION_NOT_FOUND': 404,
    'PARENT_INSTITUTION_NOT_FOUND': 422, 'INSTITUTION_HIERARCHY_CYCLE': 409,
    'CLEAN_SESSION_REQUIRED': 409,
}


def respond(db, operation, *, write=False, many=False):
    try:
        result = operation()
        output = ([InstituicaoResponse.model_validate(row) for row in result] if many
                  else InstituicaoResponse.model_validate(result))
        if write:
            db.commit()
        return output
    except InstitucionalErro as exc:
        db.rollback()
        status = ERROR_STATUS.get(exc.code, 500)
        raise HTTPException(status, {'code': exc.code if status != 500 else 'INSTITUTION_OPERATION_FAILED'}) from None
    except IntegrityError as exc:
        db.rollback()
        # Only the physical CNPJ UNIQUE identifies this business conflict.
        if (getattr(exc.orig, 'pgcode', None) == '23505' and
                getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None) == 'instituicoes_cnpj_key'):
            raise HTTPException(409, {'code': 'CNPJ_ALREADY_EXISTS'}) from None
        raise HTTPException(500, {'code': 'INSTITUTION_OPERATION_FAILED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'INSTITUTION_OPERATION_FAILED'}) from None


@router.get('/', response_model=list[InstituicaoResponse])
def list_instituicoes(
    ativo: Optional[bool] = Query(None),
    tipo_instituicao: Optional[Literal['CLINICA','UNIDADE_SAUDE','OPERADORA_SAUDE','GOVERNO_SECRETARIA','EMPRESA','INSTITUTO_ASSOCIACAO','OUTRO']] = Query(None),
    db: Session = Depends(get_db), admin=Depends(exigir_admin),
):
    return respond(db, lambda: service.list_instituicoes(db, actor_id=admin.id,
        ativo=ativo, tipo_instituicao=tipo_instituicao), many=True)


@router.get('/{instituicao_id}', response_model=InstituicaoResponse)
def get_instituicao(instituicao_id: int = Path(..., gt=0), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.get_instituicao(db, instituicao_id, actor_id=admin.id))


@router.post('/', response_model=InstituicaoResponse)
def create(payload: InstituicaoCreate, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.create_instituicao(db, payload, actor_id=admin.id), write=True)


@router.patch('/{instituicao_id}', response_model=InstituicaoResponse)
def update(payload: InstituicaoUpdate, instituicao_id: int = Path(..., gt=0),
           db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.update_instituicao(db, instituicao_id, payload, actor_id=admin.id), write=True)


@router.post('/{instituicao_id}/ativar', response_model=InstituicaoResponse)
def activate(instituicao_id: int = Path(..., gt=0), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.set_instituicao_active(db, instituicao_id, True, actor_id=admin.id), write=True)


@router.post('/{instituicao_id}/inativar', response_model=InstituicaoResponse)
def deactivate(instituicao_id: int = Path(..., gt=0), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.set_instituicao_active(db, instituicao_id, False, actor_id=admin.id), write=True)
