"""AE4 global ADMIN boundary; validate output before committing."""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.core.permissoes import exigir_admin
from app.database import get_db
from app.routers.economia import EconomicRoute
from app.schemas.financeiro import MapeamentoCreate
from app.schemas.mapeamentos_economicos import AgendaEconomicaResponse, MapeamentoAlterar
from app.services.financeiro.configuracao import FinanceiroConfiguracaoService, FinanceiroErro

router = APIRouter(prefix='/admin/economia/mapeamentos', tags=['Administração Econômica'],
                   dependencies=[Depends(exigir_admin)], route_class=EconomicRoute)
service = FinanceiroConfiguracaoService()


def respond(db, operation, *, write=False):
    try:
        result = operation()
        output = (AgendaEconomicaResponse.model_validate(result).model_dump(mode='json') if write
                  else [AgendaEconomicaResponse.model_validate(row).model_dump(mode='json') for row in result])
        if write:
            db.commit()
        return output
    except FinanceiroErro as exc:
        db.rollback()
        status = {'NOT_FOUND': 404, 'MAPPING_CONFLICT': 409, 'INACTIVE_SERVICE': 422,
                  'CLEAN_SESSION_REQUIRED': 409}.get(exc.code, 500)
        raise HTTPException(status, {'code': exc.code if status != 500 else 'ECONOMIC_OPERATION_FAILED'}) from None
    except DBAPIError as exc:
        db.rollback()
        code = getattr(exc.orig, 'pgcode', None)
        if code in ('40001', '40P01'):
            raise HTTPException(409, {'code': 'CONCURRENT_CONFIGURATION_CHANGE'}) from None
        if code == '23503':
            raise HTTPException(422, {'code': 'REFERENCE_NOT_FOUND'}) from None
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None


@router.get('/', response_model=list[AgendaEconomicaResponse])
def list_agendas(modulo_id: Optional[int] = Query(None, gt=0),
                 situacao: Literal['TODOS', 'MAPEADOS', 'NAO_MAPEADOS'] = 'TODOS',
                 busca: Optional[str] = Query(None, max_length=200), db: Session = Depends(get_db)):
    return respond(db, lambda: service.list_mapping_agendas(db, modulo_id=modulo_id, situacao=situacao, busca=busca))


@router.post('/', response_model=AgendaEconomicaResponse)
def create(payload: MapeamentoCreate, db: Session = Depends(get_db)):
    return respond(db, lambda: service.administer_mapping(db, payload=payload), write=True)


@router.put('/{mapeamento_id}', response_model=AgendaEconomicaResponse)
def change(payload: MapeamentoAlterar, mapeamento_id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.administer_mapping(db, identity=mapeamento_id, servico_id=payload.servico_id), write=True)
