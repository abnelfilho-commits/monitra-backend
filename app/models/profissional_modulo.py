from sqlalchemy import Column, Integer, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.sql import func

from app.database import Base


class ProfissionalModulo(Base):
    __tablename__ = "profissional_modulos"

    id = Column(Integer, primary_key=True, index=True)
    profissional_id = Column(Integer, ForeignKey("profissionais.id", ondelete="CASCADE"), nullable=False)
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id", ondelete="CASCADE"), nullable=False)
    criado_em = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("profissional_id", "modulo_id", name="uq_profissional_modulo"),
    )