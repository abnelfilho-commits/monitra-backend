"""Durable invitation transport; no transaction is held during external HTTP.

Only an explicit new request may retry a proven rejection. PREPARADO,
EM_EXECUCAO and INCERTO left by any interrupted request fail closed.
"""
import os
import re
from uuid import uuid4
from sqlalchemy import select, update
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio, WhatsAppConviteStatusEvento as Evento
from app.services.whatsapp_sender_service import WhatsAppSenderService, MetaInvitationRejected


def capture_wamid(result):
    messages = result.get('messages') if isinstance(result, dict) else None
    if not isinstance(messages, list) or len(messages) != 1 or not isinstance(messages[0], dict):
        raise ValueError('Ambiguous Meta invitation response')
    value = messages[0].get('id')
    if not isinstance(value, str) or not re.fullmatch(r'wamid\.[A-Za-z0-9+/=_-]{1,506}', value):
        raise ValueError('Invalid Meta invitation identifier')
    return value


def record_failure(db, identity, rejection=None):
    """Best effort. A failed update leaves durable EM_EXECUCAO blocking repeats."""
    try:
        db.rollback()
        attempt = db.scalar(select(Envio).where(Envio.id == identity).with_for_update())
        if attempt is not None and attempt.estado == 'EM_EXECUCAO':
            attempt.estado = 'REJEITADO' if rejection else 'INCERTO'
            attempt.motivo_sanitizado = 'META_REJECTION' if rejection else 'OUTCOME_UNCERTAIN'
            if rejection:
                attempt.graph_http_status = rejection.http_status
                attempt.meta_error_code = rejection.code
                attempt.meta_error_subcode = rejection.subcode
            db.commit()
        else:
            # A lost commit acknowledgement may already have persisted ACEITO.
            db.rollback()
    except Exception:
        db.rollback()


def deliver(db, identity, context, explicit_retry=False):
    from app.services.whatsapp_mental import (WhatsAppMentalService, lock_execution_scope,
                                             valid_scope, locked, Conversation, now_utc)
    service = WhatsAppMentalService()
    # Read configuration before creating an attempt; never persist credentials.
    emitter = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')
    required = (emitter, os.getenv('WHATSAPP_ACCESS_TOKEN', ''),
                os.getenv('WHATSAPP_MENTAL_TEMPLATE_NAME', ''),
                os.getenv('WHATSAPP_MENTAL_TEMPLATE_LANGUAGE', ''))
    if not all(v.strip() for v in required):
        raise ValueError('Invitation configuration unavailable')
    a, conversation, c, patient, person, now = lock_execution_scope(db, identity)
    service.authorized(db, **context)
    if (context['context'] != conversation.contexto_assistencial_id
            or conversation.convite_enviado_em is not None
            or conversation.status != 'AGUARDANDO_ACEITE' or conversation.expires_at <= now
            or not valid_scope(db, a, c, patient, person, now)):
        db.rollback()
        return False
    from app.services.whatsapp_manual import blocking_attempt, require_prior_authorization
    from app.models.whatsapp_manual import WhatsAppSolicitacaoManual as Manual
    if blocking_attempt(db, conversation.telefone, identity, follow_id=a.id):
        db.rollback()
        return False
    manual = db.scalar(select(Manual).where(Manual.conversa_id == identity))
    authorization = require_prior_authorization(db, a)
    if manual is not None:
        if (manual.usuario_id != context['actor'] or manual.instituicao_id != context['institution']
                or manual.acompanhamento_id != a.id or manual.tentativa_id is not None
                or manual.template_nome != required[2] or manual.template_idioma != required[3]):
            db.rollback()
            return False
    previous = db.scalar(select(Envio).where(Envio.conversa_id == identity)
                         .order_by(Envio.tentativa.desc()).limit(1))
    if previous is not None and (previous.estado != 'REJEITADO' or not explicit_retry):
        db.rollback()
        return False
    from app.services.whatsapp_sender_service import mental_template_payload
    mental_template_payload(required[2], required[3], conversation.data_referencia)
    attempt = Envio(conversa_id=identity, tentativa=previous.tentativa+1 if previous else 1,
                    correlacao_id=str(uuid4()), phone_number_id=emitter, estado='PREPARADO',
                    autorizacao_comunicacao_id=authorization.id)
    db.add(attempt)
    db.flush()
    attempt_id = attempt.id
    if manual is not None:
        manual.tentativa_id = attempt_id
        manual.estado = 'VINCULADO'
    db.commit()  # PREPARADO must survive process failure.

    # Reacquire canonical locks and eligibility after the preparation commit.
    a, conversation, c, patient, person, now = lock_execution_scope(db, identity)
    service.authorized(db, **context)
    attempt = db.scalar(select(Envio).where(Envio.id == attempt_id).with_for_update())
    if (attempt.estado != 'PREPARADO' or conversation.convite_enviado_em is not None
            or conversation.status != 'AGUARDANDO_ACEITE' or conversation.expires_at <= now
            or not valid_scope(db, a, c, patient, person, now)):
        db.rollback()
        return False
    authorization = require_prior_authorization(db, a)
    if authorization.id != attempt.autorizacao_comunicacao_id:
        db.rollback()
        return False
    phone = conversation.telefone
    checkin_date = conversation.data_referencia
    attempt.estado = 'EM_EXECUCAO'
    attempt.iniciado_em = now
    db.commit()  # No DB transaction/locks remain across the network call.

    try:
        result = WhatsAppSenderService.enviar_template(phone, expected_phone_id=emitter, expected_template=(required[2], required[3]), checkin_date=checkin_date)
        wamid = capture_wamid(result)
        # Record acceptance even if consent/state changed during the network call.
        # Only the transport timestamp changes; never overwrite clinical state.
        conversation = locked(db, Conversation, identity)
        attempt = db.scalar(select(Envio).where(Envio.id == attempt_id).with_for_update())
        from app.services.whatsapp_convite_status import lock_message
        lock_message(db, emitter, wamid)
        attempt.wamid = wamid
        attempt.estado = 'ACEITO'
        attempt.confirmado_em = now_utc(db)
        attempt.graph_http_status = 200
        conversation.convite_enviado_em = attempt.confirmado_em
        db.flush()
        db.execute(update(Evento).where(Evento.envio_id.is_(None),
                   Evento.phone_number_id == emitter, Evento.wamid == wamid).values(envio_id=attempt_id))
        db.commit()
        return True
    except MetaInvitationRejected as exc:
        record_failure(db, attempt_id, rejection=exc)
        raise
    except Exception:
        record_failure(db, attempt_id)
        raise
