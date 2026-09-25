"""Explicit patient institutional context and independent institutional provenance."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'g2b1_institucional_v1'
down_revision = 'g2a3_identidade_v1'
branch_labels = None
depends_on = None


def upgrade():
    c = op.get_bind()
    if c.execute(sa.text('SHOW transaction_isolation')).scalar() != 'read committed':
        raise RuntimeError('G2.B.1 requires READ COMMITTED')
    # The new FK only covers a new nullable column: no legacy association is
    # guessed, validated as canonical, or rewritten. Existing G1 constraints stay.
    c.execute(sa.text('LOCK TABLE public.paciente_profissionais IN ACCESS EXCLUSIVE MODE'))
    if c.execute(sa.text("""SELECT to_regclass('public.institucional_operacoes') IS NOT NULL
        OR EXISTS (SELECT 1 FROM pg_attribute WHERE attrelid='public.paciente_profissionais'::regclass
          AND attname='paciente_instituicao_id' AND NOT attisdropped)
        OR to_regclass('public.ix_paciente_profissionais_paciente_instituicao_id') IS NOT NULL
        OR EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.paciente_profissionais'::regclass
          AND conname='fk_paciente_profissionais_paciente_instituicao')""")).scalar():
        raise RuntimeError('G2B1_STOP_PREEXISTING_OBJECT')
    op.add_column('paciente_profissionais', sa.Column('paciente_instituicao_id', sa.Integer(), nullable=True), schema='public')
    op.create_foreign_key('fk_paciente_profissionais_paciente_instituicao', 'paciente_profissionais',
        'paciente_instituicoes', ['paciente_instituicao_id'], ['id'], source_schema='public', referent_schema='public', ondelete='RESTRICT')
    op.create_index('ix_paciente_profissionais_paciente_instituicao_id', 'paciente_profissionais', ['paciente_instituicao_id'], unique=False, schema='public')
    op.create_table('institucional_operacoes',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('ator_usuario_id', sa.Integer(), sa.ForeignKey('public.usuarios.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('instituicao_id', sa.Integer(), sa.ForeignKey('public.instituicoes.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('operacao', sa.String(32), nullable=False),
        sa.Column('tipo_alvo', sa.String(32), nullable=False),
        sa.Column('paciente_instituicao_id', sa.Integer(), sa.ForeignKey('public.paciente_instituicoes.id', ondelete='RESTRICT')),
        sa.Column('profissional_instituicao_id', sa.Integer(), sa.ForeignKey('public.profissional_instituicoes.id', ondelete='RESTRICT')),
        sa.Column('paciente_profissional_id', sa.Integer(), sa.ForeignKey('public.paciente_profissionais.id', ondelete='RESTRICT')),
        sa.Column('motivo', sa.Text(), nullable=False),
        sa.Column('resultado', sa.String(16), nullable=False),
        sa.Column('estado_anterior', postgresql.JSONB()),
        sa.Column('estado_final', postgresql.JSONB(), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("(operacao = 'CREATE_LINK' AND resultado = 'CREATED') OR (operacao = 'CLOSE_LINK' AND resultado = 'CLOSED') OR (operacao = 'INVALIDATE_LINK' AND resultado = 'INVALIDATED')", name='ck_institucional_operacao_resultado'),
        sa.CheckConstraint("(tipo_alvo = 'PACIENTE_INSTITUICAO' AND paciente_instituicao_id IS NOT NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NULL) OR (tipo_alvo = 'PROFISSIONAL_INSTITUICAO' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NOT NULL AND paciente_profissional_id IS NULL) OR (tipo_alvo = 'PACIENTE_PROFISSIONAL' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NOT NULL)", name='ck_institucional_operacao_alvo'),
        sa.CheckConstraint('length(trim(motivo)) > 0', name='ck_institucional_operacao_motivo'),
        schema='public')
    op.create_index('ix_institucional_operacoes_instituicao_id', 'institucional_operacoes', ['instituicao_id'], unique=False, schema='public')


def downgrade():
    c = op.get_bind()
    if c.execute(sa.text('SHOW transaction_isolation')).scalar() != 'read committed':
        raise RuntimeError('G2.B.1 downgrade requires READ COMMITTED')
    c.execute(sa.text('LOCK TABLE public.paciente_profissionais, public.institucional_operacoes IN ACCESS EXCLUSIVE MODE'))
    if c.execute(sa.text('''SELECT EXISTS (SELECT 1 FROM public.institucional_operacoes)
        OR EXISTS (SELECT 1 FROM public.paciente_profissionais WHERE paciente_instituicao_id IS NOT NULL)''')).scalar():
        raise RuntimeError('G2B1_DOWNGRADE_BLOCKED_CANONICAL_INFORMATION')
    op.drop_table('institucional_operacoes', schema='public')
    op.drop_index('ix_paciente_profissionais_paciente_instituicao_id', table_name='paciente_profissionais', schema='public')
    op.drop_constraint('fk_paciente_profissionais_paciente_instituicao', 'paciente_profissionais', type_='foreignkey', schema='public')
    op.drop_column('paciente_profissionais', 'paciente_instituicao_id', schema='public')
