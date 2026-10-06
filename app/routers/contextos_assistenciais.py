"""ADMIN structural preparation only; no clinical reads, activation or grants."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.schemas.contexto_assistencial import ContextoCreate, ContextoOut, ContextoLinhaRequest, ContextoLinhaOut
from app.services.contexto_assistencial import ContextoAssistencialService, ContextoAssistencialErro


class ContextoRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {'code': 'INVALID_PAYLOAD'}) from None
        return handle


router = APIRouter(prefix='/admin/contextos-assistenciais', tags=['Preparação assistencial administrativa'], route_class=ContextoRoute)
service = ContextoAssistencialService()
ERROR_STATUS = {'RESOURCE_NOT_FOUND': 404, 'INVALID_ID': 422,
    'EXPLICIT_PERSON_REQUIRED': 409, 'LINK_PERIOD_OR_STATE_CONFLICT': 409,
    'CONTEXT_PERIOD_CONFLICT': 409, 'CONTEXT_NOT_OPEN': 409, 'CONTEXT_LINE_DUPLICATE': 409}


def respond(db, operation, schema, *, write=False):
    try:
        output = schema.model_validate(operation())
        if write:
            db.commit()
        return output
    except ContextoAssistencialErro as exc:
        db.rollback()
        status = ERROR_STATUS.get(exc.code, 500)
        raise HTTPException(status, {'code': exc.code if status != 500 else 'CONTEXT_OPERATION_FAILED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'CONTEXT_OPERATION_FAILED'}) from None


@router.post('/', response_model=ContextoOut, status_code=201)
def create(payload: ContextoCreate, db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.create(db, payload, actor_id=admin.id), ContextoOut, write=True)


@router.get('/{contexto_id}', response_model=ContextoOut)
def get(contexto_id: int = Path(..., gt=0), instituicao_id: int = Query(..., gt=0),
        db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return respond(db, lambda: service.get(db, contexto_id, instituicao_id=instituicao_id), ContextoOut)


@router.post('/{contexto_id}/linhas', response_model=ContextoLinhaOut, status_code=201)
def add_line(payload: ContextoLinhaRequest, contexto_id: int = Path(..., gt=0),
             instituicao_id: int = Query(..., gt=0), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    def operation():
        service.get(db, contexto_id, instituicao_id=instituicao_id)
        return service.add_line(db, {'contexto_assistencial_id': contexto_id, 'modulo_id': payload.modulo_id})
    return respond(db, operation, ContextoLinhaOut, write=True)
