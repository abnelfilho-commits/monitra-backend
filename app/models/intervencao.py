from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Intervencao(Base):
    __tablename__ = "intervencoes"

    id = Column(Integer, primary_key=True, index=True)

    paciente_id = Column(Integer, ForeignKey("pacientes.id"))
    profissional_id = Column(Integer, ForeignKey("usuarios.id"))

    tipo = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    data_intervencao = Column(DateTime, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paciente = relationship("Paciente")
    profissional = relationship("Usuario")

