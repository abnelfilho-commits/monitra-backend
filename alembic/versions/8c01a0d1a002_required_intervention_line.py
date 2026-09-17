"""Require explicit intervention lines; never infer or erase shared data."""
from alembic import op
import sqlalchemy as sa

revision = '8c01a0d1a002'
down_revision = '8c01a0d1a001'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT count(*) FROM intervencoes WHERE modulo_id IS NULL')).scalar():
        raise RuntimeError('Sanitize non-production interventions with explicit approval before upgrading; no automatic backfill.')
    op.alter_column('intervencoes', 'modulo_id', existing_type=sa.Integer(), nullable=False)


def downgrade():
    op.alter_column('intervencoes', 'modulo_id', existing_type=sa.Integer(), nullable=True)
