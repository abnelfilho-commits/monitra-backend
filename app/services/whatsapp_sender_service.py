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
                f"{response.status_code} "
                f"{response.text}"
            )

        return response.json()