from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class ResponsavelPaciente(Base):
    __tablename__ = "responsavel_paciente"

    __table_args__ = (
        UniqueConstraint("responsavel_id", "paciente_id", name="uq_responsavel_paciente"),
    )

    id = Column(Integer, primary_key=True, index=True)

    responsavel_id = Column(
        Integer,
        ForeignKey("responsaveis.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    paciente_id = Column(
        Integer,
        ForeignKey("pacientes.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    parentesco = Column(String, nullable=True)
    principal = Column(Boolean, default=False, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relacionamentos
    responsavel = relationship("Responsavel", back_populates="vinculos")
    paciente = relationship("Paciente")
