"""Add authenticated authorship without changing historical interventions."""
from alembic import op
import sqlalchemy as sa

revision = 'w3_intervencao_autoria_v1'
down_revision = 'w3_diagnostico_autoria_v1'
branch_labels = None
depends_on = None


def upgrade():
    for column, target in (('registrador_profissional_id', 'profissionais'),):
        op.add_column('intervencoes', sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key('fk_intervencoes_' + column, 'intervencoes', target, [column], ['id'], ondelete='RESTRICT')


def downgrade():
    if op.get_bind().execute(sa.text("SHOW transaction_isolation")).scalar() != "read committed":
        raise RuntimeError("INTERVENTION_DOWNGRADE_REQUIRES_READ_COMMITTED")
    op.execute("LOCK TABLE intervencoes IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM intervencoes WHERE registrador_profissional_id IS NOT NULL)')).scalar():
        raise RuntimeError('INTERVENTION_AUTHORSHIP_PRESENT')
    for column in ('registrador_profissional_id',):
        op.drop_constraint('fk_intervencoes_' + column, 'intervencoes', type_='foreignkey')
        op.drop_column('intervencoes', column)
