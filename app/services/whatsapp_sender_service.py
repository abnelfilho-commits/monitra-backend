import os
import requests
import re
from contextlib import contextmanager
from contextvars import ContextVar


_invitation_diagnostic = ContextVar('whatsapp_invitation_diagnostic', default=None)


@contextmanager
def invitation_diagnostics():
    """Request-local, allowlisted metadata only; never retain exception contents."""
    diagnostic = dict(stage='delivery_preparation', category='other',
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


class WhatsAppSenderService:

    @staticmethod
    def enviar_texto(
        telefone: str,
        mensagem: str,
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
            raise RuntimeError(
                "Erro ao enviar mensagem WhatsApp: "
                f"{response.status_code}"
            )

        return response.json()

    @staticmethod
    def enviar_template(telefone: str):
        _diagnose(stage='configuration', category='configuration')
        token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        name = os.getenv('WHATSAPP_MENTAL_TEMPLATE_NAME')
        language = os.getenv('WHATSAPP_MENTAL_TEMPLATE_LANGUAGE')
        if not all(value and value.strip() for value in (token, phone_id, name, language)):
            raise ValueError('Configuração do convite WhatsApp indisponível.')
        _diagnose(stage='meta_request', category='other')
        try:
            response = requests.post(
                f'https://graph.facebook.com/v23.0/{phone_id}/messages',
                headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                json={'messaging_product': 'whatsapp', 'to': telefone, 'type': 'template',
                      'template': {'name': name, 'language': {'code': language}}}, timeout=15)
        except requests.exceptions.Timeout:
            _diagnose(category='timeout')
            raise
        except requests.exceptions.ConnectionError:
            _diagnose(category='connection')
            raise
        _diagnose(stage='meta_response', graph_http_status=_integer(response.status_code))
        if not response.ok:
            _diagnose(category='http_rejection')
            _meta_error(response, (token, telefone, phone_id))
            raise RuntimeError(f'Falha no convite WhatsApp: {response.status_code}')
        _diagnose(meta_accepted=True)
        result = response.json()
        # Includes the service timestamp/flush, not only the router commit.
        _diagnose(stage='local_confirmation', category='other')
        return result
