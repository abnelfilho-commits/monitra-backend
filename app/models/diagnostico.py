from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Diagnostico(Base):
    __tablename__ = "diagnosticos"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    paciente_id = Column(
        Integer,
        ForeignKey("pacientes.id"),
        nullable=False,
        index=True,
    )

    tipo = Column(
        String(30),
        nullable=False,
        default="DIAGNOSTICO",
        server_default="DIAGNOSTICO",
    )

    status = Column(
        String(30),
        nullable=False,
        default="ATIVO",
        server_default="ATIVO",
    )

    cid = Column(
        String(20),
        nullable=True,
        index=True,
    )

    descricao_clinica = Column(
        Text,
        nullable=False,
    )

    data_diagnostico = Column(
        Date,
        nullable=False,
        index=True,
    )

    medico_nome = Column(
        String(200),
        nullable=False,
    )

    medico_especialidade = Column(
        String(150),
        nullable=True,
    )

    medico_crm = Column(
        String(50),
        nullable=True,
    )

    medico_cpf = Column(
        String(20),
        nullable=True,
    )

    observacoes = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime,
        nullable=True,
        onupdate=func.now(),
    )

    paciente = relationship(
        "Paciente",
        back_populates="diagnosticos",
    )