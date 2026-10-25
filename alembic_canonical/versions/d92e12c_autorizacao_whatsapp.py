"""Prior channel authorization ledger. No historical authorization backfill."""
from alembic import op
from sqlalchemy import Table
revision = 'd92e12c_autorizacao_whatsapp'
down_revision = 'd92e12_whatsapp_manual'
branch_labels = None
depends_on = None
"""Append-only evidence of channel authorization; independent of check-in SIM."""
from sqlalchemy import (Column, Integer, String, DateTime, ForeignKey, ForeignKeyConstraint,
                        UniqueConstraint, CheckConstraint, Index, func, text)
from sqlalchemy.orm import declarative_base
Base = declarative_base()

class WhatsAppAutorizacaoComunicacao(Base):
    __tablename__ = 'whatsapp_autorizacoes_comunicacao'
    id = Column(Integer, primary_key=True)
    acompanhamento_id = Column(Integer, nullable=False)
    contexto_assistencial_id = Column(Integer, nullable=False)
    paciente_id = Column(Integer, nullable=False)
    instituicao_id = Column(Integer, nullable=False)
    anterior_id = Column(Integer, unique=True)
    estado = Column(String(16), nullable=False)
    origem = Column(String(32), nullable=False)
    ocorrido_em = Column(DateTime(timezone=True), nullable=False)
    registrado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    chave = Column(String(128))
    comando_sha256 = Column(String(64))
    destino_sha256 = Column(String(64), nullable=False)
    referencia_evidencia = Column(String(200))
    evidencia_sha256 = Column(String(64))
    motivo = Column(String(40))
    mensagem_id = Column(String(512), ForeignKey('whatsapp_mensagens.message_id', ondelete='RESTRICT'))
    conversa_id = Column(Integer, ForeignKey('whatsapp_conversas_contextuais.id', ondelete='RESTRICT'))
    __table_args__ = (
        ForeignKeyConstraint(['acompanhamento_id','contexto_assistencial_id','paciente_id'],
            ['acompanhamentos_whatsapp.id','acompanhamentos_whatsapp.contexto_assistencial_id','acompanhamentos_whatsapp.paciente_id'],
            name='fk_wac_acompanhamento', ondelete='RESTRICT'),
        ForeignKeyConstraint(['contexto_assistencial_id','instituicao_id'],
            ['contextos_assistenciais.id','contextos_assistenciais.instituicao_id'], name='fk_wac_instituicao', ondelete='RESTRICT'),
        UniqueConstraint('id','acompanhamento_id', name='uq_wac_identidade'),
        ForeignKeyConstraint(['anterior_id','acompanhamento_id'],
            ['whatsapp_autorizacoes_comunicacao.id','whatsapp_autorizacoes_comunicacao.acompanhamento_id'],
            name='fk_wac_anterior', ondelete='RESTRICT'),
        UniqueConstraint('instituicao_id','usuario_id','chave', name='uq_wac_comando'),
        CheckConstraint("estado IN ('AUTORIZADA','REVOGADA')", name='ck_wac_estado'),
        CheckConstraint("origem IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO','PORTAL_PROFISSIONAL','WHATSAPP_PARAR','ENCERRAMENTO','TROCA_TELEFONE')", name='ck_wac_origem'),
        CheckConstraint('ocorrido_em <= registrado_em', name='ck_wac_tempo'),
        CheckConstraint("origem = 'WHATSAPP_PARAR' OR usuario_id IS NOT NULL", name='ck_wac_autoria'),
        CheckConstraint("origem NOT IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO','PORTAL_PROFISSIONAL') OR chave IS NOT NULL", name='ck_wac_comando_humano'),
        CheckConstraint("estado <> 'REVOGADA' OR origem IN ('PORTAL_PROFISSIONAL','WHATSAPP_PARAR','ENCERRAMENTO','TROCA_TELEFONE')", name='ck_wac_origem_revogacao'),
        CheckConstraint("length(destino_sha256) = 64", name='ck_wac_destino'),
        CheckConstraint("estado <> 'AUTORIZADA' OR (origem IN ('PRESENCIAL','DOCUMENTO_ELETRONICO','CANAL_EXTERNO') AND usuario_id IS NOT NULL AND chave IS NOT NULL AND referencia_evidencia IS NOT NULL AND length(trim(referencia_evidencia)) >= 8 AND evidencia_sha256 IS NOT NULL AND length(evidencia_sha256) = 64 AND motivo IS NULL)", name='ck_wac_evidencia'),
        CheckConstraint("estado <> 'REVOGADA' OR (motivo IS NOT NULL AND motivo IN ('SOLICITACAO_TITULAR','ERRO_REGISTRO','ENCERRAMENTO','TROCA_TELEFONE','PARAR'))", name='ck_wac_revogacao'),
        CheckConstraint("(chave IS NULL AND comando_sha256 IS NULL) OR (chave IS NOT NULL AND length(chave) BETWEEN 16 AND 128 AND comando_sha256 IS NOT NULL AND length(comando_sha256) = 64 AND usuario_id IS NOT NULL)", name='ck_wac_chave'),
        CheckConstraint("origem <> 'WHATSAPP_PARAR' OR (estado='REVOGADA' AND usuario_id IS NULL AND conversa_id IS NOT NULL AND mensagem_id IS NOT NULL)", name='ck_wac_parar'),
        Index('uq_wac_raiz','acompanhamento_id',unique=True,postgresql_where=text('anterior_id IS NULL')),
        Index('uq_wac_evidencia','acompanhamento_id','evidencia_sha256',unique=True,postgresql_where=text("estado='AUTORIZADA'")),
        Index('ix_wac_historico','acompanhamento_id','id'),
    )

def upgrade():
    for name in ('usuarios','contextos_assistenciais','acompanhamentos_whatsapp','whatsapp_conversas_contextuais','whatsapp_mensagens'):
        Table(name,Base.metadata,autoload_with=op.get_bind())
    WhatsAppAutorizacaoComunicacao.__table__.create(op.get_bind())
    op.add_column('whatsapp_convite_envios', Column('autorizacao_comunicacao_id',Integer,nullable=True))
    op.create_foreign_key('fk_wce_autorizacao','whatsapp_convite_envios','whatsapp_autorizacoes_comunicacao',['autorizacao_comunicacao_id'],['id'],ondelete='RESTRICT')
    op.create_index('ix_wce_autorizacao','whatsapp_convite_envios',['autorizacao_comunicacao_id'])
    op.execute("""CREATE FUNCTION wac_preservar_historico() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'WHATSAPP_AUTHORIZATION_HISTORY_IMMUTABLE'; END; $$""")
    op.execute('CREATE TRIGGER wac_historico_imutavel BEFORE UPDATE OR DELETE ON whatsapp_autorizacoes_comunicacao FOR EACH ROW EXECUTE FUNCTION wac_preservar_historico()')

def downgrade():
    raise RuntimeError('Channel authorization evidence requires separately approved removal')
