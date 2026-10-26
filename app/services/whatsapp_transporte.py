"""Capture evidence only; optional/invalid contacts never change legacy routing."""
import re
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Message


def wamid_valid(value):
    return isinstance(value, str) and re.fullmatch(r'wamid\.[A-Za-z0-9+/=_-]{1,506}', value) is not None


def contact_evidence(result, requested):
    if not isinstance(result, dict) or result.get('contacts') is None:
        return 'AUSENTE', None
    contacts = result['contacts']
    if not isinstance(contacts, list) or len(contacts) != 1 or not isinstance(contacts[0], dict):
        return 'INVALIDA', None
    contact = contacts[0]
    wa = contact.get('wa_id')
    if contact.get('input') != requested or not isinstance(wa, str) or not re.fullmatch(r'[0-9]{8,15}', wa):
        return 'INVALIDA', None
    return 'VALIDA', wa


def capture(db, result, *, emitter, requested, contextual=None, legacy=None, origin):
    # Older text transports may not return an identifier. Never invent one.
    messages = result.get('messages') if isinstance(result, dict) else None
    if (not isinstance(messages, list) or len(messages) != 1 or not isinstance(messages[0], dict)
            or not wamid_valid(messages[0].get('id'))):
        return None
    state, wa = contact_evidence(result, requested)
    values = dict(phone_number_id=emitter, wamid=messages[0]['id'], destinatario_solicitado=requested,
                  wa_id=wa, evidencia_estado=state, conversa_contextual_id=contextual,
                  conversa_legada_id=legacy, origem=origin)
    db.execute(insert(Message).values(**values).on_conflict_do_nothing(constraint='uq_wmr_emissor_wamid'))
    row = db.scalar(select(Message).where(Message.phone_number_id==emitter, Message.wamid==values['wamid']))
    if any(getattr(row, k) != v for k,v in values.items()):
        raise ValueError('Transport evidence conflict')
    return row
