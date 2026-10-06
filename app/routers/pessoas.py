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
