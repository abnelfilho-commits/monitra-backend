from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

class Intervencao(Base):
    __tablename__ = "intervencoes"

    contexto_assistencial_id = Column(Integer, nullable=True)
    __table_args__ = (
        ForeignKeyConstraint(['contexto_assistencial_id', 'paciente_id'],
            ['contextos_assistenciais.id', 'contextos_assistenciais.paciente_id'],
            name='fk_intervencoes_contexto_paciente', ondelete='RESTRICT', onupdate='RESTRICT'),
        ForeignKeyConstraint(['contexto_assistencial_id', 'modulo_id'],
            ['contexto_assistencial_linhas.contexto_assistencial_id', 'contexto_assistencial_linhas.modulo_id'],
            name='fk_intervencoes_contexto_linha', ondelete='RESTRICT', onupdate='RESTRICT'),
        CheckConstraint('contexto_assistencial_id IS NULL OR (paciente_id IS NOT NULL AND modulo_id IS NOT NULL)',
            name='ck_intervencoes_contexto_identidade'),
        Index('ix_intervencoes_contexto', 'contexto_assistencial_id'),
    )

    id = Column(Integer, primary_key=True, index=True)

    paciente_id = Column(Integer, ForeignKey("pacientes.id"))
    modulo_id = Column(Integer, ForeignKey("modulos_clinicos.id"), nullable=False)
    profissional_id = Column(Integer, ForeignKey("usuarios.id"))

    registrador_profissional_id = Column(Integer, ForeignKey("profissionais.id", name="fk_intervencoes_registrador_profissional_id", ondelete="RESTRICT"), nullable=True)

    tipo = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)
    data_intervencao = Column(DateTime, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paciente = relationship("Paciente")
    profissional = relationship("Usuario")

