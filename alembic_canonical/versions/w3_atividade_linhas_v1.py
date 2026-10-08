"""Add canonical activity applicability; preserve the legacy module column."""
from alembic import op
import sqlalchemy as sa

revision = 'w3_atividade_linhas_v1'
down_revision = 'w3_cbi_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('atividade_modulos',
        sa.Column('atividade_id', sa.Integer(), nullable=False),
        sa.Column('modulo_id', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('atividade_id', 'modulo_id'),
        sa.ForeignKeyConstraint(['atividade_id'], ['atividades_terapeuticas.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['modulo_id'], ['modulos_clinicos.id'], ondelete='RESTRICT'))
    op.create_index('ix_atividade_modulos_modulo_atividade', 'atividade_modulos', ['modulo_id', 'atividade_id'])
    op.execute('INSERT INTO atividade_modulos(atividade_id, modulo_id) SELECT id, modulo_id FROM atividades_terapeuticas WHERE modulo_id IS NOT NULL')


def downgrade():
    op.execute('LOCK TABLE atividades_terapeuticas, atividade_modulos IN ACCESS EXCLUSIVE MODE')
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM atividade_modulos a JOIN atividades_terapeuticas t ON t.id=a.atividade_id WHERE a.modulo_id IS DISTINCT FROM t.modulo_id)")).scalar():
        raise RuntimeError('ACTIVITY_APPLICABILITY_CANNOT_BE_REPRESENTED_BY_LEGACY')
    op.drop_table('atividade_modulos')
