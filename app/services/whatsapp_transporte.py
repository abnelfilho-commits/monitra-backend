"""Capture evidence only; optional/invalid contacts never change legacy routing."""
import re
import hashlib
import json
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


def legacy_state(conversation):
    """Identity and episode position only; never copy answers into evidence."""
    fields = ('id', 'responsavel_id', 'paciente_id', 'telefone', 'care_line',
              'etapa_atual', 'data_referencia', 'updated_at')
    values = [getattr(conversation, key) for key in fields]
    return hashlib.sha256(json.dumps(values, default=str, ensure_ascii=False).encode()).hexdigest()


_CURRENT_STATE = object()


def capture(db, result, *, emitter, requested, contextual=None, legacy=None, origin, legacy_snapshot=_CURRENT_STATE):
    # Older text transports may not return an identifier. Never invent one.
    messages = result.get('messages') if isinstance(result, dict) else None
    if (not isinstance(messages, list) or len(messages) != 1 or not isinstance(messages[0], dict)
            or not wamid_valid(messages[0].get('id'))):
        return None
    state, wa = contact_evidence(result, requested)
    snapshot = None
    if legacy_snapshot is not _CURRENT_STATE:
        snapshot = legacy_snapshot
    elif legacy is not None:
        from app.models.whatsapp_conversa import WhatsAppConversa
        db.flush()
        conversation = db.get(WhatsAppConversa, legacy)
        if conversation is not None:
            snapshot = legacy_state(conversation)
    values = dict(phone_number_id=emitter, wamid=messages[0]['id'], destinatario_solicitado=requested,
                  wa_id=wa, evidencia_estado=state, legado_estado_sha256=snapshot, conversa_contextual_id=contextual,
                  conversa_legada_id=legacy, origem=origin)
    db.execute(insert(Message).values(**values).on_conflict_do_nothing(constraint='uq_wmr_emissor_wamid'))
    row = db.scalar(select(Message).where(Message.phone_number_id==emitter, Message.wamid==values['wamid']))
    if any(getattr(row, k) != v for k,v in values.items()):
        raise ValueError('Transport evidence conflict')
    return row
