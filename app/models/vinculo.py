from sqlalchemy import Column, Integer, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class ProfissionalPaciente(Base):
    __tablename__ = "vinculos"

    id = Column(Integer, primary_key=True, index=True)

    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paciente = relationship("Paciente")
    profissional = relationship("Usuario")

