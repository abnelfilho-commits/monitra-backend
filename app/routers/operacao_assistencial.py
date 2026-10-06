"""Operational W1B boundary; authenticated actor only, no clinical data."""
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.core.permissoes import exigir_admin
from app.routers.contextos_assistenciais import ContextoRoute
from app.services.operacao_assistencial import OperacaoAssistencialService
from app.services.permissao_assistencial import PermissaoAssistencialErro
from app.services.contexto_assistencial import ContextoAssistencialErro
from app.schemas.operacao_assistencial import NominationRequest, GrantRequest, ParticipationRequest, ReasonRequest
from app.schemas.permissao_assistencial import AutoridadeDelegacaoRecord, ConcessaoAssistencialRecord, ContextoProfissionalRecord
from app.schemas.contexto_assistencial import ContextoLinhaOut

router = APIRouter(prefix='/operacao-assistencial', tags=['Operação contextual'], route_class=ContextoRoute)
service = OperacaoAssistencialService()
DENIED = {'AUTHORITY_DENIED', 'CONTEXT_ADMINISTRATION_DENIED', 'OPERATION_DENIED', 'ADMIN_REQUIRED',
          'SELF_GRANT_DENIED', 'SELF_DELEGATION_DENIED', 'ACTOR_INACTIVE', 'VALID_PERSON_REQUIRED', 'INSTITUTION_MISMATCH'}


def respond(db, operation, schema=None, *, write=False, many=False):
    try:
        result = operation()
        if schema:
            result = ([schema.model_validate(r).model_dump(mode='json') for r in result] if many
                      else schema.model_validate(result).model_dump(mode='json'))
        if write:
            db.commit()
        return result
    except (PermissaoAssistencialErro, ContextoAssistencialErro) as exc:
        if write: db.rollback()
        status = 403 if exc.code in DENIED else 404 if exc.code == 'RESOURCE_NOT_FOUND' else 409
        raise HTTPException(status, {'code': exc.code}) from None
    except ValidationError:
        if write: db.rollback()
        raise HTTPException(422, {'code': 'INVALID_COMMAND'}) from None
    except IntegrityError:
        if write: db.rollback()
        raise HTTPException(409, {'code': 'OPERATION_CONFLICT'}) from None
    except Exception:
        if write: db.rollback()
        raise HTTPException(500, {'code': 'OPERATION_NOT_CONFIRMED'}) from None


def scope(contexto_id: int = Path(..., gt=0, le=2147483647), instituicao_id: int = Query(..., gt=0, le=2147483647)):
    return instituicao_id, contexto_id


@router.get('/instituicoes')
def institutions(db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return respond(db, lambda: service.institutions(db, actor.id))


@router.get('/contextos')
def contexts(instituicao_id: int = Query(..., gt=0, le=2147483647), db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return respond(db, lambda: service.contexts(db, actor.id, instituicao_id))


@router.get('/contextos/{contexto_id}')
def state(ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return respond(db, lambda: service.state(db, actor.id, *ids))


@router.post('/contextos/{contexto_id}/saude-mental/ativar', response_model=ContextoLinhaOut)
def activate(ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(exigir_admin)):
    return respond(db, lambda: service.line(db, actor.id, *ids, True), ContextoLinhaOut, write=True)


@router.post('/contextos/{contexto_id}/saude-mental/desativar', response_model=ContextoLinhaOut)
def deactivate(ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(exigir_admin)):
    return respond(db, lambda: service.line(db, actor.id, *ids, False), ContextoLinhaOut, write=True)


@router.post('/contextos/{contexto_id}/autoridades/bootstrap', response_model=list[AutoridadeDelegacaoRecord])
def bootstrap(payload: NominationRequest, ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(exigir_admin)):
    return respond(db, lambda: service.nominate(db, actor.id, *ids, payload), AutoridadeDelegacaoRecord, write=True, many=True)


@router.post('/contextos/{contexto_id}/autoridades/recovery', response_model=list[AutoridadeDelegacaoRecord])
def recovery(payload: NominationRequest, ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(exigir_admin)):
    return respond(db, lambda: service.nominate(db, actor.id, *ids, payload, recovery=True), AutoridadeDelegacaoRecord, write=True, many=True)


@router.post('/contextos/{contexto_id}/grants', response_model=ConcessaoAssistencialRecord)
def grant(payload: GrantRequest, ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return respond(db, lambda: service.contextual_grant(db, actor.id, *ids, payload), ConcessaoAssistencialRecord, write=True)


@router.post('/contextos/{contexto_id}/grants/{grant_id}/revogar', response_model=ConcessaoAssistencialRecord)
def revoke(payload: ReasonRequest, grant_id: int = Path(..., gt=0, le=2147483647), ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return respond(db, lambda: service.contextual_revoke(db, actor.id, *ids, grant_id, payload), ConcessaoAssistencialRecord, write=True)


@router.post('/contextos/{contexto_id}/participacoes', response_model=ContextoProfissionalRecord)
def participation(payload: ParticipationRequest, ids=Depends(scope), db: Session = Depends(get_db), actor=Depends(get_usuario_atual)):
    return respond(db, lambda: service.contextual_participation(db, actor.id, *ids, payload), ContextoProfissionalRecord, write=True)
