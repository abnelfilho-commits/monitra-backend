"""Durable inbound receipt; committed atomically with conversation/clinical writes."""
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from app.database import Base


class WhatsAppMensagem(Base):
    __tablename__ = 'whatsapp_mensagens'
    message_id = Column(String(512), primary_key=True)
    phone_number_id = Column(String(128), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    resposta = Column(Text, nullable=False)
    enviado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, nullable=False, server_default=func.now())
