from sqlalchemy import Column, Integer, Date, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class RegistroDiario(Base):
    __tablename__ = "registros_diarios"

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(
        Integer,
        ForeignKey("pacientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

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
