from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Clinica(Base):
    __tablename__ = "clinicas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    cnpj = Column(String, nullable=True)
    email = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    ativa = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    profissionais = relationship("Profissional", back_populates="clinica")
    pacientes = relationship("Paciente", back_populates="clinica")
