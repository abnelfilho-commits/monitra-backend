import os

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
)
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.whatsapp_conversation_service import (
    processar_mensagem,
)

from app.services.whatsapp_sender_service import (
    WhatsAppSenderService,
)

router = APIRouter(
    prefix="/whatsapp",
    tags=["WhatsApp"],
)


class WhatsAppTesteRequest(BaseModel):
    telefone: str
    mensagem: str


@router.post("/teste")
def testar_whatsapp(
    payload: WhatsAppTesteRequest,
    db: Session = Depends(get_db),
):
    resposta = processar_mensagem(
        db=db,
        telefone=payload.telefone,
        mensagem=payload.mensagem,
    )

    return {
        "resposta": resposta,
    }
    
# ---------------------------------------------------------
# WEBHOOK — VERIFICAÇÃO DA META
# ---------------------------------------------------------

@router.get("/webhook")
def verificar_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(
        None,
        alias="hub.verify_token",
    ),
    hub_challenge: str = Query(
        None,
        alias="hub.challenge",
    ),
):
    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN")

    if (
        hub_mode == "subscribe"
        and hub_verify_token == verify_token
    ):
        return PlainTextResponse(
            content=hub_challenge or "",
            status_code=200,
        )

    raise HTTPException(
        status_code=403,
        detail="Falha na verificação do webhook.",
    )


# ---------------------------------------------------------
# WEBHOOK — RECEBIMENTO DE MENSAGENS
# ---------------------------------------------------------

@router.post("/webhook")
def receber_webhook(
    payload: dict,
    db: Session = Depends(get_db),
):

    try:
        entry = payload.get("entry", [])

        if not entry:
            return {"status": "ignored"}

        changes = entry[0].get("changes", [])

        if not changes:
            return {"status": "ignored"}

        value = changes[0].get("value", {})

        messages = value.get("messages", [])

        # A Meta também envia eventos de status:
        # enviado, entregue, lido etc.
        if not messages:
            return {"status": "ignored"}

        message = messages[0]

        telefone = message.get("from")

        message_type = message.get("type")

        if message_type != "text":
            return {
                "status": "ignored",
                "reason": "unsupported_message_type",
            }

        texto = (
            message
            .get("text", {})
            .get("body", "")
            .strip()
        )

        if not telefone or not texto:
            return {"status": "ignored"}

        resposta = processar_mensagem(
            db=db,
            telefone=telefone,
            mensagem=texto,
        )
        if os.getenv("WHATSAPP_ACCESS_TOKEN"):
            WhatsAppSenderService.enviar_texto(
                telefone=telefone,
                mensagem=resposta,
            )
        else:
            print(
                "[WHATSAPP] Resposta simulada:",
                resposta,
            )

        # Ainda não enviaremos para a Meta.
        # Neste momento estamos validando apenas
        # entrada -> motor conversacional.
        print(
            "[WHATSAPP] "
            f"De: {telefone} | "
            f"Mensagem: {texto} | "
            f"Resposta: {resposta}"
        )

        return {
            "status": "processed",
        }

    except Exception as exc:
        print(
            "[WHATSAPP] Erro ao processar webhook:",
            repr(exc),
        )

        # Importante:
        # não expor detalhes internos no endpoint público.
        return {
            "status": "error",
        }