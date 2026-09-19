"""Add diagnosis context before an explicit, operator-approved remediation.

Stop at this revision for databases with historical diagnoses. No line is
inferred here. Revision 001 fails closed until every row has explicit context.
"""
from alembic import op
import sqlalchemy as sa

revision = '8c01a0d1a000'
down_revision = '5a01c7e2d903'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('diagnosticos', sa.Column('modulo_id', sa.Integer(), nullable=True))


def downgrade():
    if op.get_bind().execute(sa.text(
            'SELECT count(*) FROM diagnosticos WHERE modulo_id IS NOT NULL')).scalar():
        raise RuntimeError('Diagnosis context exists; an explicit preservation plan is required.')
    op.drop_column('diagnosticos', 'modulo_id')
