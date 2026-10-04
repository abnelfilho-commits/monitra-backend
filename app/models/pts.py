from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from sqlalchemy import text
from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PTS(Base):
    __tablename__ = "pts"

    contexto_assistencial_id = Column(Integer, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(['contexto_assistencial_id', 'paciente_id'],
            ['contextos_assistenciais.id', 'contextos_assistenciais.paciente_id'],
            name='fk_pts_contexto_paciente', ondelete='RESTRICT', onupdate='RESTRICT'),
        ForeignKeyConstraint(['contexto_assistencial_id', 'modulo_id'],
            ['contexto_assistencial_linhas.contexto_assistencial_id', 'contexto_assistencial_linhas.modulo_id'],
            name='fk_pts_contexto_linha', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint('contexto_assistencial_id IS NULL OR (paciente_id IS NOT NULL AND modulo_id IS NOT NULL)',
            name='ck_pts_contexto_identidade'),
        Index('ix_pts_contexto', 'contexto_assistencial_id'),
        Index('uq_pts_contexto_linha_ativo', 'contexto_assistencial_id', 'modulo_id', unique=True,
            postgresql_where=text("contexto_assistencial_id IS NOT NULL AND status = 'ATIVO'")).ddl_if(dialect='postgresql'),
    )

    id = Column(Integer, primary_key=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=True)
    data_inicio = Column(Date, nullable=False, server_default=text('CURRENT_DATE'))
    data_fim = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, default="ATIVO", server_default=text("'ATIVO'"))
    objetivo_geral = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
    criado_por_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, nullable=True)

    objetivos = relationship(
        "PTSObjetivo",
        back_populates="pts",
        cascade="all, delete-orphan",
    )


class PTSObjetivo(Base):
    __tablename__ = "pts_objetivos"

    id = Column(Integer, primary_key=True)
    pts_id = Column(Integer, ForeignKey("pts.id", ondelete="CASCADE"), nullable=False)
    descricao = Column(Text, nullable=False)
    prioridade = Column(String(30), nullable=True)
    status = Column(String(30), nullable=False, default="ABERTO", server_default=text("'ABERTO'"))
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, nullable=True)

    pts = relationship("PTS", back_populates="objetivos")