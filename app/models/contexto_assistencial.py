"""Assistive context foundation. Membership never grants authorization."""
from sqlalchemy import (Boolean, CheckConstraint, Column, Date, DateTime,
                        ForeignKey, ForeignKeyConstraint, Identity, Integer,
                        UniqueConstraint, func, text)
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from app.database import Base


class ContextoAssistencial(Base):
    __tablename__ = 'contextos_assistenciais'
    id = Column(Integer, Identity(), primary_key=True)
    paciente_instituicao_id = Column(Integer, nullable=False, index=True)
    # Materialized only for declarative integrity; the composite FK owns consistency.
    paciente_id = Column(Integer, nullable=False, index=True)
    instituicao_id = Column(Integer, nullable=False, index=True)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date)
    ativo = Column(Boolean, nullable=False, server_default=text('true'))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    criado_por_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    __table_args__ = (
        UniqueConstraint('id', 'instituicao_id', name='uq_contexto_instituicao'),
        UniqueConstraint('id', 'paciente_id', name='uq_contexto_paciente'),
        ForeignKeyConstraint(
            ['paciente_instituicao_id', 'paciente_id', 'instituicao_id'],
            ['paciente_instituicoes.id', 'paciente_instituicoes.paciente_id', 'paciente_instituicoes.instituicao_id'],
            name='fk_contexto_vinculo_identidade', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint('data_fim IS NULL OR data_fim >= data_inicio', name='ck_contexto_periodo'),
        ExcludeConstraint(('paciente_id', '='), ('instituicao_id', '='),
            (text("daterange(data_inicio, data_fim, '[]')"), '&&'),
            where=text('ativo'), using='gist', name='ex_contexto_vigencia').ddl_if(dialect='postgresql'),
    )


class ContextoAssistencialLinha(Base):
    __tablename__ = 'contexto_assistencial_linhas'
    id = Column(Integer, Identity(), primary_key=True)
    contexto_assistencial_id = Column(Integer, ForeignKey('contextos_assistenciais.id', ondelete='RESTRICT'), nullable=False, index=True)
    modulo_id = Column(Integer, ForeignKey('modulos_clinicos.id', ondelete='RESTRICT'), nullable=False, index=True)
    ativo = Column(Boolean, nullable=False, server_default=text('false'))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    __table_args__ = (UniqueConstraint('contexto_assistencial_id', 'modulo_id', name='uq_contexto_linha'),)
