"""Durable WhatsApp receipt and explicit conversation care-line context.

Revision ID: 8c01a0d1a004
Revises: 8c01a0d1a003
"""
from alembic import op
import sqlalchemy as sa
revision = '8c01a0d1a004'
down_revision = '8c01a0d1a003'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('whatsapp_mensagens',
        sa.Column('message_id', sa.String(512), primary_key=True),
        sa.Column('phone_number_id', sa.String(128), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('resposta', sa.Text(), nullable=False),
        sa.Column('enviado_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False))
    op.add_column('whatsapp_conversas', sa.Column('care_line', sa.String(32), nullable=True))
    # Existing conversations were produced exclusively by the Neuro questionnaire.
    # This is source provenance, never inferred from patient membership.
    op.execute("UPDATE whatsapp_conversas SET care_line = 'NEURO'")


def downgrade():
    op.drop_column('whatsapp_conversas', 'care_line')
    op.drop_table('whatsapp_mensagens')
