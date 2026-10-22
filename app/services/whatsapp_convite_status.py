"""Authenticated transport evidence only. No clinical transitions or outbound IO."""
import hashlib
import json
import re
from datetime import datetime, timezone
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio, WhatsAppConviteStatusEvento as Evento


def lock_message(db, phone_number_id, wamid):
    # Same key on acceptance and callback: an early callback cannot remain orphaned
    # because its insert raced the sender's correlation UPDATE.
    value = json.dumps(['invitation-status-v1', phone_number_id, wamid], separators=(',', ':'))
    key = int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], 'big', signed=True)
    db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


def parse_statuses(value, recipient):
    statuses = value.get('statuses', [])
    if not isinstance(statuses, list):
        raise ValueError('Invalid status collection')
    parsed = []
    for event in statuses:
        if not isinstance(event, dict):
            raise ValueError('Invalid status event')
        wamid, status, stamp = event.get('id'), event.get('status'), event.get('timestamp')
        # Authenticated future statuses must not discard valid siblings/messages.
        # No raw payload or unknown evidence is stored or exposed.
        if isinstance(status, str) and status not in ('sent', 'delivered', 'read', 'failed'):
            continue
        if (not isinstance(wamid, str) or not re.fullmatch(r'wamid\.[A-Za-z0-9+/=_-]{1,506}', wamid)
                or status not in ('sent', 'delivered', 'read', 'failed')
                or not isinstance(stamp, str) or not re.fullmatch(r'[0-9]{1,12}', stamp)):
            raise ValueError('Invalid status identity or timestamp')
        try:
            occurred = datetime.fromtimestamp(int(stamp), timezone.utc)
        except (ValueError, OverflowError, OSError):
            raise ValueError('Invalid status timestamp') from None
        errors = event.get('errors', [])
        if not isinstance(errors, list):
            raise ValueError('Invalid error collection')
        codes = set()
        for error in errors:
            if not isinstance(error, dict):
                raise ValueError('Invalid status error')
            code, subcode = error.get('code'), error.get('error_subcode')
            if (type(code) is not int or not 0 <= code <= 2147483647
                    or (subcode is not None and (type(subcode) is not int or not 0 <= subcode <= 2147483647))):
                raise ValueError('Invalid numeric error')
            codes.add((code, subcode))
        # One row per distinct numeric error; no error is silently lost in the
        # scalar error columns. Input order and repeated errors do not affect keys.
        for code, subcode in sorted(codes, key=lambda x: (x[0], -1 if x[1] is None else x[1])) if codes else [(None, None)]:
            identity = ['v1', recipient, wamid, status, int(stamp), code, subcode]
            key = hashlib.sha256(json.dumps(identity, separators=(',', ':')).encode()).hexdigest()
            parsed.append(dict(phone_number_id=recipient, wamid=wamid, status=status,
                               evento_em=occurred, deduplicacao_chave=key,
                               meta_error_code=code, meta_error_subcode=subcode,
                               motivo_sanitizado=('META_ERROR_'+str(code)) if code is not None else
                               ('META_DELIVERY_FAILED' if status == 'failed' else None)))
    return parsed


def persist_statuses(db, events):
    """Commit entire status batch before acknowledging it or handling messages."""
    if not events:
        return
    try:
        pairs = sorted({(e['phone_number_id'], e['wamid']) for e in events})
        bindings = {}
        for emitter, wamid in pairs:
            lock_message(db, emitter, wamid)
            bindings[emitter, wamid] = db.scalar(select(Envio.id).where(
                Envio.phone_number_id == emitter, Envio.wamid == wamid))
        for event in events:
            envio_id = bindings[event['phone_number_id'], event['wamid']]
            statement = insert(Evento).values(**event, envio_id=envio_id)
            # Replayed early events can acquire a now-known binding. Existing
            # timestamps, errors and evidence are otherwise immutable.
            if envio_id is None:
                statement = statement.on_conflict_do_nothing(index_elements=['deduplicacao_chave'])
            else:
                statement = statement.on_conflict_do_update(index_elements=['deduplicacao_chave'],
                    set_={'envio_id': envio_id}, where=Evento.envio_id.is_(None))
            db.execute(statement)
        db.commit()
    except Exception:
        db.rollback()
        raise
