from sqlalchemy import CheckConstraint, ForeignKeyConstraint
from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Diagnostico(Base):
    __tablename__ = "diagnosticos"

    registrador_usuario_id = Column(Integer, ForeignKey("usuarios.id", name="fk_diagnosticos_registrador_usuario_id", ondelete="RESTRICT"), nullable=True)
    registrador_profissional_id = Column(Integer, ForeignKey("profissionais.id", name="fk_diagnosticos_registrador_profissional_id", ondelete="RESTRICT"), nullable=True)
    contexto_assistencial_id = Column(Integer, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(['contexto_assistencial_id', 'paciente_id'],
            ['contextos_assistenciais.id', 'contextos_assistenciais.paciente_id'],
            name='fk_diagnosticos_contexto_paciente', ondelete='RESTRICT', onupdate='RESTRICT'),
        ForeignKeyConstraint(['contexto_assistencial_id', 'modulo_id'],
            ['contexto_assistencial_linhas.contexto_assistencial_id', 'contexto_assistencial_linhas.modulo_id'],
            name='fk_diagnosticos_contexto_linha', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint('contexto_assistencial_id IS NULL OR (paciente_id IS NOT NULL AND modulo_id IS NOT NULL)',
            name='ck_diagnosticos_contexto_identidade'),
        Index('ix_diagnosticos_contexto', 'contexto_assistencial_id'),
        Index("ix_diagnosticos_paciente_modulo", "paciente_id", "modulo_id"),
    )

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

    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)

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
