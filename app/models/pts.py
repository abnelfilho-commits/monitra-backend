from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class PTS(Base):
    __tablename__ = "pts"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=True)
    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=True)
    status = Column(String(30), nullable=False, default="ATIVO")
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

    id = Column(Integer, primary_key=True, index=True)
    pts_id = Column(Integer, ForeignKey("pts.id", ondelete="CASCADE"), nullable=False)
    descricao = Column(Text, nullable=False)
    prioridade = Column(String(30), nullable=True)
    status = Column(String(30), nullable=False, default="ABERTO")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, nullable=True)

    pts = relationship("PTS", back_populates="objetivos")