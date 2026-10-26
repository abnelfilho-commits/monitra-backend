"""Manual dispatch orchestration. No public opt-in assertion or retry bypass."""
import hashlib
import os
import re
from sqlalchemy import select, text, or_, and_
from app.models.whatsapp_manual import WhatsAppSolicitacaoManual as Manual
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio
from app.services.whatsapp_mental import (WhatsAppMentalService, Follow, Conversation,
    lock_phone, locked, lock_care, now_utc, valid_scope)
from app.services.checkin_bem_estar import CheckinInvalid
from app.services.whatsapp_autorizacao import require_prior_authorization


def blocking_attempt(db, phone, exclude_conversation=None, follow_id=None):
    from app.services.whatsapp_comunicacao import aliases
    emitter = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '').strip()
    if not emitter: raise CheckinInvalid('WHATSAPP_EMITTER_UNAVAILABLE')
    phones = aliases(db, emitter, phone)
    # Same followup remains blocking even if configuration/destination changed.
    same_follow = Conversation.acompanhamento_whatsapp_id == follow_id if follow_id is not None else False
    scope = or_(and_(Conversation.telefone.in_(phones), Envio.phone_number_id == emitter), same_follow)
    pending_scope = or_(Conversation.telefone.in_(phones), same_follow)
    q = select(Envio.id).join(Conversation, Conversation.id == Envio.conversa_id).where(
        scope, Envio.estado.in_(('PREPARADO','EM_EXECUCAO','INCERTO')))
    pending = select(Manual.id).join(Conversation, Conversation.id == Manual.conversa_id).where(
        pending_scope, Manual.estado == 'PREPARADO')
    if exclude_conversation is not None:
        q = q.where(Conversation.id != exclude_conversation)
        pending = pending.where(Conversation.id != exclude_conversation)
    return db.scalar(q.limit(1)) is not None or db.scalar(pending.limit(1)) is not None


def result(db, request):
    attempt = db.get(Envio, request.tentativa_id) if request.tentativa_id else None
    return dict(solicitacao_id=request.id, conversa_id=request.conversa_id,
        tentativa_id=request.tentativa_id, estado=attempt.estado if attempt else request.estado,
        aceitacao_meta=bool(attempt and attempt.estado == 'ACEITO'))


def dispatch_manual(db, context, key, payload):
    if not re.fullmatch(r'[A-Za-z0-9._:-]{16,128}', key or ''):
        raise CheckinInvalid('INVALID_IDEMPOTENCY_KEY')
    service = WhatsAppMentalService()
    service.authorized(db, lock=False, **context)
    initial = db.scalar(select(Follow).where(Follow.contexto_assistencial_id == context['context']))
    if initial is None: raise CheckinInvalid('FOLLOW_UP_NOT_FOUND')
    identity, phone = initial.id, initial.telefone
    db.rollback()  # Canonical lock order: phone before institution/care.
    # Serialize key across phones too; same key with changed context conflicts.
    from app.services.whatsapp_comunicacao import coordinate_configured
    coordinate_configured(db, (phone,), operation='manual:' + str(context['institution']) + ':' + str(context['actor']) + ':' + key)
    service.authorized(db, **context)
    follow = locked(db, Follow, identity)
    if follow.telefone != phone: raise CheckinInvalid('DESTINATION_CHANGED')
    old = db.scalar(select(Manual).where(Manual.instituicao_id == context['institution'],
        Manual.usuario_id == context['actor'], Manual.chave == key))
    if old:
        if old.acompanhamento_id != identity or old.motivo != payload.motivo:
            raise CheckinInvalid('IDEMPOTENCY_CONFLICT')
        output = result(db, old)
        db.rollback()
        return output  # Never retry even PREPARADO or uncertain after process death.
    c, patient, person = lock_care(db, context['context'])
    if not valid_scope(db, follow, c, patient, person, now_utc(db)):
        raise CheckinInvalid('FOLLOW_UP_NOT_ELIGIBLE')
    require_prior_authorization(db, follow)
    name = os.getenv('WHATSAPP_MENTAL_TEMPLATE_NAME', '').strip()
    language = os.getenv('WHATSAPP_MENTAL_TEMPLATE_LANGUAGE', '').strip()
    if not name or not language: raise CheckinInvalid('INVITATION_CONFIGURATION_UNAVAILABLE')
    conversation = service.prepare(db, identity, manual=True)
    if conversation is None: raise CheckinInvalid('INVITATION_NOT_ELIGIBLE')
    request = Manual(instituicao_id=context['institution'], acompanhamento_id=identity,
        usuario_id=context['actor'], chave=key, motivo=payload.motivo,
        conversa_id=conversation.id, template_nome=name, template_idioma=language)
    db.add(request); db.flush()
    request_id, conversation_id = request.id, conversation.id
    db.commit()  # Durable request and conversation before any transport.
    try:
        service.deliver_invitation(db, conversation_id, context=context)
    except Exception:
        # Transport owns acceptance/uncertainty; never resend or relabel rejection.
        db.rollback()
    request = db.get(Manual, request_id)
    output = result(db, request)
    db.rollback()
    return output
