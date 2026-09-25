"""Gate A economic configuration. No clinical mutation or projection model."""
from sqlalchemy import (Column, BigInteger, Integer, Identity, String, Text, Boolean,
                        Date, DateTime, Numeric, ForeignKey, CheckConstraint,
                        UniqueConstraint, Index, text, func)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from app.database import Base


class EconomicRow:
    id = Column(BigInteger, Identity(), primary_key=True)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ServicoEconomico(EconomicRow, Base):
    __tablename__ = 'servicos_economicos'
    codigo = Column(String(64), nullable=False)
    descricao = Column(Text, nullable=False)
    ocupacao_id = Column(Integer, ForeignKey('ocupacoes_profissionais.id', ondelete='RESTRICT'), nullable=False, index=True)
    duracao_minutos = Column(Integer, nullable=False)
    tipo_atendimento = Column(String(16), nullable=False, server_default=text("'INDIVIDUAL'"))
    unidade = Column(String(16), nullable=False, server_default=text("'SESSAO'"))
    ativo = Column(Boolean, nullable=False, server_default=text('true'))
    __table_args__ = (
        UniqueConstraint('codigo', name='uq_servico_economico_codigo'),
        CheckConstraint("length(trim(codigo)) > 0 AND length(trim(descricao)) > 0", name='ck_servico_economico_texto'),
        CheckConstraint('duracao_minutos > 0', name='ck_servico_economico_duracao'),
        CheckConstraint("tipo_atendimento = 'INDIVIDUAL' AND unidade = 'SESSAO'", name='ck_servico_economico_unidade'),
    )


class TabelaPreco(EconomicRow, Base):
    __tablename__ = 'tabelas_preco'
    proprietario_instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False)
    codigo = Column(String(64), nullable=False)
    nome = Column(Text, nullable=False)
    moeda = Column(String(3), nullable=False, server_default=text("'BRL'"))
    __table_args__ = (
        UniqueConstraint('proprietario_instituicao_id', 'codigo', name='uq_tabela_preco_codigo'),
        CheckConstraint("length(trim(codigo)) > 0 AND length(trim(nome)) > 0", name='ck_tabela_preco_texto'),
        CheckConstraint("moeda = 'BRL'", name='ck_tabela_preco_moeda'),
    )


class TabelaPrecoVersao(EconomicRow, Base):
    __tablename__ = 'tabela_preco_versoes'
    tabela_id = Column(BigInteger, ForeignKey('tabelas_preco.id', ondelete='RESTRICT'), nullable=False)
    numero = Column(Integer, nullable=False)
    vigente_desde = Column(Date, nullable=False)
    estado = Column(String(16), nullable=False, server_default=text("'DRAFT'"))
    publicado_em = Column(DateTime(timezone=True))
    publicado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    __table_args__ = (
        UniqueConstraint('tabela_id', 'numero', name='uq_tabela_preco_versao_numero'),
        CheckConstraint('numero > 0', name='ck_tabela_preco_versao_numero'),
        CheckConstraint("(estado = 'DRAFT' AND publicado_em IS NULL AND publicado_por_usuario_id IS NULL) OR (estado = 'PUBLISHED' AND publicado_em IS NOT NULL AND publicado_por_usuario_id IS NOT NULL)", name='ck_tabela_preco_versao_publicacao'),
        Index('uq_tabela_preco_versao_vigencia', 'tabela_id', 'vigente_desde', unique=True, postgresql_where=text("estado = 'PUBLISHED'")),
    )


class PrecoServico(EconomicRow, Base):
    __tablename__ = 'precos_servico'
    versao_id = Column(BigInteger, ForeignKey('tabela_preco_versoes.id', ondelete='RESTRICT'), nullable=False)
    servico_id = Column(BigInteger, ForeignKey('servicos_economicos.id', ondelete='RESTRICT'), nullable=False, index=True)
    valor_base = Column(Numeric(14, 2), nullable=False)
    codigo_externo = Column(String(128))
    __table_args__ = (
        UniqueConstraint('versao_id', 'servico_id', name='uq_preco_servico'),
        CheckConstraint("valor_base >= 0 AND valor_base::text NOT IN ('NaN', 'Infinity', '-Infinity')", name='ck_preco_servico_valor').ddl_if(dialect='postgresql'),
        CheckConstraint('codigo_externo IS NULL OR length(trim(codigo_externo)) > 0', name='ck_preco_servico_codigo'),
        Index('uq_preco_servico_externo', 'versao_id', 'codigo_externo', unique=True, postgresql_where=text('codigo_externo IS NOT NULL')),
    )


class ContratoFinanceiro(EconomicRow, Base):
    __tablename__ = 'contratos_financeiros'
    pagador_instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False)
    codigo = Column(String(64), nullable=False)
    edicao = Column(Integer, nullable=False)
    tabela_preco_id = Column(BigInteger, ForeignKey('tabelas_preco.id', ondelete='RESTRICT'), nullable=False, index=True)
    inicio = Column(Date, nullable=False)
    fim = Column(Date)
    estado = Column(String(16), nullable=False, server_default=text("'DRAFT'"))
    publicado_em = Column(DateTime(timezone=True))
    publicado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    __table_args__ = (
        UniqueConstraint('pagador_instituicao_id', 'codigo', 'edicao', name='uq_contrato_financeiro_edicao'),
        CheckConstraint('edicao > 0 AND length(trim(codigo)) > 0', name='ck_contrato_financeiro_codigo'),
        CheckConstraint('fim IS NULL OR fim >= inicio', name='ck_contrato_financeiro_periodo'),
        CheckConstraint("(estado = 'DRAFT' AND publicado_em IS NULL AND publicado_por_usuario_id IS NULL) OR (estado = 'PUBLISHED' AND publicado_em IS NOT NULL AND publicado_por_usuario_id IS NOT NULL)", name='ck_contrato_financeiro_publicacao'),
    )


class PacienteContrato(EconomicRow, Base):
    __tablename__ = 'paciente_contratos'
    paciente_id = Column(Integer, ForeignKey('pacientes.id', ondelete='RESTRICT'), nullable=False, index=True)
    contrato_id = Column(BigInteger, ForeignKey('contratos_financeiros.id', ondelete='RESTRICT'), nullable=False, index=True)
    inicio = Column(Date, nullable=False)
    fim = Column(Date)
    identificador_beneficiario = Column(String(128))
    __table_args__ = (
        CheckConstraint('fim IS NULL OR fim >= inicio', name='ck_paciente_contrato_periodo'),
        CheckConstraint('identificador_beneficiario IS NULL OR length(trim(identificador_beneficiario)) > 0', name='ck_paciente_contrato_identificador'),
        ExcludeConstraint(('paciente_id', '='), ('contrato_id', '='), (text("daterange(inicio, fim, '[]')"), '&&'), using='gist', name='ex_paciente_contrato_periodo').ddl_if(dialect='postgresql'),
    )


class MapeamentoAgendaServico(EconomicRow, Base):
    __tablename__ = 'mapeamentos_agenda_servico'
    agenda_cuidado_id = Column(Integer, ForeignKey('agenda_cuidados.id', ondelete='RESTRICT'), nullable=False)
    servico_id = Column(BigInteger, ForeignKey('servicos_economicos.id', ondelete='RESTRICT'), nullable=False, index=True)
    __table_args__ = (UniqueConstraint('agenda_cuidado_id', name='uq_mapeamento_agenda_servico'),)
