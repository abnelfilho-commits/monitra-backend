import os
import requests
import re
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone


_invitation_diagnostic = ContextVar('whatsapp_invitation_diagnostic', default=None)


@contextmanager
def invitation_diagnostics():
    """Request-local, allowlisted metadata only; never retain exception contents."""
    diagnostic = dict(graph_version='v25.0', observed_at_utc=datetime.now(timezone.utc).isoformat(), stage='delivery_preparation', category='other',
                      graph_http_status=None, meta_code=None, meta_subcode=None,
                      meta_trace_id=None, meta_accepted=False)
    token = _invitation_diagnostic.set(diagnostic)
    try:
        yield diagnostic
    finally:
        _invitation_diagnostic.reset(token)


def _diagnose(**values):
    diagnostic = _invitation_diagnostic.get()
    if diagnostic is not None:
        diagnostic.update(values)


def _integer(value):
    return value if type(value) is int and 0 <= value <= 2147483647 else None


def _meta_error(response, sensitive):
    try:
        body = response.json()
        error = body.get('error') if isinstance(body, dict) else None
        if not isinstance(error, dict):
            return
        trace = error.get('fbtrace_id')
        if (not isinstance(trace, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', trace)
                or trace.isdigit() or any(value and value in trace for value in sensitive)):
            trace = None
        _diagnose(meta_code=_integer(error.get('code')),
                  meta_subcode=_integer(error.get('error_subcode')), meta_trace_id=trace)
    except Exception:
        # Non-JSON/malformed errors must not replace the original HTTP failure.
        pass


class MetaInvitationRejected(RuntimeError):
    """Confirmed HTTP rejection with numeric, allowlisted metadata only."""
    def __init__(self, http_status, code=None, subcode=None):
        super().__init__('Meta rejected invitation')
        self.http_status = http_status
        self.code = _integer(code)
        self.subcode = _integer(subcode)


LEGACY_MENTAL_TEMPLATE = 'integra_care_checkin_bem_estar'
DATED_MENTAL_TEMPLATE = 'integra_care_checkin_acompanhamento_v1'


def mental_template_payload(name, language, checkin_date=None):
    """Explicit template contracts. Reference date is civil, never server time."""
    if name not in (LEGACY_MENTAL_TEMPLATE, DATED_MENTAL_TEMPLATE) or language != 'pt_BR':
        raise ValueError('Unsupported mental check-in template configuration')
    template = {'name': name, 'language': {'code': language}}
    if name == DATED_MENTAL_TEMPLATE:
        # Reject datetimes (including naive ones): the caller must supply the
        # conversation's canonical civil date, without timezone conversion.
        if type(checkin_date) is not date:
            raise ValueError('Check-in reference date required')
        template['components'] = [{'type': 'body', 'parameters': [
            {'type': 'text', 'text': checkin_date.strftime('%d/%m/%Y')}
        ]}]
    return template


class WhatsAppSenderService:

    @staticmethod
    def enviar_texto(
        telefone: str,
        mensagem: str,
        *, expected_phone_id=None,
    ):
        access_token = os.getenv(
            "WHATSAPP_ACCESS_TOKEN"
        )

        phone_number_id = os.getenv(
            "WHATSAPP_PHONE_NUMBER_ID"
        )

        if not access_token or not phone_number_id:
            raise ValueError(
                "Credenciais do WhatsApp não configuradas."
            )

        if expected_phone_id is not None and phone_number_id != expected_phone_id:
            raise ValueError("WhatsApp emitter changed")

        url = (
            "https://graph.facebook.com/v23.0/"
            f"{phone_number_id}/messages"
        )

        headers = {
            "Authorization": (
                f"Bearer {access_token}"
            ),
            "Content-Type": "application/json",
        }

        payload = {
            "messaging_product": "whatsapp",
            "to": telefone,
            "type": "text",
            "text": {
                "body": mensagem,
            },
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        if not response.ok:
            # A structured non-transient 4xx is a proven rejection, not delivery.
            if 400 <= response.status_code < 500 and response.status_code not in (408, 429):
                try:
                    error = response.json().get('error', {})
                    code = error.get('code')
                except (ValueError, AttributeError):
                    code = None
                if type(code) is int:
                    raise MetaInvitationRejected(response.status_code, code, None)
            raise RuntimeError(
                "Erro ao enviar mensagem WhatsApp: "
                f"{response.status_code}"
            )

        return response.json()

    @staticmethod
    def enviar_template(telefone: str, *, expected_phone_id=None, expected_template=None, checkin_date=None):
        _diagnose(stage='configuration', category='configuration')
        token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        name = os.getenv('WHATSAPP_MENTAL_TEMPLATE_NAME')
        language = os.getenv('WHATSAPP_MENTAL_TEMPLATE_LANGUAGE')
        if not all(value and value.strip() for value in (token, phone_id, name, language)):
            raise ValueError('Configuração do convite WhatsApp indisponível.')
        if expected_phone_id is not None and phone_id != expected_phone_id:
            raise ValueError('Invitation emitter changed')
        if expected_template is not None and (name, language) != expected_template:
            raise ValueError('Invitation template changed')
        template = mental_template_payload(name, language, checkin_date)
        _diagnose(stage='meta_request', category='other')
        try:
            response = requests.post(
                f'https://graph.facebook.com/v25.0/{phone_id}/messages',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={'messaging_product': 'whatsapp', 'to': telefone, 'type': 'template',
                      'template': template}, timeout=15)
        except requests.exceptions.Timeout:
            _diagnose(category='timeout')
            raise
        except requests.exceptions.ConnectionError:
            _diagnose(category='connection')
            raise
        _diagnose(stage='meta_response', graph_http_status=_integer(response.status_code),
                  observed_at_utc=datetime.now(timezone.utc).isoformat())
        if not response.ok:
            _diagnose(category='http_rejection')
            _meta_error(response, (token, telefone, phone_id))
            try:
                error = response.json().get('error')
            except Exception:
                error = None
            if 400 <= response.status_code < 500 and isinstance(error, dict) and _integer(error.get('code')) is not None:
                raise MetaInvitationRejected(response.status_code, error.get('code'), error.get('error_subcode'))
            raise RuntimeError('Uncertain Meta invitation response')
        _diagnose(meta_accepted=True)
        if expected_phone_id is not None and response.status_code != 200:
            raise RuntimeError('Unexpected Meta invitation success status')
        result = response.json()
        # Includes the service timestamp/flush, not only the router commit.
        _diagnose(stage='local_confirmation', category='other')
        return result
