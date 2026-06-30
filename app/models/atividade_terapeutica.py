from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class AtividadeTerapeutica(Base):
    __tablename__ = "atividades_terapeuticas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(200), nullable=False)
    descricao = Column(Text, nullable=True)
    duracao_minutos = Column(Integer, nullable=True)
    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())

    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=True)

    ocupacoes = relationship(
        "AtividadeOcupacao",
        back_populates="atividade",
        cascade="all, delete-orphan",
    )


class OcupacaoProfissional(Base):
    __tablename__ = "ocupacoes_profissionais"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String(100), nullable=False)
    ativo = Column(Boolean, default=True)

    atividades = relationship(
        "AtividadeOcupacao",
        back_populates="ocupacao",
        cascade="all, delete-orphan",
    )


class AtividadeOcupacao(Base):
    __tablename__ = "atividade_ocupacao"

    id = Column(Integer, primary_key=True, index=True)

    atividade_id = Column(
        Integer,
        ForeignKey("atividades_terapeuticas.id", ondelete="CASCADE"),
        nullable=False,
    )

    ocupacao_id = Column(
        Integer,
        ForeignKey("ocupacoes_profissionais.id", ondelete="CASCADE"),
        nullable=False,
    )

    atividade = relationship(
        "AtividadeTerapeutica",
        back_populates="ocupacoes",
    )

    ocupacao = relationship(
        "OcupacaoProfissional",
        back_populates="atividades",
    )