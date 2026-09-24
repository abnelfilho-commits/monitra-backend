from sqlalchemy import Column, Integer, Date, Boolean, UniqueConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class RegistroDiario(Base):
    __tablename__ = "registros_diarios"
    # Legado Neuro preservado; coleta canônica permanece Registro + Respostas.
    __table_args__ = (UniqueConstraint("paciente_id", "data", name="uq_registro_paciente_data"),)

    id = Column(Integer, primary_key=True, index=True)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="CASCADE"), nullable=False, index=True)

    data = Column(Date, nullable=False, index=True)

    sono_qualidade = Column(String, nullable=True)
    evacuacao = Column(Boolean, nullable=True)
    consistencia_fezes = Column(String, nullable=True)
    irritabilidade = Column(String, nullable=True)
    crise_sensorial = Column(Boolean, nullable=True)
    observacao = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    paciente = relationship("Paciente")

    origem = Column(String, nullable=True, index=True)

    responsavel_id = Column(
        Integer,
        ForeignKey("responsaveis.id"),
        nullable=True,
        index=True
    )
    alimentacao = Column(String, nullable=True)

    criado_por_tipo = Column(String, nullable=True)
    criado_por_id = Column(Integer, nullable=True)

    responsavel = relationship("Responsavel")
