"""AE3 ADMIN HTTP boundary for contracts and beneficiaries."""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.permissoes import exigir_admin
from app.routers.economia import EconomicRoute
from app.database import get_db
from app.models.financeiro import ContratoFinanceiro, PacienteContrato
from app.schemas.financeiro import (
    Command,
    ContratoCreate,
    ContratoAdminResponse,
    BeneficiarioCreate,
    BeneficiarioResponse,
    BeneficiarioCandidateResponse,
    BeneficiarioClose,
)
from app.services.financeiro.configuracao import FinanceiroConfiguracaoService, FinanceiroErro


service = FinanceiroConfiguracaoService()
router = APIRouter(
    prefix='/admin/economia',
    dependencies=[Depends(exigir_admin)],
    tags=['Administração Econômica'],
    route_class=EconomicRoute,
)


def respond(db, operation, schema=None, *, write=False, many=False):
    try:
        result = operation()
        output = (
            [schema.model_validate(row).model_dump(mode='json') for row in result]
            if many
            else schema.model_validate(result).model_dump(mode='json')
            if schema
            else None
        )
        if write:
            db.commit()
        return output
    except FinanceiroErro as exc:
        db.rollback()
        status = {
            'NOT_FOUND': 404,
            'PUBLISHED_IMMUTABLE': 409,
            'CONCURRENT_CONFIGURATION_CHANGE': 409,
            'CLEAN_SESSION_REQUIRED': 409,
            'INVALID_PUBLISHER': 403,
            'PAYER_TABLE_MISMATCH': 422,
            'INVALID_BENEFICIARY': 422,
            'BENEFICIARY_PAYER_MISMATCH': 422,
            'BENEFICIARY_OUTSIDE_CONTRACT_PERIOD': 422,
            'BENEFICIARY_ALREADY_CLOSED': 409,
            'INVALID_PERIOD': 422,
        }.get(exc.code, 500)
        raise HTTPException(
            status,
            {'code': exc.code if status != 500 else 'ECONOMIC_OPERATION_FAILED'},
        ) from None
    except DBAPIError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None)
        code = getattr(exc.orig, 'pgcode', None)

        duplicates = {
            'uq_contrato_financeiro_edicao': 'CONTRACT_EDITION_EXISTS',
        }
        if code == '23505' and constraint in duplicates:
            raise HTTPException(409, {'code': duplicates[constraint]}) from None

        if constraint == 'ex_paciente_contrato_periodo':
            raise HTTPException(409, {'code': 'BENEFICIARY_PERIOD_OVERLAP'}) from None

        if code == '23503':
            raise HTTPException(422, {'code': 'REFERENCE_NOT_FOUND'}) from None

        if code in ('40001', '40P01'):
            raise HTTPException(
                409,
                {'code': 'CONCURRENT_CONFIGURATION_CHANGE'},
            ) from None

        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'ECONOMIC_OPERATION_FAILED'}) from None


@router.get('/contratos/', response_model=list[ContratoAdminResponse])
def contracts(db: Session = Depends(get_db)):
    return respond(
        db,
        lambda: service.list_contracts(db),
        ContratoAdminResponse,
        many=True,
    )


@router.post('/contratos/', response_model=ContratoAdminResponse)
def create_contract(payload: ContratoCreate, db: Session = Depends(get_db)):
    return respond(
        db,
        lambda: service.get_contract(
            db,
            service.create(db, ContratoFinanceiro, payload).id,
        ),
        ContratoAdminResponse,
        write=True,
    )


@router.get('/contratos/{id}', response_model=ContratoAdminResponse)
def contract(id: int = Path(gt=0), db: Session = Depends(get_db)):
    return respond(
        db,
        lambda: service.get_contract(db, id),
        ContratoAdminResponse,
    )


@router.put('/contratos/{id}', response_model=ContratoAdminResponse)
def update_contract(
    payload: ContratoCreate,
    id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    def operation():
        service.update_draft(db, ContratoFinanceiro, id, payload)
        return service.get_contract(db, id)

    return respond(
        db,
        operation,
        ContratoAdminResponse,
        write=True,
    )


@router.post('/contratos/{id}/publicar', response_model=ContratoAdminResponse)
def publish_contract(
    payload: Optional[Command] = Body(default=None),
    id: int = Path(gt=0),
    db: Session = Depends(get_db),
    actor=Depends(exigir_admin),
):
    def operation():
        service.publish_contract(db, id, actor_id=actor.id)
        return service.get_contract(db, id)

    return respond(
        db,
        operation,
        ContratoAdminResponse,
        write=True,
    )

@router.get(
    '/contratos/{id}/beneficiarios/candidatos',
    response_model=list[BeneficiarioCandidateResponse],
)
def beneficiary_candidates(
    id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    return respond(
        db,
        lambda: service.list_beneficiary_candidates(db, id),
        BeneficiarioCandidateResponse,
        many=True,
    )


@router.get(
    '/contratos/{id}/beneficiarios',
    response_model=list[BeneficiarioResponse],
)
def beneficiaries(
    id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    return respond(
        db,
        lambda: service.list_beneficiaries(db, id),
        BeneficiarioResponse,
        many=True,
    )


@router.post(
    '/contratos/{id}/beneficiarios',
    response_model=BeneficiarioResponse,
)
def create_beneficiary(
    payload: BeneficiarioCreate,
    id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    def operation():
        row = service.create(
            db,
            PacienteContrato,
            dict(payload.model_dump(), contrato_id=id),
        )
        return service.get_beneficiary(db, row.id)

    return respond(
        db,
        operation,
        BeneficiarioResponse,
        write=True,
    )


@router.post(
    '/beneficiarios/{id}/encerrar',
    response_model=BeneficiarioResponse,
)
def close_beneficiary(
    payload: BeneficiarioClose,
    id: int = Path(gt=0),
    db: Session = Depends(get_db),
):
    def operation():
        row = service.close_beneficiary(db, id, fim=payload.fim)
        return service.get_beneficiary(db, row.id)

    return respond(
        db,
        operation,
        BeneficiarioResponse,
        write=True,
    )

