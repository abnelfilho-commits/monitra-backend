"""Add authenticated authorship without changing historical diagnoses."""
from alembic import op
import sqlalchemy as sa

revision = 'w3_diagnostico_autoria_v1'
down_revision = 'capacidade_reconciliacao_v1'
branch_labels = None
depends_on = None


def upgrade():
    for column, target in (('registrador_usuario_id', 'usuarios'), ('registrador_profissional_id', 'profissionais')):
        op.add_column('diagnosticos', sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key('fk_diagnosticos_' + column, 'diagnosticos', target, [column], ['id'], ondelete='RESTRICT')


def downgrade():
    if op.get_bind().execute(sa.text("SHOW transaction_isolation")).scalar() != "read committed":
        raise RuntimeError("DIAGNOSIS_DOWNGRADE_REQUIRES_READ_COMMITTED")
    op.execute("LOCK TABLE diagnosticos IN ACCESS EXCLUSIVE MODE")
    if op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM diagnosticos WHERE registrador_usuario_id IS NOT NULL OR registrador_profissional_id IS NOT NULL)')).scalar():
        raise RuntimeError('DIAGNOSIS_AUTHORSHIP_PRESENT')
    for column in ('registrador_profissional_id', 'registrador_usuario_id'):
        op.drop_constraint('fk_diagnosticos_' + column, 'diagnosticos', type_='foreignkey')
        op.drop_column('diagnosticos', column)
