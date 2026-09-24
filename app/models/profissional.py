from sqlalchemy import text
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Profissional(Base):
    __tablename__ = "profissionais"

    id = Column(Integer, primary_key=True, index=True)
    pessoa_id = Column(Integer, ForeignKey("pessoas.id", ondelete="RESTRICT"), nullable=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, nullable=True, unique=False)
    especialidade = Column(String, nullable=True)

    clinica_id = Column(Integer, ForeignKey("clinicas.id"), nullable=True, index=True)

    ocupacao_id = Column(
        Integer,
        ForeignKey("ocupacoes_profissionais.id"),
        nullable=True,
    )

    ativo = Column(Boolean, default=True, server_default=text('true'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    clinica = relationship("Clinica", back_populates="profissionais")

    ocupacao = relationship(
        "OcupacaoProfissional",
        foreign_keys=[ocupacao_id],
    )

    # Legado transitório, consistente com o join explícito de Paciente.
    pacientes = relationship(
        "Paciente", back_populates="profissional",
        primaryjoin="Profissional.id == foreign(Paciente.profissional_id)",
    )