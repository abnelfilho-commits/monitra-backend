"""Weekly preferences only; existing schedules stay unconfigured and inactive."""
from alembic import op
import sqlalchemy as sa

revision = 'mh_weekly_config_v1'
down_revision = 'e14b_close_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('acompanhamentos_whatsapp', sa.Column('dia_semana', sa.Integer()))
    op.add_column('acompanhamentos_whatsapp', sa.Column('horario_local', sa.Time(timezone=False)))
    op.add_column('acompanhamentos_whatsapp', sa.Column('programacao_ativa', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('acompanhamentos_whatsapp', sa.Column('configurado_por_usuario_id', sa.Integer()))
    op.create_foreign_key('fk_aw_configurador', 'acompanhamentos_whatsapp', 'usuarios', ['configurado_por_usuario_id'], ['id'], ondelete='RESTRICT')
    op.create_check_constraint('ck_aw_dia_semana', 'acompanhamentos_whatsapp', 'dia_semana BETWEEN 0 AND 6')
    op.create_check_constraint('ck_aw_programacao', 'acompanhamentos_whatsapp', '(dia_semana IS NULL AND horario_local IS NULL AND configurado_por_usuario_id IS NULL AND NOT programacao_ativa) OR (dia_semana IS NOT NULL AND horario_local IS NOT NULL AND configurado_por_usuario_id IS NOT NULL)')


def downgrade():
    # Do not silently lose preferences or re-enable legacy dispatch for paused rows.
    raise RuntimeError('Weekly scheduling requires forward recovery')
