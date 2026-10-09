"""AE2 ADMIN HTTP boundary. Economic rules remain in the canonical service."""
from typing import Optional
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from app.core.permissoes import exigir_admin
from app.routers.economia import EconomicRoute
from app.database import get_db
from app.models.financeiro import TabelaPreco, TabelaPrecoVersao, PrecoServico
from app.schemas.financeiro import (Command, TabelaCreate, TabelaResponse, VersaoAdministrativaInput,
    VersaoResponse, PrecoAdministrativoInput, PrecoAdministrativoUpdate, PrecoResponse, GradePrecosResponse)
from app.services.financeiro.configuracao import FinanceiroConfiguracaoService, FinanceiroErro

service = FinanceiroConfiguracaoService()
router = APIRouter(prefix='/admin/economia', dependencies=[Depends(exigir_admin)],
                   tags=['Administração Econômica'], route_class=EconomicRoute)


def respond(db, operation, schema=None, *, write=False, many=False):
    try:
        result = operation()
        output = ([schema.model_validate(row).model_dump(mode='json') for row in result] if many
                  else schema.model_validate(result).model_dump(mode='json') if schema else None)
        if write:
            db.commit()
        return output
    except FinanceiroErro as exc:
        db.rollback()
        status = {'NOT_FOUND': 404, 'PUBLISHED_IMMUTABLE': 409,
                  'CONCURRENT_CONFIGURATION_CHANGE': 409, 'CLEAN_SESSION_REQUIRED': 409,
                  'RETROACTIVE_PUBLICATION': 422, 'INVALID_PUBLISHER': 403}.get(exc.code, 500)
        raise HTTPException(status, {'code': exc.code if status != 500 else 'ECONOMIC_OPERATION_FAILED'}) from None
    except DBAPIError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None)
        duplicates = {'uq_tabela_preco_codigo': 'TABLE_CODE_EXISTS',
                      'uq_tabela_preco_versao_numero': 'VERSION_NUMBER_EXISTS',
                      'uq_tabela_preco_versao_vigencia': 'VERSION_DATE_EXISTS',
                      'uq_preco_servico': 'SERVICE_PRICE_EXISTS',
                      'uq_preco_servico_externo': 'EXTERNAL_CODE_EXISTS'}
        code = getattr(exc.orig, 'pgcode', None)
        if code == '23505' and constraint in duplicates:
            raise HTTPException(409, {'code': duplicates[constraint]}) from None
        if constraint in ('f1_version_immutable', 'f1_price_immutable'):
            raise HTTPException(409, {'code': 'PUBLISHED_IMMUTABLE'}) from None
        if constraint == 'f1_version_retroactive':
            raise HTTPException(422, {'code': 'RETROACTIVE_PUBLICATION'}) from None
        if code == '23503':
            raise HTTPException(422, {'code': 'REFERENCE_NOT_FOUND'}) from None
        if code in ('40001', '40P01'):
            raise HTTPException(409, {'code': 'CONCURRENT_CONFIGURATION_CHANGE'}) from None
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None


@router.get('/tabelas/', response_model=list[TabelaResponse])
def tables(db: Session = Depends(get_db)):
    return respond(db, lambda: service.list_tables(db), TabelaResponse, many=True)


@router.post('/tabelas/', response_model=TabelaResponse)
def create_table(payload: TabelaCreate, db: Session = Depends(get_db)):
    return respond(db, lambda: service.get_table(db, service.create(db, TabelaPreco, payload).id),
                   TabelaResponse, write=True)


@router.get('/tabelas/{id}', response_model=TabelaResponse)
def table(id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.get_table(db, id), TabelaResponse)


@router.get('/tabelas/{id}/versoes', response_model=list[VersaoResponse])
def versions(id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.list_versions(db, id), VersaoResponse, many=True)


@router.post('/tabelas/{id}/versoes', response_model=VersaoResponse)
def create_version(payload: VersaoAdministrativaInput, id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.create(db, TabelaPrecoVersao, dict(payload.model_dump(), tabela_id=id)),
                   VersaoResponse, write=True)


@router.get('/versoes/{id}', response_model=VersaoResponse)
def version(id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.read_row(db, TabelaPrecoVersao, id), VersaoResponse)


@router.put('/versoes/{id}', response_model=VersaoResponse)
def update_version(payload: VersaoAdministrativaInput, id: int = Path(gt=0), db: Session = Depends(get_db)):
    def operation():
        row = service.read_row(db, TabelaPrecoVersao, id)
        return service.update_draft(db, TabelaPrecoVersao, id, dict(payload.model_dump(), tabela_id=row.tabela_id))
    return respond(db, operation, VersaoResponse, write=True)


@router.post('/versoes/{id}/publicar', response_model=VersaoResponse)
def publish(payload: Optional[Command] = Body(default=None), id: int = Path(gt=0),
            db: Session = Depends(get_db), actor=Depends(exigir_admin)):
    return respond(db, lambda: service.publish_version(db, id, actor_id=actor.id), VersaoResponse, write=True)


@router.get('/versoes/{id}/precos', response_model=GradePrecosResponse)
def prices(id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.list_prices(db, id), GradePrecosResponse)



@router.post('/versoes/{id}/precos', response_model=PrecoResponse)
def create_price(payload: PrecoAdministrativoInput, id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(db, lambda: service.price_output(db, service.create(db, PrecoServico,
                   dict(payload.model_dump(), versao_id=id))), PrecoResponse, write=True)


@router.put('/precos/{id}', response_model=PrecoResponse)
def update_price(payload: PrecoAdministrativoUpdate, id: int = Path(gt=0), db: Session = Depends(get_db)):
    def operation():
        row = service.read_row(db, PrecoServico, id)
        return service.price_output(db, service.update_price(db, id, dict(payload.model_dump(),
                            versao_id=row.versao_id, servico_id=row.servico_id)))
    return respond(db, operation, PrecoResponse, write=True)


@router.delete('/precos/{id}', status_code=204)
def delete_price(id: int = Path(gt=0), db: Session = Depends(get_db)):
    respond(db, lambda: service.delete_price(db, id), write=True)
    return Response(status_code=204)
