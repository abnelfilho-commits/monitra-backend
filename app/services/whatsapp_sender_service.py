import os
import requests


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
        token = os.getenv('WHATSAPP_ACCESS_TOKEN')
        phone_id = os.getenv('WHATSAPP_PHONE_NUMBER_ID')
        name = os.getenv('WHATSAPP_MENTAL_TEMPLATE_NAME')
        language = os.getenv('WHATSAPP_MENTAL_TEMPLATE_LANGUAGE')
        if not all(value and value.strip() for value in (token, phone_id, name, language)):
            raise ValueError('Configuração do convite WhatsApp indisponível.')
        response = requests.post(
            f'https://graph.facebook.com/v23.0/{phone_id}/messages',
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
            json={'messaging_product': 'whatsapp', 'to': telefone, 'type': 'template',
                  'template': {'name': name, 'language': {'code': language}}}, timeout=15)
        if not response.ok:
            raise RuntimeError(f'Falha no convite WhatsApp: {response.status_code}')
        return response.json()
