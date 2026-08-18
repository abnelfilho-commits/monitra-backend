from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    Time,
    DateTime,
    ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class SessaoAssistencial(Base):
    """
    Representa uma sessão individual gerada a partir de um
    Planejamento Assistencial.

    Cada sessão possui data, profissional, status e dados próprios
    de execução.
    """

    __tablename__ = "sessoes_assistenciais"

    __table_args__ = (
        UniqueConstraint(
            "agenda_cuidado_id",
            "numero_sessao",
            name="uq_sessao_agenda_numero",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    agenda_cuidado_id = Column(
        Integer,
        ForeignKey("agenda_cuidados.id"),
        nullable=False,
        index=True,
    )

    paciente_id = Column(
        Integer,
        ForeignKey("pacientes.id"),
        nullable=False,
        index=True,
    )

    profissional_id = Column(
        Integer,
        ForeignKey("profissionais.id"),
        nullable=True,
        index=True,
    )

    numero_sessao = Column(
        Integer,
        nullable=False,
    )

    data_agendada = Column(
        Date,
        nullable=False,
        index=True,
    )

    hora_inicio = Column(
        Time,
        nullable=True,
    )

    hora_fim = Column(
        Time,
        nullable=True,
    )

    duracao_minutos = Column(
        Integer,
        nullable=False,
    )

    status = Column(
        String(30),
        nullable=False,
        default="AGENDADA",
        server_default="AGENDADA",
        index=True,
    )

    data_realizacao = Column(
        Date,
        nullable=True,
    )

    hora_inicio_real = Column(
        Time,
        nullable=True,
    )

    hora_fim_real = Column(
        Time,
        nullable=True,
    )

    observacoes = Column(
        Text,
        nullable=True,
    )

    motivo_falta = Column(
        Text,
        nullable=True,
    )

    motivo_cancelamento = Column(
        Text,
        nullable=True,
    )

    motivo_reagendamento = Column(
        Text,
        nullable=True,
    )

    sessao_origem_id = Column(
        Integer,
        ForeignKey("sessoes_assistenciais.id"),
        nullable=True,
    )

    registro_longitudinal_id = Column(
        Integer,
        ForeignKey("registros_longitudinais.id"),
        nullable=True,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    agenda_cuidado = relationship(
        "AgendaCuidado",
        back_populates="sessoes",
    )

    paciente = relationship(
        "Paciente",
    )

    profissional = relationship(
        "Profissional",
    )

    registro_longitudinal = relationship(
        "RegistroLongitudinal",
    )

    sessao_origem = relationship(
        "SessaoAssistencial",
        remote_side=[id],
        foreign_keys=[sessao_origem_id],
        back_populates="sessoes_reagendadas",
    )

    sessoes_reagendadas = relationship(
        "SessaoAssistencial",
        foreign_keys=[sessao_origem_id],
        back_populates="sessao_origem",
    )