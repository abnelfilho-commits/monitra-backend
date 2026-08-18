from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.sessao_assistencial import SessaoAssistencial

class AgendaCuidado(Base):
    """
    Representa o Planejamento Assistencial de uma atividade vinculada ao PTS.

    Um planejamento poderá gerar várias Sessões Assistenciais.
    """

    __tablename__ = "agenda_cuidados"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    pts_id = Column(
        Integer,
        ForeignKey("pts.id"),
        nullable=False,
    )

    objetivo_id = Column(
        Integer,
        ForeignKey("pts_objetivos.id"),
        nullable=False,
    )

    atividade_id = Column(
        Integer,
        ForeignKey("atividades_terapeuticas.id"),
        nullable=False,
    )

    ocupacao_id = Column(
        Integer,
        ForeignKey("ocupacoes_profissionais.id"),
        nullable=False,
    )

    profissional_id = Column(
        Integer,
        ForeignKey("profissionais.id"),
        nullable=True,
        index=True,
    )

    frequencia_semanal = Column(
        Integer,
        nullable=False,
    )

    quantidade_sessoes = Column(
        Integer,
        nullable=True,
    )

    duracao_minutos = Column(
        Integer,
        nullable=False,
    )

    data_inicio = Column(
        Date,
        nullable=False,
    )

    data_fim = Column(
        Date,
        nullable=True,
    )

    status = Column(
        String(30),
        nullable=False,
        default="PLANEJADO",
    )

    observacoes = Column(
        Text,
        nullable=True,
    )

    # Campos legados de execução.
    # Serão preservados temporariamente para compatibilidade.
    status_execucao = Column(
        String(30),
        default="PLANEJADO",
    )

    data_realizacao = Column(
        Date,
        nullable=True,
    )

    observacao_execucao = Column(
        Text,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        server_default=func.now(),
    )

    pts = relationship("PTS")

    objetivo = relationship("PTSObjetivo")

    atividade = relationship(
        "AtividadeTerapeutica",
    )

    ocupacao = relationship(
        "OcupacaoProfissional",
    )

    profissional = relationship(
        "Profissional",
    )

    sessoes = relationship(
        "SessaoAssistencial",
        back_populates="agenda_cuidado",
        cascade="all, delete-orphan",
        order_by=lambda: SessaoAssistencial.numero_sessao,
    )