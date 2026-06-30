from sqlalchemy import Column, Integer, Numeric, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.database import Base


class CapacidadeInstalada(Base):
    __tablename__ = "capacidade_instalada"

    id = Column(Integer, primary_key=True, index=True)

    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)
    ocupacao_id = Column(Integer, ForeignKey("ocupacoes_profissionais.id"), nullable=False)

    quantidade_profissionais = Column(Integer, nullable=False)
    horas_semanais_por_profissional = Column(Numeric(10, 2), nullable=False)

    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())