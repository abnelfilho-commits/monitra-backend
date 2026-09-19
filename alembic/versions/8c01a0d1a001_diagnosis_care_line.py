"""Explicit diagnosis line; require approved sanitation of test data."""
from alembic import op
import sqlalchemy as sa

revision = '8c01a0d1a001'
down_revision = '8c01a0d1a000'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().execute(sa.text('SELECT count(*) FROM diagnosticos WHERE modulo_id IS NULL')).scalar():
        raise RuntimeError('Sanitize non-production diagnoses with explicit approval before upgrading.')
    op.alter_column('diagnosticos', 'modulo_id', existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key('fk_diagnosticos_modulo_id', 'diagnosticos',
                          'modulos_clinicos', ['modulo_id'], ['id'])
    op.create_index('ix_diagnosticos_paciente_modulo', 'diagnosticos', ['paciente_id', 'modulo_id'])


def downgrade():
    # Do not silently destroy clinically meaningful associations.
    raise RuntimeError('Diagnosis care-line downgrade requires an explicit data-preservation plan.')
