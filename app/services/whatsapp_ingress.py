"""Shared transport authentication and atomic inbound-message processing."""
import hashlib
import hmac
import json
import os
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from app.models.whatsapp_mensagem import WhatsAppMensagem
from app.services.whatsapp_conversation_service import processar_mensagem, normalizar_telefone


def authenticated_events(body, signature):
    secret = os.getenv('WHATSAPP_APP_SECRET', '')
    recipient = os.getenv('WHATSAPP_PHONE_NUMBER_ID', '')
    if not secret.strip() or not recipient.strip():
        raise HTTPException(503, 'WhatsApp ingress unavailable.')
    expected = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected.encode(), signature.encode()):
        raise HTTPException(403, 'Invalid webhook signature.')
    try:
        payload = json.loads(body)
        if not isinstance(payload, dict) or payload.get('object') != 'whatsapp_business_account':
            raise ValueError()
        entries = payload['entry']
        if not isinstance(entries, list) or not entries:
            raise ValueError()
        messages = []
        statuses = []
        for entry in entries:
            changes = entry['changes']
            if not isinstance(changes, list) or not changes:
                raise ValueError()
            for change in changes:
                if change.get('field') != 'messages':
                    raise ValueError()
                value = change['value']
                if value['metadata']['phone_number_id'] != recipient:
                    raise HTTPException(403, 'Unexpected webhook recipient.')
                from app.services.whatsapp_convite_status import parse_statuses
                statuses.extend(parse_statuses(value, recipient))
                incoming = value.get('messages', [])
                if not isinstance(incoming, list):
                    raise ValueError()
                for message in incoming:
                    if message.get('type') != 'text':
                        continue
                    identity, sender, content = message['id'], message['from'], message['text']['body']
                    if (not isinstance(identity, str) or not 1 <= len(identity) <= 512
                            or not isinstance(sender, str) or not sender.isascii()
                            or not sender.isdigit() or not 8 <= len(sender) <= 15
                            or not isinstance(content, str) or not content.strip() or len(content) > 4096):
                        raise ValueError()
                    context = message.get('context')
                    if context is not None:
                        from app.services.whatsapp_transporte import wamid_valid
                        if not isinstance(context, dict) or ('id' in context and not wamid_valid(context['id'])):
                            raise ValueError()
                        messages.append((identity, recipient, sender, content, context.get('id')))
                    else:
                        messages.append((identity, recipient, sender, content))
        return messages, statuses
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, AttributeError):
        raise HTTPException(400, 'Invalid webhook payload.') from None


def process_message(db, identity, recipient, sender, content, context_wamid=None):
    """PostgreSQL owns dedup and sender serialization; no intermediate commits.

    Reply is retained for outbound retry, without logging clinical contents.
    Delivery may be repeated after an uncertain transport failure; clinical writes
    and conversation transitions are processed only once per message identity.
    """
    try:
        # Serializes even the first conversation; transaction-scoped, no session lock.
        key = int.from_bytes(hashlib.sha256(normalizar_telefone(sender).encode()).digest()[:8],
                             'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})
        fingerprint = hashlib.sha256(json.dumps([recipient, sender, content], ensure_ascii=False).encode()).hexdigest()
        # v1 receipts remain replayable using their original fingerprint contract.
        legacy_fingerprint = fingerprint
        fingerprint = hashlib.sha256(json.dumps([recipient, sender, content, context_wamid], ensure_ascii=False).encode()).hexdigest()
        claimed = db.execute(insert(WhatsAppMensagem).values(
            message_id=identity, phone_number_id=recipient, fingerprint=fingerprint, fingerprint_versao=2, context_wamid=context_wamid, resposta='').on_conflict_do_nothing(
                index_elements=['message_id']).returning(WhatsAppMensagem.message_id)).scalar()
        if claimed is None:
            receipt = db.query(WhatsAppMensagem).filter_by(message_id=identity).one()
            if receipt.phone_number_id != recipient or receipt.fingerprint != (legacy_fingerprint if receipt.fingerprint_versao == 1 else fingerprint):
                raise HTTPException(409, 'Webhook identity conflict.')
            response = receipt.resposta
        else:
            from app.services.whatsapp_mental import dispatch
            observation = {}
            def legacy(session, phone, message):
                return processar_mensagem(session, phone, message, observation=observation)
            response = dispatch(db, sender, content, legacy, message_id=identity, observation=observation)
            db.query(WhatsAppMensagem).filter_by(message_id=identity).update(dict(observation, resposta=response))
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def deliver_reply(db, identity, sender):
    """Serialize outbound retries after clinical commit, without repeating writes.

    A network timeout after Meta accepted a reply still has uncertain delivery;
    no exactly-once network delivery is claimed without a remote idempotency API.
    """
    from datetime import datetime
    from app.services.whatsapp_sender_service import WhatsAppSenderService
    try:
        receipt = db.query(WhatsAppMensagem).filter_by(message_id=identity).with_for_update().one()
        if receipt.enviado_em is None:
            result = WhatsAppSenderService.enviar_texto(sender, receipt.resposta)
            # Mark accepted text delivery before optional evidence persistence. A
            # capture failure must not cause an additional text send on replay.
            receipt.enviado_em = datetime.utcnow()
            db.commit()
            if receipt.conversa_contextual_id is not None or receipt.conversa_legada_id is not None:
                from app.services.whatsapp_transporte import capture
                capture(db, result, emitter=receipt.phone_number_id, requested=sender,
                        contextual=receipt.conversa_contextual_id, legacy=receipt.conversa_legada_id,
                        origin='META_RESPOSTA')
        db.commit()
    except Exception:
        db.rollback()
        raise
