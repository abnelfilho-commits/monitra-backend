from sqlalchemy import Column, Integer, String, Text, Numeric, DateTime, JSON
from sqlalchemy.sql import func

from app.database import Base


class AvaliacaoClinica(Base):
    __tablename__ = "avaliacoes_clinicas"

    id = Column(Integer, primary_key=True, index=True)

    registro_id = Column(Integer, nullable=False)
    paciente_id = Column(Integer, nullable=False)
    modulo_id = Column(Integer, nullable=False)
    formulario_id = Column(Integer, nullable=True)

    instrumento = Column(String(50), nullable=False)
    versao = Column(String(20), nullable=True)

    score = Column(Numeric(10, 2), nullable=True)
    score_texto = Column(String(100), nullable=True)

    classificacao = Column(String(100), nullable=True)
    classificacao_codigo = Column(String(50), nullable=True)

    conduta = Column(Text, nullable=True)
    interpretacao = Column(Text, nullable=True)
    resultado = Column(JSON, nullable=True)

    engine_version = Column(String(20), nullable=True)
    profissional_id = Column(Integer, nullable=True)

    status = Column(String(30), nullable=False, default="CONCLUIDA")

    executado_em = Column(DateTime, nullable=False, server_default=func.now())
    created_at = Column(DateTime, nullable=False, server_default=func.now())