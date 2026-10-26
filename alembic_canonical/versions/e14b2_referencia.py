"""Add explicit-reference receipt decisions without rewriting historical evidence."""
from alembic import op
import sqlalchemy as sa
revision = 'e14b2_referencia'
down_revision = 'e14b1_transporte'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('whatsapp_mensagens_roteaveis', sa.Column('legado_estado_sha256', sa.String(64)))
    op.add_column('whatsapp_mensagens', sa.Column('resolucao_motivo', sa.String(40)))
    op.add_column('whatsapp_mensagens', sa.Column('legado_estado_sha256', sa.String(64)))
    op.drop_constraint('ck_wm_resolucao', 'whatsapp_mensagens', type_='check')
    op.create_check_constraint('ck_wm_resolucao', 'whatsapp_mensagens', "(resolucao IN ('HISTORICO','LEGADO_SEM_CONVERSA','REFERENCIA_RECUSADA') AND conversa_contextual_id IS NULL AND conversa_legada_id IS NULL) OR (resolucao IN ('CONTEXTUAL_ATUAL','REFERENCIA_CONTEXTUAL') AND conversa_contextual_id IS NOT NULL AND conversa_legada_id IS NULL) OR (resolucao IN ('LEGADO_ATUAL','REFERENCIA_LEGADA') AND conversa_legada_id IS NOT NULL AND conversa_contextual_id IS NULL)")

def downgrade():
    raise RuntimeError('Transport evidence removal requires an approved recovery procedure')
