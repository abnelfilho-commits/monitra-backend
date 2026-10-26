"""Operational communication ledger. Not clinical records or check-in answers."""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, ForeignKeyConstraint, UniqueConstraint, CheckConstraint, Index, func, text
from app.database import Base


class WhatsAppComunicacaoEvento(Base):
    __tablename__ = 'whatsapp_comunicacao_eventos'
    id = Column(Integer, primary_key=True)
    escopo = Column(String(80), nullable=False)
    anterior_id = Column(Integer, unique=True)
    phone_number_id = Column(String(128), nullable=False)
    destino_sha256 = Column(String(64), nullable=False)
    acompanhamento_id = Column(Integer)
    contexto_assistencial_id = Column(Integer)
    paciente_id = Column(Integer)
    instituicao_id = Column(Integer)
    estado = Column(String(16), nullable=False)
    origem = Column(String(32), nullable=False)
    mensagem_id = Column(String(512), ForeignKey('whatsapp_mensagens.message_id', ondelete='RESTRICT'), unique=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    chave = Column(String(64), nullable=False, unique=True)
    comando_sha256 = Column(String(64), nullable=False)
    evidencia_obtida_em = Column(DateTime(timezone=True))
    evidencia_referencia = Column(String(200))
    evidencia_sha256 = Column(String(64))
    ocorrido_em = Column(DateTime(timezone=True), nullable=False, server_default=func.clock_timestamp())
    __table_args__ = (
        UniqueConstraint('id','escopo',name='uq_wce_escopo'),
        ForeignKeyConstraint(['anterior_id','escopo'],['whatsapp_comunicacao_eventos.id','whatsapp_comunicacao_eventos.escopo'],ondelete='RESTRICT',name='fk_wce_anterior'),
        ForeignKeyConstraint(['acompanhamento_id','contexto_assistencial_id','paciente_id'],['acompanhamentos_whatsapp.id','acompanhamentos_whatsapp.contexto_assistencial_id','acompanhamentos_whatsapp.paciente_id'],ondelete='RESTRICT',name='fk_wce_acompanhamento'),
        ForeignKeyConstraint(['contexto_assistencial_id','instituicao_id'],['contextos_assistenciais.id','contextos_assistenciais.instituicao_id'],ondelete='RESTRICT',name='fk_wce_instituicao'),
        CheckConstraint("estado IN ('INTERROMPIDA','REATIVADA')",name='ck_wce_estado'),
        CheckConstraint("(acompanhamento_id IS NULL AND contexto_assistencial_id IS NULL AND paciente_id IS NULL AND instituicao_id IS NULL) OR (acompanhamento_id IS NOT NULL AND contexto_assistencial_id IS NOT NULL AND paciente_id IS NOT NULL AND instituicao_id IS NOT NULL)",name='ck_wce_contexto'),
        CheckConstraint("length(destino_sha256)=64 AND length(chave)=64 AND length(comando_sha256)=64 AND length(trim(phone_number_id))>0",name='ck_wce_identidade'),
        CheckConstraint("(estado='INTERROMPIDA' AND origem='WHATSAPP' AND mensagem_id IS NOT NULL AND usuario_id IS NULL) OR (estado='REATIVADA' AND origem='PROFISSIONAL' AND usuario_id IS NOT NULL AND mensagem_id IS NULL AND evidencia_referencia IS NOT NULL AND length(trim(evidencia_referencia))>=8 AND evidencia_sha256 IS NOT NULL AND length(evidencia_sha256)=64 AND evidencia_obtida_em IS NOT NULL AND evidencia_obtida_em <= ocorrido_em)",name='ck_wce_autoria'),
        Index('uq_wce_raiz','escopo',unique=True,postgresql_where=text('anterior_id IS NULL')),
        Index('ix_wce_acompanhamento','acompanhamento_id','id'),
    )


class WhatsAppRespostaExecucao(Base):
    __tablename__ = 'whatsapp_resposta_execucoes'
    mensagem_id = Column(String(512), ForeignKey('whatsapp_mensagens.message_id',ondelete='RESTRICT'),primary_key=True)
    phone_number_id = Column(String(128),nullable=False)
    destinatario = Column(String(15),nullable=False)
    conversa_contextual_id = Column(Integer,ForeignKey('whatsapp_conversas_contextuais.id',ondelete='RESTRICT'))
    conversa_legada_id = Column(Integer,ForeignKey('whatsapp_conversas.id',ondelete='RESTRICT'))
    origem = Column(String(24),nullable=False)
    estado = Column(String(24),nullable=False)
    wamid = Column(String(512))
    graph_http_status = Column(Integer)
    criado_em = Column(DateTime(timezone=True),nullable=False,server_default=func.clock_timestamp())
    iniciado_em = Column(DateTime(timezone=True))
    concluido_em = Column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint('phone_number_id','wamid',name='uq_wre_emissor_wamid'),
        CheckConstraint("estado IN ('PREPARADO','EM_EXECUCAO','CONFIRMADO','INCERTO','FALHA_DEFINITIVA')",name='ck_wre_estado'),
        CheckConstraint("(conversa_contextual_id IS NOT NULL AND conversa_legada_id IS NULL AND origem='SAUDE_MENTAL') OR (conversa_contextual_id IS NULL AND conversa_legada_id IS NOT NULL AND origem='LEGADO') OR (conversa_contextual_id IS NULL AND conversa_legada_id IS NULL AND origem='NAVEGACAO')",name='ck_wre_vinculo'),
        CheckConstraint("destinatario ~ '^[0-9]{8,15}$' AND length(trim(phone_number_id))>0",name='ck_wre_transporte'),
        CheckConstraint("estado <> 'CONFIRMADO' OR (wamid IS NOT NULL AND iniciado_em IS NOT NULL AND concluido_em IS NOT NULL)",name='ck_wre_confirmacao'),
    )
