"""Frozen W1B physical contract; no operational policy or automatic grants."""
from sqlalchemy import (Column, Integer, String, Text, Date, DateTime, Identity,
                        ForeignKey, ForeignKeyConstraint, UniqueConstraint,
                        CheckConstraint, Index, func, text)
from sqlalchemy.dialects.postgresql import ExcludeConstraint, UUID
from sqlalchemy.orm import declarative_base
from sqlalchemy import MetaData, Table
from alembic import op

Base = declarative_base(metadata=MetaData(schema="public", naming_convention={"ix": "ix_%(table_name)s_%(column_0_name)s"}))

CAPACIDADES = ('ASSISTENCIAL_LER', 'ASSISTENCIAL_REGISTRAR', 'CONTEXTO_ADMINISTRAR')


def grouped_event(prefix, fields):
    empty = ' AND '.join(f'{f} IS NULL' for f in fields)
    full = ' AND '.join(f'{f} IS NOT NULL' for f in fields)
    return CheckConstraint(f'({empty}) OR ({full})', name=prefix)


class ContextoProfissional(Base):
    __tablename__ = 'contexto_profissionais'
    id = Column(Integer, Identity(), primary_key=True)
    instituicao_id = Column(Integer, nullable=False, index=True)
    contexto_assistencial_id = Column(Integer, nullable=False, index=True)
    profissional_instituicao_id = Column(Integer, nullable=False, index=True)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date)
    criado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    motivo_criacao = Column(Text, nullable=False)
    encerrado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    encerrado_em = Column(DateTime(timezone=True))
    motivo_encerramento = Column(Text)
    invalidado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    invalidado_em = Column(DateTime(timezone=True))
    motivo_invalidacao = Column(Text)
    __table_args__ = (
        ForeignKeyConstraint(['contexto_assistencial_id', 'instituicao_id'],
            ['contextos_assistenciais.id', 'contextos_assistenciais.instituicao_id'],
            name='fk_participacao_contexto_instituicao', ondelete='RESTRICT', onupdate='RESTRICT'),
        ForeignKeyConstraint(['profissional_instituicao_id', 'instituicao_id'],
            ['profissional_instituicoes.id', 'profissional_instituicoes.instituicao_id'],
            name='fk_participacao_profissional_instituicao', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint('data_fim IS NULL OR data_fim >= data_inicio', name='ck_participacao_periodo'),
        grouped_event('ck_participacao_encerramento', ('encerrado_por_usuario_id','encerrado_em','motivo_encerramento')),
        grouped_event('ck_participacao_invalidacao', ('invalidado_por_usuario_id','invalidado_em','motivo_invalidacao')),
        CheckConstraint('encerrado_em IS NULL OR data_fim IS NOT NULL', name='ck_participacao_encerramento_fim'),
        *(CheckConstraint(f'{f} IS NULL OR length(trim({f})) > 0', name='ck_participacao_'+f)
          for f in ('motivo_criacao','motivo_encerramento','motivo_invalidacao')),
        ExcludeConstraint(('contexto_assistencial_id', '='), ('profissional_instituicao_id', '='),
            (text("daterange(data_inicio, data_fim, '[]')"), '&&'),
            where=text('invalidado_em IS NULL'), using='gist', name='ex_participacao_vigencia').ddl_if(dialect='postgresql'),
    )


def permission_constraints(prefix, capability, scope):
    return (
        ForeignKeyConstraint(['usuario_instituicao_acesso_id', 'instituicao_id'],
            ['usuario_instituicao_acessos.id', 'usuario_instituicao_acessos.instituicao_id'],
            name='fk_'+prefix+'_raiz_instituicao', ondelete='RESTRICT', onupdate='RESTRICT'),
        ForeignKeyConstraint(['contexto_assistencial_id', 'instituicao_id'],
            ['contextos_assistenciais.id', 'contextos_assistenciais.instituicao_id'],
            name='fk_'+prefix+'_contexto_instituicao', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint(capability+' IN '+str(CAPACIDADES), name='ck_'+prefix+'_capacidade'),
        CheckConstraint(f"({scope} = 'INSTITUICAO' AND contexto_assistencial_id IS NULL) OR "
                        f"({scope} = 'CONTEXTO' AND contexto_assistencial_id IS NOT NULL)", name='ck_'+prefix+'_escopo'),
        grouped_event('ck_'+prefix+'_revogacao', ('revogado_por_usuario_id','revogado_em','motivo_revogacao','revogacao_origem')),
        CheckConstraint('length(trim(motivo_concessao)) > 0', name='ck_'+prefix+'_motivo_concessao'),
        CheckConstraint('motivo_revogacao IS NULL OR length(trim(motivo_revogacao)) > 0', name='ck_'+prefix+'_motivo_revogacao'),
        CheckConstraint('revogacao_origem IS NULL OR length(trim(revogacao_origem)) > 0', name='ck_'+prefix+'_revogacao_origem'),
        Index('uq_'+prefix+'_instituicao_vigente', 'usuario_instituicao_acesso_id', capability,
              unique=True, postgresql_where=text("revogado_em IS NULL AND "+scope+" = 'INSTITUICAO'")),
        Index('uq_'+prefix+'_contexto_vigente', 'usuario_instituicao_acesso_id', capability, 'contexto_assistencial_id',
              unique=True, postgresql_where=text("revogado_em IS NULL AND "+scope+" = 'CONTEXTO'")),
    )


class AutoridadeDelegacao(Base):
    __tablename__ = 'autoridades_delegacao'
    id = Column(Integer, Identity(), primary_key=True)
    usuario_instituicao_acesso_id = Column(Integer, nullable=False, index=True)
    instituicao_id = Column(Integer, nullable=False, index=True)
    capacidade_delegavel = Column(String(32), nullable=False)
    envelope_tipo = Column(String(16), nullable=False)
    contexto_assistencial_id = Column(Integer, index=True)
    origem = Column(String(16), nullable=False)
    operacao_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    concedido_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    concedido_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    motivo_concessao = Column(Text, nullable=False)
    revogado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    revogado_em = Column(DateTime(timezone=True))
    motivo_revogacao = Column(Text)
    revogacao_origem = Column(String(32))
    __table_args__ = permission_constraints('autoridade', 'capacidade_delegavel', 'envelope_tipo') + (
        UniqueConstraint('id', 'instituicao_id', name='uq_autoridade_instituicao'),
        CheckConstraint("origem IN ('BOOTSTRAP', 'RECOVERY')", name='ck_autoridade_origem'),
    )


class ConcessaoAssistencial(Base):
    __tablename__ = 'concessoes_assistenciais'
    id = Column(Integer, Identity(), primary_key=True)
    usuario_instituicao_acesso_id = Column(Integer, nullable=False, index=True)
    instituicao_id = Column(Integer, nullable=False, index=True)
    capacidade = Column(String(32), nullable=False)
    escopo_tipo = Column(String(16), nullable=False)
    contexto_assistencial_id = Column(Integer, index=True)
    autoridade_delegacao_id = Column(Integer, index=True)
    concedido_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    concedido_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    motivo_concessao = Column(Text, nullable=False)
    revogado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    revogado_em = Column(DateTime(timezone=True))
    motivo_revogacao = Column(Text)
    revogacao_origem = Column(String(32))
    __table_args__ = permission_constraints('concessao', 'capacidade', 'escopo_tipo') + (
        ForeignKeyConstraint(['autoridade_delegacao_id', 'instituicao_id'],
            ['autoridades_delegacao.id', 'autoridades_delegacao.instituicao_id'],
            name='fk_concessao_autoridade_instituicao', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint("capacidade = 'CONTEXTO_ADMINISTRAR' OR escopo_tipo = 'CONTEXTO'", name='ck_concessao_clinica_contextual'),
    )


revision = 'w1b_permissoes_v1'
down_revision = 'w1a_contexto_v1'
branch_labels = None
depends_on = None

# Reference stubs only; never created or dropped by this revision.
Table('usuarios', Base.metadata, Column('id', Integer, primary_key=True))
for name in ('usuario_instituicao_acessos', 'contextos_assistenciais', 'profissional_instituicoes'):
    Table(name, Base.metadata, Column('id', Integer, primary_key=True), Column('instituicao_id', Integer))
TABLES = (ContextoProfissional.__table__, AutoridadeDelegacao.__table__, ConcessaoAssistencial.__table__)
SUPPORT = (('usuario_instituicao_acessos', 'uq_acesso_instituicao'),
           ('contextos_assistenciais', 'uq_contexto_instituicao'),
           ('profissional_instituicoes', 'uq_profissional_instituicao_identidade'))


def upgrade():
    for table, name in SUPPORT:
        op.create_unique_constraint(name, table, ['id', 'instituicao_id'], schema='public')
    for table in TABLES:
        table.create(op.get_bind())


def downgrade():
    connection = op.get_bind()
    if connection.exec_driver_sql('SHOW transaction_isolation').scalar() != 'read committed':
        raise RuntimeError('W1B_READ_COMMITTED_REQUIRED')
    connection.exec_driver_sql('LOCK TABLE public.contexto_profissionais, public.autoridades_delegacao, public.concessoes_assistenciais IN ACCESS EXCLUSIVE MODE')
    if any(connection.exec_driver_sql('SELECT EXISTS (SELECT 1 FROM public.' + table.name + ')').scalar() for table in TABLES):
        raise RuntimeError('W1B_DOWNGRADE_BLOCKED_HISTORY')
    for table in reversed(TABLES):
        table.drop(connection)
    for table, name in reversed(SUPPORT):
        op.drop_constraint(name, table, type_='unique', schema='public')
    # btree_gist belongs to G1 and remains installed.
