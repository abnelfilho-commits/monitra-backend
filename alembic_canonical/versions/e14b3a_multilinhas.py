"""Dormant multilines decision audit. No routing activation or index removal."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'e14b3a_multilinhas'
down_revision = 'e14b2_referencia'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('whatsapp_resolucoes',
        sa.Column('message_id', sa.String(512), sa.ForeignKey('whatsapp_mensagens.message_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('versao', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('decisao', postgresql.JSONB(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('versao = 1', name='ck_wr_versao'))

    op.execute("""CREATE FUNCTION wr_preservar_historico() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'WHATSAPP_ROUTING_HISTORY_IMMUTABLE'; END; $$""")
    op.execute("""CREATE TRIGGER wr_historico_imutavel BEFORE UPDATE OR DELETE ON whatsapp_resolucoes
        FOR EACH ROW EXECUTE FUNCTION wr_preservar_historico()""")


def downgrade():
    raise RuntimeError('Routing evidence removal requires an approved recovery procedure')
