"""Context-authorized management and controlled proactive execution."""
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp, WhatsAppConversaContextual
from app.schemas.whatsapp_mental import WhatsAppConfig, WhatsAppState
from app.services.whatsapp_mental import WhatsAppMentalService, OPEN
from app.services.checkin_bem_estar import CheckinDenied, CheckinInvalid
from app.services.whatsapp_sender_service import invitation_diagnostics

router = APIRouter(prefix='/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/whatsapp', tags=['Saúde Mental'])
service = WhatsAppMentalService()

# Inherit the server's INFO handler so successful diagnostics are visible too.
logger = logging.getLogger('uvicorn.error.whatsapp_mental')


def scope(pessoa_id: int = Path(gt=0), contexto_id: int = Path(gt=0),
          instituicao_id: int = Query(gt=0), actor=Depends(get_usuario_atual)):
    return dict(actor=actor.id, institution=instituicao_id, person=pessoa_id, context=contexto_id)


def command(db, operation, write=True):
    try:
        result = operation()
        output = WhatsAppState.model_validate(result).model_dump(mode='json') if result else None
        if write: db.commit()
        return output
    except CheckinDenied:
        db.rollback()
        raise HTTPException(403, {'code':'CHECKIN_UNAVAILABLE'}) from None
    except CheckinInvalid as exc:
        db.rollback()
        raise HTTPException(409, {'code':str(exc)}) from None
    except Exception:
        db.rollback()
        raise HTTPException(500, {'code':'WHATSAPP_OPERATION_FAILED'}) from None


@router.get('', response_model=Optional[WhatsAppState])
def state(db: Session = Depends(get_db), context=Depends(scope)):
    return command(db, lambda: service.read(db, **context), write=False)


@router.put('', response_model=WhatsAppState)
def configure(payload: WhatsAppConfig, db: Session = Depends(get_db), context=Depends(scope)):
    return command(db, lambda: service.configure(db, payload.telefone, **context))


@router.post('/pausar', response_model=WhatsAppState)
def pause(db: Session = Depends(get_db), context=Depends(scope)):
    return command(db, lambda: service.lifecycle(db, 'pausar', **context))


@router.post('/reativar', response_model=WhatsAppState)
def resume(db: Session = Depends(get_db), context=Depends(scope)):
    return command(db, lambda: service.lifecycle(db, 'reativar', **context))


@router.post('/encerrar', response_model=WhatsAppState)
def end(db: Session = Depends(get_db), context=Depends(scope)):
    return command(db, lambda: service.lifecycle(db, 'encerrar', **context))


def invitation(db, context, retry=False):
    # Commit the execution before Meta; uncertain delivery never recreates it.
    try:
        service.authorized(db, **context)
        a = db.scalar(select(AcompanhamentoWhatsApp).where(AcompanhamentoWhatsApp.contexto_assistencial_id == context['context']))
        if a is None: raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
        # Release authorization locks before taking the phone lock (canonical order).
        db.rollback()
        if retry:
            conversation = db.scalar(select(WhatsAppConversaContextual).where(
                WhatsAppConversaContextual.acompanhamento_whatsapp_id == a.id,
                WhatsAppConversaContextual.status.in_(OPEN)))
        else:
            conversation = service.prepare(db, a.id)
        identity = conversation.id if conversation else None
        db.commit()
    except CheckinDenied:
        db.rollback()
        raise HTTPException(403, {'code':'CHECKIN_UNAVAILABLE'}) from None
    except CheckinInvalid as exc:
        db.rollback()
        raise HTTPException(409, {'code':str(exc)}) from None
    except Exception:
        db.rollback()
        raise HTTPException(409, {'code':'WHATSAPP_DISPATCH_FAILED'}) from None
    if identity is None: return {'status':'NAO_ELEGIVEL', 'conversa_id':None}
    with invitation_diagnostics() as diagnostic:
        try:
            sent = service.deliver_invitation(db, identity, context=context, explicit_retry=retry)
            diagnostic['stage'] = 'local_commit'
            db.commit()
            if sent:
                logger.info(
                    'WhatsApp invitation confirmed conversation_id=%s graph_version=%s '
                    'observed_at_utc=%s graph_http_status=%s meta_accepted=%s',
                    identity, diagnostic['graph_version'], diagnostic['observed_at_utc'],
                    diagnostic['graph_http_status'], diagnostic['meta_accepted'])
            return {'status':'ENVIADO' if sent else 'SEM_NOVO_ENVIO', 'conversa_id':identity}
        except Exception:
            # Do not log exception strings, tracebacks, requests or response bodies.
            logger.warning(
                'WhatsApp invitation failed conversation_id=%s stage=%s category=%s '
                'graph_http_status=%s meta_code=%s meta_subcode=%s meta_trace_id=%s meta_accepted=%s '
                'graph_version=%s observed_at_utc=%s',
                identity, diagnostic['stage'], diagnostic['category'],
                diagnostic['graph_http_status'], diagnostic['meta_code'],
                diagnostic['meta_subcode'], diagnostic['meta_trace_id'], diagnostic['meta_accepted'],
                diagnostic['graph_version'], diagnostic['observed_at_utc'])
            db.rollback()
            # Durable attempts block repetition of uncertain or interrupted sends.
            return {'status':'ENVIO_PENDENTE', 'conversa_id':identity}


@router.post('/disparar')
def send(db: Session = Depends(get_db), context=Depends(scope)):
    return invitation(db, context)


@router.post('/reenviar-convite')
def retry(db: Session = Depends(get_db), context=Depends(scope)):
    return invitation(db, context, retry=True)


@router.get('/diagnostico')
def diagnostic(db: Session = Depends(get_db), context=Depends(scope)):
    from app.services.whatsapp_diagnostico import diagnose
    try:
        return diagnose(db, **context)
    except CheckinDenied:
        raise HTTPException(403, {'code': 'CHECKIN_UNAVAILABLE'}) from None
    except Exception:
        raise HTTPException(500, {'code': 'WHATSAPP_OPERATION_FAILED'}) from None
