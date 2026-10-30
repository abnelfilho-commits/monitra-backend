"""Planned occurrences are never delivery authorization or Meta attempts."""
from sqlalchemy import (Column, Integer, String, DateTime, JSON, ForeignKey,
                        ForeignKeyConstraint, CheckConstraint, UniqueConstraint, Index, func)
from app.database import Base

STATES = ('AGENDADO', 'PROCESSANDO', 'EXECUTADO', 'CANCELADO', 'PERDIDO', 'BLOQUEADO')


class WhatsAppAgendaCheckin(Base):
    __tablename__ = 'whatsapp_agenda_checkins'
    id = Column(Integer, primary_key=True)
    acompanhamento_id = Column(Integer, ForeignKey('acompanhamentos_whatsapp.id', ondelete='RESTRICT'), nullable=False)
    previsto_em = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(16), nullable=False)
    programacao_versao = Column(Integer, nullable=False)
    conversa_id = Column(Integer)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    processamento_iniciado_em = Column(DateTime(timezone=True))
    processado_em = Column(DateTime(timezone=True))
    motivo_estado = Column(String(64), nullable=False)
    __table_args__ = (
        UniqueConstraint('acompanhamento_id', 'previsto_em', name='uq_wagc_instante'),
        UniqueConstraint('id', 'acompanhamento_id', name='uq_wagc_identidade'),
        ForeignKeyConstraint(['conversa_id', 'acompanhamento_id'],
            ['whatsapp_conversas_contextuais.id', 'whatsapp_conversas_contextuais.acompanhamento_whatsapp_id'],
            name='fk_wagc_conversa', ondelete='RESTRICT'),
        CheckConstraint("status IN ('AGENDADO','PROCESSANDO','EXECUTADO','CANCELADO','PERDIDO','BLOQUEADO')", name='ck_wagc_status'),
        CheckConstraint('programacao_versao > 0', name='ck_wagc_versao'),
        CheckConstraint('processado_em IS NULL OR processamento_iniciado_em IS NOT NULL', name='ck_wagc_processamento'),
        Index('ix_wagc_estado_instante', 'acompanhamento_id', 'status', 'previsto_em'),
    )


class WhatsAppAgendaEvento(Base):
    __tablename__ = 'whatsapp_agenda_eventos'
    id = Column(Integer, primary_key=True)
    acompanhamento_id = Column(Integer, ForeignKey('acompanhamentos_whatsapp.id', ondelete='RESTRICT'), nullable=False)
    ocorrencia_id = Column(Integer)
    programacao_versao = Column(Integer, nullable=False)
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'))
    origem = Column(String(32), nullable=False)
    motivo = Column(String(64), nullable=False)
    estado_anterior = Column(String(16))
    estado_novo = Column(String(16))
    configuracao = Column(JSON)
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['ocorrencia_id', 'acompanhamento_id'],
            ['whatsapp_agenda_checkins.id', 'whatsapp_agenda_checkins.acompanhamento_id'],
            name='fk_wage_ocorrencia', ondelete='RESTRICT'),
        CheckConstraint('programacao_versao > 0', name='ck_wage_versao'),
        CheckConstraint("estado_anterior IS NULL OR estado_anterior IN ('AGENDADO','PROCESSANDO','EXECUTADO','CANCELADO','PERDIDO','BLOQUEADO')", name='ck_wage_anterior'),
        CheckConstraint("estado_novo IS NULL OR estado_novo IN ('AGENDADO','PROCESSANDO','EXECUTADO','CANCELADO','PERDIDO','BLOQUEADO')", name='ck_wage_novo'),
        Index('ix_wage_acompanhamento', 'acompanhamento_id', 'id'),
    )
