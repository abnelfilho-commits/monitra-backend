"""Private manual request ledger; transport/delivery evidence remains in D9.2."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, func
from app.database import Base

class WhatsAppSolicitacaoManual(Base):
    __tablename__ = 'whatsapp_solicitacoes_manuais'
    id = Column(Integer, primary_key=True)
    instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False)
    acompanhamento_id = Column(Integer, ForeignKey('acompanhamentos_whatsapp.id', ondelete='RESTRICT'), nullable=False)
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    chave = Column(String(128), nullable=False)
    motivo = Column(String(40), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    estado = Column(String(16), nullable=False, server_default='PREPARADO')
    conversa_id = Column(Integer, ForeignKey('whatsapp_conversas_contextuais.id', ondelete='RESTRICT'), nullable=False, unique=True)
    tentativa_id = Column(Integer, ForeignKey('whatsapp_convite_envios.id', ondelete='RESTRICT'), unique=True)
    template_nome = Column(String(512), nullable=False)
    template_idioma = Column(String(32), nullable=False)
    __table_args__ = (
        UniqueConstraint('instituicao_id', 'usuario_id', 'chave', name='uq_wsm_idempotencia'),
        CheckConstraint("estado IN ('PREPARADO','VINCULADO')", name='ck_wsm_estado'),
        CheckConstraint("motivo IN ('ACOMPANHAMENTO_EXTRAORDINARIO','SOLICITACAO_DA_PESSOA')", name='ck_wsm_motivo'),
        CheckConstraint("length(chave) BETWEEN 16 AND 128", name='ck_wsm_chave'),
        CheckConstraint("(estado = 'PREPARADO' AND tentativa_id IS NULL) OR (estado = 'VINCULADO' AND tentativa_id IS NOT NULL)", name='ck_wsm_vinculo'),
    )
