"""One authenticated ingress for every care line. No public diagnostic bypass."""
import hmac
import logging
import os
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.services.whatsapp_ingress import authenticated_messages, process_message, deliver_reply
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix='/whatsapp', tags=['WhatsApp'])
logger = logging.getLogger(__name__)


class WebhookAccessFilter(logging.Filter):
    """Uvicorn access logs must not retain the GET verification token."""
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) == 5:
            args = list(record.args)
            if isinstance(args[2], str) and args[2].split('?', 1)[0] == '/whatsapp/webhook':
                args[2] = '/whatsapp/webhook'
                record.args = tuple(args)
        return True


logging.getLogger('uvicorn.access').addFilter(WebhookAccessFilter())


@router.get('/webhook')
def verificar_webhook(
    hub_mode: str = Query(None, alias='hub.mode'),
    hub_verify_token: str = Query(None, alias='hub.verify_token'),
    hub_challenge: str = Query(None, alias='hub.challenge'),
):
    expected = os.getenv('WHATSAPP_VERIFY_TOKEN', '')
    if not expected.strip():
        raise HTTPException(503, 'WhatsApp verification unavailable.')
    if (hub_mode != 'subscribe' or not hub_verify_token or not hub_challenge
            or not hmac.compare_digest(expected.encode(), hub_verify_token.encode())):
        raise HTTPException(403, 'Invalid verification token.')
    return PlainTextResponse(hub_challenge)


@router.post('/webhook')
async def receber_webhook(request: Request, db: Session = Depends(get_db)):
    # get_db only creates a Session; no query occurs before authentication/validation.
    messages = authenticated_messages(await request.body(), request.headers.get('X-Hub-Signature-256'))
    return await run_in_threadpool(process_validated, db, messages)


def process_validated(db, messages):
    try:
        for identity, recipient, sender, content in messages:
            process_message(db, identity, recipient, sender, content)
            if os.getenv('WHATSAPP_ACCESS_TOKEN'):
                deliver_reply(db, identity, sender)
        return {'status': 'processed' if messages else 'ignored'}
    except HTTPException:
        raise
    except Exception:
        # No exception strings/tracebacks: transports/DB exceptions can contain PHI.
        logger.error('WhatsApp processing or delivery failed.')
        raise HTTPException(503, 'WhatsApp processing unavailable.') from None
