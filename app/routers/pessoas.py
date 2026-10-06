"""Global ADMIN register. Creation remains exclusively in /admin/identidades."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import NoResultFound
from app.database import get_db
from app.core.permissoes import exigir_admin
from app.schemas.pessoa import PessoaUpdate, PessoaOut
from app.services.pessoa import PessoaService
from app.schemas.acesso_pessoa import AcessoPessoaCreate, AcessoPessoaOut
from app.services.acesso_pessoa import AcessoPessoaService, AcessoPessoaErro
from app.services.autorizacao_institucional import AutorizacaoInstitucionalErro


class PessoaRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                return await handler(request)
            except RequestValidationError:
                raise HTTPException(422, {'code': 'INVALID_PAYLOAD'}) from None
        return handle


router = APIRouter(prefix='/admin/pessoas', tags=['Pessoas administrativas'], route_class=PessoaRoute)
service = PessoaService()


@router.post('/{pessoa_id}/acesso', response_model=AcessoPessoaOut)
def enable_access(payload: AcessoPessoaCreate, pessoa_id: int = Path(..., gt=0),
                  db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    try:
        result = AcessoPessoaService().enable(db, pessoa_id, payload, actor_id=admin.id)
        output = AcessoPessoaOut.model_validate(result)
        db.commit()
        return output
    except AcessoPessoaErro as exc:
        db.rollback()
        raise HTTPException(exc.status, {'code': exc.code}) from None
    except AutorizacaoInstitucionalErro as exc:
        db.rollback()
        raise HTTPException(403 if exc.code == 'ADMIN_REQUIRED' else 409, {'code': exc.code}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'ACCESS_PROVISIONING_FAILED'}) from None


@router.get('/', response_model=list[PessoaOut])
def list_pessoas(offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
                 db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    return [PessoaOut.model_validate(row) for row in service.list(db, offset=offset, limit=limit)]


@router.get('/{pessoa_id}', response_model=PessoaOut)
def get_pessoa(pessoa_id: int = Path(..., gt=0), db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    row = service.get(db, pessoa_id)
    if row is None:
        raise HTTPException(404, {'code': 'PERSON_NOT_FOUND'})
    return PessoaOut.model_validate(row)


@router.patch('/{pessoa_id}', response_model=PessoaOut)
def update_pessoa(payload: PessoaUpdate, pessoa_id: int = Path(..., gt=0),
                  db: Session = Depends(get_db), admin=Depends(exigir_admin)):
    try:
        try:
            row = service.update(db, pessoa_id, payload.model_dump(exclude_unset=True))
        except NoResultFound:
            raise HTTPException(404, {'code': 'PERSON_NOT_FOUND'}) from None
        except ValueError:
            raise HTTPException(422, {'code': 'INVALID_PERSON_DATA'}) from None
        output = PessoaOut.model_validate(row)
        db.commit()
        return output
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code': 'PERSON_OPERATION_FAILED'}) from None
