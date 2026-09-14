"""Durable module association for new institutional interventions; no backfill."""
from alembic import op
import sqlalchemy as sa

revision = '5a01c7e2d903'
down_revision = 'fb27d5139e1e'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('intervencoes', sa.Column('modulo_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_intervencoes_modulo_id', 'intervencoes',
                          'modulos_clinicos', ['modulo_id'], ['id'])


def downgrade():
    op.drop_constraint('fk_intervencoes_modulo_id', 'intervencoes', type_='foreignkey')
    op.drop_column('intervencoes', 'modulo_id')
