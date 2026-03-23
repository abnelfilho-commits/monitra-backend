from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Profissional(Base):
    __tablename__ = "profissionais"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=True, unique=False)
    especialidade = Column(String, nullable=True)

    clinica_id = Column(Integer, ForeignKey("clinicas.id"), nullable=False)

    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    clinica = relationship("Clinica", back_populates="profissionais")
    pacientes = relationship("Paciente", back_populates="profissional")
