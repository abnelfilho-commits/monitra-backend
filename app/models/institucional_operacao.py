"""Institutional provenance, separate from identity and clinical authorization."""
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, CheckConstraint, JSON, func
from sqlalchemy.dialects.postgresql import JSONB
from app.database import Base


class InstitucionalOperacao(Base):
    __tablename__ = 'institucional_operacoes'
    id = Column(Integer, primary_key=True)
    ator_usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False, index=True)
    operacao = Column(String(32), nullable=False)
    tipo_alvo = Column(String(32), nullable=False)
    paciente_instituicao_id = Column(Integer, ForeignKey('paciente_instituicoes.id', ondelete='RESTRICT'))
    profissional_instituicao_id = Column(Integer, ForeignKey('profissional_instituicoes.id', ondelete='RESTRICT'))
    paciente_profissional_id = Column(Integer, ForeignKey('paciente_profissionais.id', ondelete='RESTRICT'))
    motivo = Column(Text, nullable=False)
    resultado = Column(String(16), nullable=False)
    estado_anterior = Column(JSON().with_variant(JSONB(), 'postgresql'))
    estado_final = Column(JSON().with_variant(JSONB(), 'postgresql'), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("(operacao = 'CREATE_LINK' AND resultado = 'CREATED') OR (operacao = 'CLOSE_LINK' AND resultado = 'CLOSED') OR (operacao = 'INVALIDATE_LINK' AND resultado = 'INVALIDATED')", name='ck_institucional_operacao_resultado'),
        CheckConstraint("(tipo_alvo = 'PACIENTE_INSTITUICAO' AND paciente_instituicao_id IS NOT NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NULL) OR (tipo_alvo = 'PROFISSIONAL_INSTITUICAO' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NOT NULL AND paciente_profissional_id IS NULL) OR (tipo_alvo = 'PACIENTE_PROFISSIONAL' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NOT NULL)", name='ck_institucional_operacao_alvo'),
        CheckConstraint('length(trim(motivo)) > 0', name='ck_institucional_operacao_motivo'),
    )
