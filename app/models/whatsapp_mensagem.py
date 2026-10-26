"""Durable inbound receipt; committed atomically with conversation/clinical writes."""
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, CheckConstraint
from sqlalchemy.sql import func
from app.database import Base


class WhatsAppMensagem(Base):
    __tablename__ = 'whatsapp_mensagens'
    message_id = Column(String(512), primary_key=True)
    phone_number_id = Column(String(128), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    fingerprint_versao = Column(Integer, nullable=False, server_default='1')
    context_wamid = Column(String(512))
    resolucao = Column(String(24), nullable=False, server_default='HISTORICO')
    conversa_contextual_id = Column(Integer, ForeignKey('whatsapp_conversas_contextuais.id', ondelete='RESTRICT'))
    conversa_legada_id = Column(Integer, ForeignKey('whatsapp_conversas.id', ondelete='RESTRICT'))
    __table_args__ = (
        CheckConstraint('fingerprint_versao IN (1,2)', name='ck_wm_fingerprint_versao'),
        CheckConstraint("(resolucao IN ('HISTORICO','LEGADO_SEM_CONVERSA') AND conversa_contextual_id IS NULL AND conversa_legada_id IS NULL) OR (resolucao='CONTEXTUAL_ATUAL' AND conversa_contextual_id IS NOT NULL AND conversa_legada_id IS NULL) OR (resolucao='LEGADO_ATUAL' AND conversa_legada_id IS NOT NULL AND conversa_contextual_id IS NULL)", name='ck_wm_resolucao'),
    )
    resposta = Column(Text, nullable=False)
    enviado_em = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, nullable=False, server_default=func.now())
