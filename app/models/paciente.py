from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Paciente(Base):
    __tablename__ = "pacientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    data_nascimento = Column(Date, nullable=True)
    genero = Column(String, nullable=True)

    responsavel_nome = Column(String, nullable=True)
    responsavel_email = Column(String, nullable=True)

    clinica_id = Column(Integer, ForeignKey("clinicas.id"), nullable=True)
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=True)

    clinica = relationship("Clinica", back_populates="pacientes")
    profissional = relationship("Profissional", back_populates="pacientes")

    ativo = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
