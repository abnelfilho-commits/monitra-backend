"""HTTP adapter only: authentication and errors are scoped to this router."""
from datetime import date
from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.exc import InterfaceError, OperationalError, TimeoutError
from sqlalchemy.orm import Session

from app.core.permissoes import exigir_admin
from app.database import get_db
from app.schemas.consolidacao_gerencial import (
    MonthlyManagementResponse, AuthenticationErrorResponse, ManagementErrorResponse,
)
from app.services.consolidacao_mensal import ConsolidacaoMensalService
from app.services.institucional import InstitucionalErro


class ManagementRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {'code': 'INVALID_MONTHLY_PARAMETERS'}) from None
            except HTTPException:
                # Preserve legitimate authentication status, headers and messages.
                raise
            except (OperationalError, InterfaceError, TimeoutError):
                # Includes failures during dependency resolution; no SQL/params.
                raise HTTPException(503, {'code': 'MONTHLY_CONSOLIDATION_UNAVAILABLE'}) from None
            except Exception:
                raise HTTPException(500, {'code': 'MONTHLY_CONSOLIDATION_FAILED'}) from None
        return handle


router = APIRouter(prefix='/admin/consolidacao-gerencial',
                   tags=['Consolidação gerencial'], route_class=ManagementRoute)
service = ConsolidacaoMensalService()


def _with_reasons(result):
    demand = ['DEMANDA_NAO_CALCULAVEL'] if result['demanda_mensal_projetada'] is None else []
    capacity = ['CAPACIDADE_NAO_CONCLUSIVA'] if result['capacidade_mensal_equivalente'] is None else []
    zero = ['CAPACIDADE_ZERO'] if result['capacidade_mensal_equivalente'] == '0.00' else []
    return dict(result, motivos_nao_calculaveis=dict(
        demanda_mensal_projetada=demand, capacidade_mensal_equivalente=capacity,
        saldo_mensal=demand + capacity, utilizacao_percentual=demand + capacity + zero))


@router.get('/mensal', response_model=MonthlyManagementResponse, responses={
    401: {'model': AuthenticationErrorResponse, 'description': 'Autenticação ausente, inválida ou conta inativa.',
          'headers': {'WWW-Authenticate': {'schema': {'type': 'string'}, 'description': 'Bearer'}}},
    403: {'model': Union[AuthenticationErrorResponse, ManagementErrorResponse],
          'description': 'Perfil negado pela dependência ou ADMIN_REQUIRED na revalidação.'},
    422: {'model': ManagementErrorResponse, 'description': 'INVALID_MONTHLY_PARAMETERS'},
    404: {'model': ManagementErrorResponse, 'description': 'CAPACITY_INSTITUTION_NOT_FOUND'},
    409: {'model': ManagementErrorResponse, 'description': 'CAPACITY_INSTITUTION_INACTIVE'},
    500: {'model': ManagementErrorResponse, 'description': 'MONTHLY_CONSOLIDATION_FAILED'},
    503: {'model': ManagementErrorResponse, 'description': 'MONTHLY_CONSOLIDATION_UNAVAILABLE'},
})
def monthly_management(instituicao_id: int = Query(..., gt=0),
                       mes_referencia: str = Query(..., pattern=r'^[0-9]{4}-(0[1-9]|1[0-2])$'),
                       ocupacao_id: Optional[int] = Query(None, gt=0),
                       db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    try:
        date(int(mes_referencia[:4]), int(mes_referencia[5:]), 1)
    except ValueError:
        raise HTTPException(422, {'code': 'INVALID_MONTHLY_PARAMETERS'}) from None
    try:
        result = service.calculate(db, instituicao_id=instituicao_id,
            mes_referencia=mes_referencia, ocupacao_id=ocupacao_id, actor_id=admin.id)
        output = _with_reasons(result)
        output['ocupacoes'] = [_with_reasons(group) for group in result['ocupacoes']]
        return MonthlyManagementResponse.model_validate(output)
    except InstitucionalErro as exc:
        codes = {'ADMIN_REQUIRED': 403, 'CAPACITY_INSTITUTION_NOT_FOUND': 404,
                 'CAPACITY_INSTITUTION_INACTIVE': 409}
        if exc.code in codes:
            raise HTTPException(codes[exc.code], {'code': exc.code}) from None
        raise HTTPException(500, {'code': 'MONTHLY_CONSOLIDATION_FAILED'}) from None
    except (OperationalError, InterfaceError, TimeoutError):
        raise HTTPException(503, {'code': 'MONTHLY_CONSOLIDATION_UNAVAILABLE'}) from None
    except Exception:
        raise HTTPException(500, {'code': 'MONTHLY_CONSOLIDATION_FAILED'}) from None
