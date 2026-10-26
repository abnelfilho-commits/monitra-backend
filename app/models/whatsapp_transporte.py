"""Transport evidence, never an authorization or routing decision."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, func
from app.database import Base

class WhatsAppMensagemRoteavel(Base):
    __tablename__ = 'whatsapp_mensagens_roteaveis'
    id = Column(Integer, primary_key=True)
    phone_number_id = Column(String(128), nullable=False)
    wamid = Column(String(512), nullable=False)
    destinatario_solicitado = Column(String(30), nullable=False)
    wa_id = Column(String(30))
    evidencia_estado = Column(String(16), nullable=False)
    conversa_contextual_id = Column(Integer, ForeignKey('whatsapp_conversas_contextuais.id', ondelete='RESTRICT'))
    conversa_legada_id = Column(Integer, ForeignKey('whatsapp_conversas.id', ondelete='RESTRICT'))
    origem = Column(String(32), nullable=False)
    observado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    __table_args__ = (
        UniqueConstraint('phone_number_id', 'wamid', name='uq_wmr_emissor_wamid'),
        CheckConstraint("length(trim(phone_number_id)) > 0 AND wamid LIKE 'wamid.%'", name='ck_wmr_identidade'),
        CheckConstraint("destinatario_solicitado ~ '^[0-9]{8,15}$'", name='ck_wmr_destino'),
        CheckConstraint("(conversa_contextual_id IS NOT NULL)::int + (conversa_legada_id IS NOT NULL)::int = 1", name='ck_wmr_conversa'),
        CheckConstraint("origem IN ('META_CONVITE','META_RESPOSTA')", name='ck_wmr_origem'),
        CheckConstraint("(evidencia_estado = 'VALIDA' AND wa_id IS NOT NULL AND wa_id ~ '^[0-9]{8,15}$') OR (evidencia_estado IN ('AUSENTE','INVALIDA') AND wa_id IS NULL)", name='ck_wmr_evidencia'),
    )
