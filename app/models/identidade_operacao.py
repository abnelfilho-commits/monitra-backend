"""Administrative provenance; never a clinical actor or access grant."""
from sqlalchemy import Column, JSON, Integer, String, Text, DateTime, ForeignKey, UniqueConstraint, CheckConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.database import Base


class IdentidadeOperacao(Base):
    __tablename__ = "identidade_operacoes"
    __table_args__ = (
        UniqueConstraint("chave_idempotencia", name="uq_identidade_operacao_chave"),
        CheckConstraint("tipo_operacao IN ('PESSOA', 'ADICIONAR_PAPEL', 'ASSOCIAR_PAPEL', 'ASSOCIAR_CONTA')", name="ck_identidade_operacao_tipo"),
        CheckConstraint("resultado IN ('PESSOA_CRIADA', 'PESSOA_REUTILIZADA', 'PAPEL_CRIADO', 'PAPEL_REUTILIZADO', 'LEGADO_ASSOCIADO', 'ASSOCIACAO_REUTILIZADA')", name="ck_identidade_operacao_resultado"),
        CheckConstraint("num_nonnulls(paciente_id, profissional_id, responsavel_id, usuario_id) = CASE WHEN tipo_operacao = 'PESSOA' THEN 0 ELSE 1 END", name="ck_identidade_operacao_alvo").ddl_if(dialect="postgresql"),
        CheckConstraint("(tipo_operacao = 'ASSOCIAR_CONTA' AND usuario_id IS NOT NULL) OR (tipo_operacao <> 'ASSOCIAR_CONTA' AND usuario_id IS NULL)", name="ck_identidade_operacao_conta"),
        CheckConstraint("tipo_operacao NOT IN ('ASSOCIAR_PAPEL', 'ASSOCIAR_CONTA') OR (tipo_evidencia IS NOT NULL AND length(trim(tipo_evidencia)) > 0 AND referencia_evidencia IS NOT NULL AND length(trim(referencia_evidencia)) > 0)", name="ck_identidade_operacao_evidencia"),
        CheckConstraint("length(trim(motivo)) > 0", name="ck_identidade_operacao_motivo"),
    )
    id = Column(Integer, primary_key=True)
    chave_idempotencia = Column(UUID(as_uuid=True), nullable=False)
    ator_usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"), nullable=False)
    tipo_operacao = Column(String(32), nullable=False)
    pessoa_id = Column(Integer, ForeignKey("pessoas.id", ondelete="RESTRICT"), nullable=False)
    paciente_id = Column(Integer, ForeignKey("pacientes.id", ondelete="RESTRICT"))
    profissional_id = Column(Integer, ForeignKey("profissionais.id", ondelete="RESTRICT"))
    responsavel_id = Column(Integer, ForeignKey("responsaveis.id", ondelete="RESTRICT"))
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="RESTRICT"))
    pessoa_anterior_id = Column(Integer, ForeignKey("pessoas.id", ondelete="RESTRICT"))
    resultado = Column(String(32), nullable=False)
    motivo = Column(Text, nullable=False)
    tipo_evidencia = Column(Text)
    referencia_evidencia = Column(Text)
    requisicao_normalizada = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
