"""Explicit digital-account authorization; no temporal validity or legacy grants."""
from alembic import op
import sqlalchemy as sa

revision = 'g2c1_autorizacao_v1'
down_revision = 'g2b1_institucional_v1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('usuario_instituicao_acessos',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('instituicao_id', sa.Integer(), sa.ForeignKey('public.instituicoes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('perfil_institucional', sa.String(16), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.UniqueConstraint('usuario_id', 'instituicao_id', name='uq_usuario_instituicao_acesso'),
        sa.CheckConstraint("perfil_institucional IN ('GESTOR', 'PROFISSIONAL', 'SUPORTE')", name='ck_acesso_perfil_institucional'),
        schema='public')
    op.create_index('ix_usuario_instituicao_acessos_instituicao_id', 'usuario_instituicao_acessos', ['instituicao_id'], schema='public')


def downgrade():
    c = op.get_bind()
    if c.execute(sa.text('SHOW transaction_isolation')).scalar() != 'read committed':
        raise RuntimeError('G2C1_READ_COMMITTED_REQUIRED')
    c.execute(sa.text('LOCK TABLE public.usuario_instituicao_acessos IN ACCESS EXCLUSIVE MODE'))
    if c.execute(sa.text('SELECT EXISTS (SELECT 1 FROM public.usuario_instituicao_acessos)')).scalar():
        raise RuntimeError('G2C1_DOWNGRADE_BLOCKED_AUTHORIZATIONS')
    op.drop_table('usuario_instituicao_acessos', schema='public')
