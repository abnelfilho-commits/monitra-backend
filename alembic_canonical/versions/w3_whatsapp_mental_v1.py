"""WhatsApp MH: configuration and contextual conversations; frozen DDL."""
from alembic import op
revision = "w3_whatsapp_mental_v1"
down_revision = "w3_atendimento_mental_v1"
branch_labels = None
depends_on = None
from sqlalchemy import (Column, Integer, String, Date, DateTime, JSON, ForeignKey,
                        ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, text, func)
from sqlalchemy.orm import declarative_base
Base = declarative_base()

OPEN = "status IN ('AGUARDANDO_ACEITE','EM_ANDAMENTO')"


class AcompanhamentoWhatsApp(Base):
    __tablename__ = 'acompanhamentos_whatsapp'
    id = Column(Integer, primary_key=True)
    contexto_assistencial_id = Column(Integer, nullable=False)
    paciente_id = Column(Integer, nullable=False)
    telefone = Column(String(15), nullable=False)
    consentimento_status = Column(String(16), nullable=False, server_default='PENDENTE')
    consentido_em = Column(DateTime(timezone=True))
    revogado_em = Column(DateTime(timezone=True))
    frequencia = Column(String(16), nullable=False, server_default='SEMANAL')
    proximo_envio_em = Column(DateTime(timezone=True))
    status = Column(String(16), nullable=False, server_default='ATIVO')
    criado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['contexto_assistencial_id','paciente_id'], ['contextos_assistenciais.id','contextos_assistenciais.paciente_id'], ondelete='RESTRICT', name='fk_aw_contexto'),
        UniqueConstraint('contexto_assistencial_id', name='uq_aw_contexto'),
        UniqueConstraint('id','contexto_assistencial_id','paciente_id', name='uq_aw_identidade'),
        CheckConstraint("telefone ~ '^[0-9]{8,15}$'", name='ck_aw_telefone'),
        CheckConstraint("consentimento_status IN ('PENDENTE','CONSENTIDO','REVOGADO')", name='ck_aw_consentimento'),
        CheckConstraint("status IN ('ATIVO','PAUSADO','ENCERRADO')", name='ck_aw_status'),
        CheckConstraint("frequencia = 'SEMANAL'", name='ck_aw_frequencia'),
        Index('ix_aw_envio', 'status', 'proximo_envio_em'),
    )


class WhatsAppConversaContextual(Base):
    __tablename__ = 'whatsapp_conversas_contextuais'
    id = Column(Integer, primary_key=True)
    acompanhamento_whatsapp_id = Column(Integer, nullable=False)
    contexto_assistencial_id = Column(Integer, nullable=False)
    paciente_id = Column(Integer, nullable=False)
    telefone = Column(String(15), nullable=False)
    care_line = Column(String(32), nullable=False, server_default='MENTAL_HEALTH')
    etapa_atual = Column(String(32), nullable=False, server_default='ACEITE')
    respostas_json = Column(JSON, nullable=False, server_default=text("'{}'"))
    status = Column(String(24), nullable=False, server_default='AGUARDANDO_ACEITE')
    data_referencia = Column(Date, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    convite_enviado_em = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['acompanhamento_whatsapp_id','contexto_assistencial_id','paciente_id'], ['acompanhamentos_whatsapp.id','acompanhamentos_whatsapp.contexto_assistencial_id','acompanhamentos_whatsapp.paciente_id'], name='fk_wcc_acompanhamento', ondelete='RESTRICT'),
        CheckConstraint("telefone ~ '^[0-9]{8,15}$'", name='ck_wcc_telefone'),
        CheckConstraint("care_line = 'MENTAL_HEALTH'", name='ck_wcc_linha'),
        CheckConstraint("status IN ('AGUARDANDO_ACEITE','EM_ANDAMENTO','CONCLUIDA','EXPIRADA','CANCELADA')", name='ck_wcc_status'),
        CheckConstraint('expires_at > created_at', name='ck_wcc_janela'),
        Index('uq_wcc_aberta_acompanhamento','acompanhamento_whatsapp_id',unique=True,postgresql_where=text(OPEN)),
        Index('uq_wcc_aberta_telefone','telefone',unique=True,postgresql_where=text(OPEN)),
    )


def upgrade():
    # Resolve external FK targets without creating existing canonical tables.
    from sqlalchemy import Table, MetaData
    metadata = Base.metadata
    for name in ('usuarios', 'contextos_assistenciais'):
        Table(name, metadata, autoload_with=op.get_bind())
    AcompanhamentoWhatsApp.__table__.create(op.get_bind())
    WhatsAppConversaContextual.__table__.create(op.get_bind())


def downgrade():
    WhatsAppConversaContextual.__table__.drop(op.get_bind())
    AcompanhamentoWhatsApp.__table__.drop(op.get_bind())
