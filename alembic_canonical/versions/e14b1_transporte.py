"""Add transport evidence without enabling contextual routing."""
from alembic import op
import sqlalchemy as sa
revision = 'e14b1_transporte'
down_revision = 'd92e12c_autorizacao_whatsapp'
branch_labels = None
depends_on = None
"""Transport evidence, never an authorization or routing decision."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, func
from sqlalchemy.orm import declarative_base
Base = declarative_base()

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

def upgrade():
    bind = op.get_bind()
    for name in ('whatsapp_conversas_contextuais', 'whatsapp_conversas'):
        sa.Table(name, Base.metadata, autoload_with=bind)
    WhatsAppMensagemRoteavel.__table__.create(bind)
    op.add_column('whatsapp_mensagens', sa.Column('fingerprint_versao', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('whatsapp_mensagens', sa.Column('context_wamid', sa.String(512)))
    op.add_column('whatsapp_mensagens', sa.Column('resolucao', sa.String(24), nullable=False, server_default='HISTORICO'))
    for col, target in (('conversa_contextual_id','whatsapp_conversas_contextuais'),('conversa_legada_id','whatsapp_conversas')):
        op.add_column('whatsapp_mensagens', sa.Column(col, sa.Integer()))
        op.create_foreign_key('fk_wm_'+col, 'whatsapp_mensagens', target, [col], ['id'], ondelete='RESTRICT')
    op.create_check_constraint('ck_wm_fingerprint_versao','whatsapp_mensagens','fingerprint_versao IN (1,2)')
    op.create_check_constraint('ck_wm_resolucao','whatsapp_mensagens', "(resolucao IN ('HISTORICO','LEGADO_SEM_CONVERSA') AND conversa_contextual_id IS NULL AND conversa_legada_id IS NULL) OR (resolucao='CONTEXTUAL_ATUAL' AND conversa_contextual_id IS NOT NULL AND conversa_legada_id IS NULL) OR (resolucao='LEGADO_ATUAL' AND conversa_legada_id IS NOT NULL AND conversa_contextual_id IS NULL)")

def downgrade():
    raise RuntimeError('Transport evidence removal requires an approved recovery procedure')
