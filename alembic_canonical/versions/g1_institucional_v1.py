"""Institutional domain only: these relationships never grant clinical access."""
from sqlalchemy import Column, Integer, String, Boolean, Date, DateTime, ForeignKey, CheckConstraint, UniqueConstraint, text, func
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import declarative_base
Base = declarative_base()

TYPES = ('CLINICA', 'UNIDADE_SAUDE', 'OPERADORA_SAUDE', 'GOVERNO_SECRETARIA', 'EMPRESA', 'INSTITUTO_ASSOCIACAO', 'OUTRO')
ROLES = ('CONTRATANTE', 'ASSISTENCIAL')
LINK_TYPES = ('BENEFICIARIO', 'ASSISTENCIAL', 'COLABORADOR', 'ASSOCIADO', 'OUTRO')

class Instituicao(Base):
    __tablename__ = 'instituicoes'
    id = Column(Integer, primary_key=True)
    razao_social = Column(String, nullable=False)
    nome_fantasia = Column(String)
    cnpj = Column(String(14), unique=True)
    tipo_instituicao = Column(String, nullable=False)
    instituicao_pai_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'))
    ativo = Column(Boolean, nullable=False, server_default=text('true'))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint('length(trim(razao_social)) > 0', name='ck_instituicao_nome'),
        CheckConstraint('id <> instituicao_pai_id', name='ck_instituicao_pai'),
        CheckConstraint("cnpj IS NULL OR cnpj ~ '^[0-9]{14}$'", name='ck_instituicao_cnpj').ddl_if(dialect='postgresql'),
        CheckConstraint('tipo_instituicao IN ' + str(TYPES), name='ck_instituicao_tipo'),
    )

class InstituicaoPapel(Base):
    __tablename__ = 'instituicao_papeis'
    id = Column(Integer, primary_key=True)
    instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False, index=True)
    papel = Column(String, nullable=False)
    ativo = Column(Boolean, nullable=False, server_default=text('true'))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint('instituicao_id', 'papel', name='uq_instituicao_papel'),
                     CheckConstraint('papel IN ' + str(ROLES), name='ck_instituicao_papel'))

class Temporal:
    id = Column(Integer, primary_key=True)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date)
    ativo = Column(Boolean, nullable=False, server_default=text('true'))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())


def temporal_constraints(name, keys):
    return (
        CheckConstraint('data_fim IS NULL OR data_fim >= data_inicio', name='ck_' + name + '_periodo'),
        ExcludeConstraint(*[(key, '=') for key in keys],
            (text("daterange(data_inicio, data_fim, '[]')"), '&&'),
            where=text('ativo'), using='gist', name='ex_' + name + '_vigencia').ddl_if(dialect='postgresql'),
    )

class PacienteInstituicao(Temporal, Base):
    __tablename__ = 'paciente_instituicoes'
    paciente_id = Column(Integer, ForeignKey('pacientes.id', ondelete='RESTRICT'), nullable=False, index=True)
    instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False, index=True)
    tipo_vinculo = Column(String, nullable=False)
    identificador_externo = Column(String)
    __table_args__ = temporal_constraints('paciente_instituicao', ('paciente_id', 'instituicao_id', 'tipo_vinculo')) + (
        CheckConstraint('tipo_vinculo IN ' + str(LINK_TYPES), name='ck_paciente_instituicao_tipo'),)

class ProfissionalInstituicao(Temporal, Base):
    __tablename__ = 'profissional_instituicoes'
    profissional_id = Column(Integer, ForeignKey('profissionais.id', ondelete='RESTRICT'), nullable=False, index=True)
    instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False, index=True)
    ocupacao_id = Column(Integer, ForeignKey('ocupacoes_profissionais.id', ondelete='RESTRICT'), nullable=False, index=True)
    __table_args__ = temporal_constraints('profissional_instituicao', ('profissional_id', 'instituicao_id', 'ocupacao_id'))

class PacienteProfissional(Temporal, Base):
    __tablename__ = 'paciente_profissionais'
    paciente_id = Column(Integer, ForeignKey('pacientes.id', ondelete='RESTRICT'), nullable=False, index=True)
    profissional_instituicao_id = Column(Integer, ForeignKey('profissional_instituicoes.id', ondelete='RESTRICT'), nullable=False, index=True)
    __table_args__ = temporal_constraints('paciente_profissional', ('paciente_id', 'profissional_instituicao_id'))

revision = 'g1_institucional_v1'
down_revision = 'm0_baseline_v1'
branch_labels = None
depends_on = None

from alembic import op
from sqlalchemy import Table
# References only: these existing objects are never created/dropped here.
for name in ('pacientes', 'profissionais', 'ocupacoes_profissionais'):
    Table(name, Base.metadata, Column('id', Integer, primary_key=True))
TABLES = [Instituicao.__table__, InstituicaoPapel.__table__, PacienteInstituicao.__table__, ProfissionalInstituicao.__table__, PacienteProfissional.__table__]

def upgrade():
    op.execute('CREATE EXTENSION IF NOT EXISTS btree_gist')
    for table in TABLES:
        table.create(op.get_bind())

def downgrade():
    for table in reversed(TABLES):
        table.drop(op.get_bind())
    # Extension may be shared by other domains; do not drop it.
