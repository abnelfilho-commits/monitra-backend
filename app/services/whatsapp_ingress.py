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

    Reply is retained without logging clinical contents.
    Durable executions block retries after uncertain transport failure; clinical writes
    and conversation transitions are processed only once per message identity.
    """
    try:
        # Transport coordination precedes existing routing/clinical locks.
        from app.services.whatsapp_comunicacao import coordinate
        if context_wamid is not None:
            from app.services.whatsapp_referencia import lock_reference
            lock_reference(db, recipient, sender, context_wamid, operation='ingress:'+identity)
        else:
            coordinate(db, recipient, sender, operation='ingress:'+identity, identity_check=False)
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
            if context_wamid is not None:
                from app.services.whatsapp_referencia import resolve
                response = resolve(db, recipient, sender, context_wamid, content,
                                   message_id=identity, observation=observation)
            else:
                response = dispatch(db, sender, content, legacy, message_id=identity, observation=observation)
            if observation.get('conversa_legada_id') is not None:
                from app.models.whatsapp_conversa import WhatsAppConversa
                from app.services.whatsapp_transporte import legacy_state
                db.flush()
                observation['legado_estado_sha256'] = legacy_state(db.get(WhatsAppConversa, observation['conversa_legada_id']))
            db.query(WhatsAppMensagem).filter_by(message_id=identity).update(dict(observation, resposta=response))
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise


def deliver_reply(db, identity, sender):
    from app.services.whatsapp_resposta import deliver
    return deliver(db, identity, sender)
