"""Shared transport authentication and atomic inbound-message processing."""
import hashlib
import hmac
import json
import os
from fastapi import HTTPException


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
    """Authenticated selected ingress; no phone-search fallback or external IO."""
    from app.services.whatsapp_runtime import require_active
    from app.services.whatsapp_stop import is_stop, process as process_stop
    from app.services.whatsapp_selected import process_selected
    try:
        require_active(db)
        if is_stop(content):
            return process_stop(db, identity, recipient, sender, content, context_wamid)
        return process_selected(db, identity, recipient, sender, content, context_wamid)
    except Exception:
        db.rollback()
        raise


def deliver_reply(db, identity, sender):
    from app.services.whatsapp_resposta import deliver
    return deliver(db, identity, sender)
