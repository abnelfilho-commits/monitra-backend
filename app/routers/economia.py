"""Global ADMIN economic service catalogue; caller owns transactions."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.models.financeiro import ServicoEconomico
from app.schemas.financeiro import ServicoCreate, ServicoResponse, ServicoEstado
from app.services.financeiro.configuracao import FinanceiroConfiguracaoService, FinanceiroErro


class EconomicRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {'code': 'INVALID_PAYLOAD'}) from None
        return handle


router = APIRouter(prefix='/admin/economia/servicos', tags=['Administração Econômica'],
                   dependencies=[Depends(exigir_admin)], route_class=EconomicRoute)
service = FinanceiroConfiguracaoService()


def respond(db, operation, *, write=False, many=False):
    try:
        result = operation()
        if write:
            result = service.get_service(db, result.id)
        output = ([ServicoResponse.model_validate(row) for row in result] if many
                  else ServicoResponse.model_validate(result))
        if write:
            db.commit()
        return output
    except FinanceiroErro as exc:
        db.rollback()
        status = {'NOT_FOUND': 404, 'SERVICE_IN_USE': 409,
                  'CLEAN_SESSION_REQUIRED': 409}.get(exc.code, 500)
        raise HTTPException(status, {'code': exc.code if status != 500 else 'ECONOMIC_OPERATION_FAILED'}) from None
    except IntegrityError as exc:
        db.rollback()
        code = getattr(exc.orig, 'pgcode', None)
        constraint = getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None)
        if code == '23505' and constraint == 'uq_servico_economico_codigo':
            raise HTTPException(409, {'code': 'SERVICE_CODE_EXISTS'}) from None
        if code == '23503' and constraint == 'servicos_economicos_ocupacao_id_fkey':
            raise HTTPException(422, {'code': 'OCCUPATION_NOT_FOUND'}) from None
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None


@router.get('/', response_model=list[ServicoResponse])
def list_services(ativo: Optional[bool] = None, db: Session = Depends(get_db)):
    return respond(db, lambda: service.list_services(db, ativo=ativo), many=True)


@router.get('/{servico_id}', response_model=ServicoResponse)
def get_service(servico_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.get_service(db, servico_id))


@router.post('/', response_model=ServicoResponse)
def create(payload: ServicoCreate, db: Session = Depends(get_db)):
    return respond(db, lambda: service.create(db, ServicoEconomico, payload), write=True)


@router.put('/{servico_id}', response_model=ServicoResponse)
def update(payload: ServicoCreate, servico_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.update_service(db, servico_id, payload), write=True)


@router.patch('/{servico_id}/estado', response_model=ServicoResponse)
def state(payload: ServicoEstado, servico_id: int = Path(..., gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.set_service_active(db, servico_id, payload.ativo), write=True)
