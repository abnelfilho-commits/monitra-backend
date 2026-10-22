"""D9.2-A additive invitation transport persistence; frozen DDL."""
from alembic import op
revision = 'd92a_whatsapp_persistencia'
down_revision = 'w3_whatsapp_mental_v1'
branch_labels = None
depends_on = None
"""Transport persistence only; never changes consent or initiates delivery."""
from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey,
                        ForeignKeyConstraint, UniqueConstraint, CheckConstraint,
                        Index, func)
from sqlalchemy.orm import declarative_base
Base = declarative_base()


class WhatsAppConviteEnvio(Base):
    __tablename__ = 'whatsapp_convite_envios'
    id = Column(Integer, primary_key=True)
    conversa_id = Column(Integer, ForeignKey('whatsapp_conversas_contextuais.id', ondelete='RESTRICT'), nullable=False)
    tentativa = Column(Integer, nullable=False)
    correlacao_id = Column(String(36), nullable=False, unique=True)
    phone_number_id = Column(String(128), nullable=False)
    wamid = Column(String(512))
    estado = Column(String(16), nullable=False, server_default='PREPARADO')
    preparado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    iniciado_em = Column(DateTime(timezone=True))
    confirmado_em = Column(DateTime(timezone=True))
    graph_http_status = Column(Integer)
    meta_error_code = Column(Integer)
    meta_error_subcode = Column(Integer)
    motivo_sanitizado = Column(String(256))
    __table_args__ = (
        UniqueConstraint('conversa_id', 'tentativa', name='uq_wce_conversa_tentativa'),
        UniqueConstraint('phone_number_id', 'wamid', name='uq_wce_emissor_wamid'),
        UniqueConstraint('id', 'phone_number_id', 'wamid', name='uq_wce_correlacao'),
        CheckConstraint('tentativa > 0', name='ck_wce_tentativa'),
        CheckConstraint("estado IN ('PREPARADO','EM_EXECUCAO','ACEITO','REJEITADO','INCERTO')", name='ck_wce_estado'),
        CheckConstraint("length(trim(phone_number_id)) > 0 AND length(trim(correlacao_id)) > 0", name='ck_wce_identidade'),
        CheckConstraint("wamid IS NULL OR length(trim(wamid)) > 0", name='ck_wce_wamid'),
        CheckConstraint("estado <> 'ACEITO' OR (wamid IS NOT NULL AND confirmado_em IS NOT NULL)", name='ck_wce_aceito'),
        CheckConstraint('graph_http_status IS NULL OR graph_http_status BETWEEN 100 AND 599', name='ck_wce_http'),
        CheckConstraint('(meta_error_code IS NULL OR meta_error_code >= 0) AND (meta_error_subcode IS NULL OR meta_error_subcode >= 0)', name='ck_wce_erros'),
        Index('ix_wce_estado', 'estado'),
    )


class WhatsAppConviteStatusEvento(Base):
    __tablename__ = 'whatsapp_convite_status_eventos'
    id = Column(Integer, primary_key=True)
    envio_id = Column(Integer)
    phone_number_id = Column(String(128), nullable=False)
    wamid = Column(String(512), nullable=False)
    status = Column(String(16), nullable=False)
    evento_em = Column(DateTime(timezone=True), nullable=False)
    recebido_em = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    deduplicacao_chave = Column(String(64), nullable=False, unique=True)
    meta_error_code = Column(Integer)
    meta_error_subcode = Column(Integer)
    motivo_sanitizado = Column(String(256))
    __table_args__ = (
        ForeignKeyConstraint(['envio_id','phone_number_id','wamid'],
                             ['whatsapp_convite_envios.id','whatsapp_convite_envios.phone_number_id','whatsapp_convite_envios.wamid'],
                             ondelete='RESTRICT', name='fk_wcse_correlacao'),
        CheckConstraint("status IN ('sent','delivered','read','failed')", name='ck_wcse_status'),
        CheckConstraint("length(trim(phone_number_id)) > 0 AND length(trim(wamid)) > 0", name='ck_wcse_identidade'),
        CheckConstraint('length(deduplicacao_chave) = 64', name='ck_wcse_chave'),
        CheckConstraint('(meta_error_code IS NULL OR meta_error_code >= 0) AND (meta_error_subcode IS NULL OR meta_error_subcode >= 0)', name='ck_wcse_erros'),
        Index('ix_wcse_mensagem_tempo', 'phone_number_id', 'wamid', 'evento_em'),
        Index('ix_wcse_envio', 'envio_id'),
    )


def upgrade():
    from sqlalchemy import Table
    Table('whatsapp_conversas_contextuais', Base.metadata, autoload_with=op.get_bind())
    WhatsAppConviteEnvio.__table__.create(op.get_bind())
    WhatsAppConviteStatusEvento.__table__.create(op.get_bind())


def downgrade():
    raise RuntimeError('D9.2 delivery evidence must be preserved; destructive downgrade requires a separately approved procedure')
