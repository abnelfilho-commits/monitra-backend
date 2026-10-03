"""Assistive contexts; no backfill, grants or clinical activation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ExcludeConstraint

revision = 'w1a_contexto_v1'
down_revision = 'f1_economia_v1'
branch_labels = None
depends_on = None


def upgrade():
    # btree_gist already belongs to G1; preserve its lifecycle.
    op.create_unique_constraint('uq_paciente_instituicao_identidade', 'paciente_instituicoes',
                                ['id', 'paciente_id', 'instituicao_id'], schema='public')
    op.create_table('contextos_assistenciais',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('paciente_instituicao_id', sa.Integer(), nullable=False),
        sa.Column('paciente_id', sa.Integer(), nullable=False),
        sa.Column('instituicao_id', sa.Integer(), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=False),
        sa.Column('data_fim', sa.Date()),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('criado_por_usuario_id', sa.Integer(), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.ForeignKeyConstraint(['paciente_instituicao_id', 'paciente_id', 'instituicao_id'],
            ['public.paciente_instituicoes.id', 'public.paciente_instituicoes.paciente_id', 'public.paciente_instituicoes.instituicao_id'],
            name='fk_contexto_vinculo_identidade', ondelete='RESTRICT', onupdate='RESTRICT'),
        sa.CheckConstraint('data_fim IS NULL OR data_fim >= data_inicio', name='ck_contexto_periodo'),
        ExcludeConstraint(('paciente_id', '='), ('instituicao_id', '='),
            (sa.text("daterange(data_inicio, data_fim, '[]')"), '&&'),
            where=sa.text('ativo'), using='gist', name='ex_contexto_vigencia'), schema='public')
    for column in ('paciente_instituicao_id', 'paciente_id', 'instituicao_id'):
        op.create_index('ix_contextos_assistenciais_' + column, 'contextos_assistenciais', [column], schema='public')
    op.create_table('contexto_assistencial_linhas',
        sa.Column('id', sa.Integer(), sa.Identity(), primary_key=True),
        sa.Column('contexto_assistencial_id', sa.Integer(), sa.ForeignKey('public.contextos_assistenciais.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('modulo_id', sa.Integer(), sa.ForeignKey('public.modulos_clinicos.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint('contexto_assistencial_id', 'modulo_id', name='uq_contexto_linha'), schema='public')
    for column in ('contexto_assistencial_id', 'modulo_id'):
        op.create_index('ix_contexto_assistencial_linhas_' + column, 'contexto_assistencial_linhas', [column], schema='public')


def downgrade():
    c = op.get_bind()
    if c.exec_driver_sql('SHOW transaction_isolation').scalar() != 'read committed':
        raise RuntimeError('W1A_READ_COMMITTED_REQUIRED')
    c.exec_driver_sql('LOCK TABLE public.contextos_assistenciais, public.contexto_assistencial_linhas IN ACCESS EXCLUSIVE MODE')
    if c.exec_driver_sql('SELECT EXISTS (SELECT 1 FROM public.contextos_assistenciais) OR EXISTS (SELECT 1 FROM public.contexto_assistencial_linhas)').scalar():
        raise RuntimeError('W1A_DOWNGRADE_BLOCKED_CONTEXTS')
    op.drop_table('contexto_assistencial_linhas', schema='public')
    op.drop_table('contextos_assistenciais', schema='public')
    op.drop_constraint('uq_paciente_instituicao_identidade', 'paciente_instituicoes', type_='unique', schema='public')
