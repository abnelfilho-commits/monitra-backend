"""Persistent pause and protocol gate. Missing schema always fails closed."""
from sqlalchemy import text
from app.services.checkin_bem_estar import CheckinInvalid

PROTOCOL = 'e14b_close_v1'


def require_active(db):
    # Shared row lock makes an operator pause wait for already authorized DB work.
    # No lock survives the durable boundary preceding external HTTP.
    row = db.execute(text("SELECT protocol, active FROM whatsapp_runtime WHERE id=1 FOR SHARE")).one_or_none()
    if row is None or row.protocol != PROTOCOL or not row.active:
        raise CheckinInvalid('WHATSAPP_RUNTIME_PAUSED_OR_INCOMPATIBLE')
