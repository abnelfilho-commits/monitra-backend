"""Append-only-by-service routing proposal, separate from executed ingress receipt."""
from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class WhatsAppResolucao(Base):
    __tablename__ = 'whatsapp_resolucoes'
    message_id = Column(String(512), ForeignKey('whatsapp_mensagens.message_id', ondelete='RESTRICT'), primary_key=True)
    versao = Column(Integer, nullable=False, server_default='1')
    decisao = Column(JSONB, nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (CheckConstraint('versao = 1', name='ck_wr_versao'),)
