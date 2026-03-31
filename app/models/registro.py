from sqlalchemy import Column, Integer, Date, Boolean, Text, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class RegistroDiario(Base):
    __tablename__ = "registros_diarios"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id"), nullable=False, index=True)

    data = Column(Date, nullable=False, index=True)

    sono_qualidade = Column(Integer, nullable=True)
    evacuacao = Column(Boolean, nullable=True)
    consistencia_fezes = Column(Integer, nullable=True)
    irritabilidade = Column(Integer, nullable=True)
    crise_sensorial = Column(Integer, nullable=True)

    observacao = Column(Text, nullable=True)
    alimentacao = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    paciente = relationship("Paciente")

    origem = Column(String, nullable=True, index=True)

    responsavel_id = Column(
        Integer,
        ForeignKey("responsaveis.id"),
        nullable=True,
        index=True
    )
    origem = Column(String(30), nullable=False, default="PROFISSIONAL")

    criado_por_tipo = Column(String, nullable=True)
    criado_por_id = Column(Integer, nullable=True)

    responsavel = relationship("Responsavel")
