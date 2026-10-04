"""Transversal authorship metadata; clinical responses remain in respostas_registro."""
from sqlalchemy import Column, Integer, String, ForeignKey, CheckConstraint
from app.database import Base


class RegistroProveniencia(Base):
    __tablename__ = 'registro_proveniencias'
    registro_id = Column(Integer, ForeignKey('registros_longitudinais.id', ondelete='RESTRICT'), primary_key=True)
    respondente_pessoa_id = Column(Integer, ForeignKey('pessoas.id', ondelete='RESTRICT'), nullable=False)
    registrador_pessoa_id = Column(Integer, ForeignKey('pessoas.id', ondelete='RESTRICT'), nullable=False)
    registrador_profissional_id = Column(Integer, ForeignKey('profissionais.id', ondelete='RESTRICT'))
    canal = Column(String(32), nullable=False)
    modalidade = Column(String(16), nullable=False)
    __table_args__ = (CheckConstraint(
        "(modalidade='ASSISTIDO' AND canal='PORTAL_PROFISSIONAL' AND registrador_profissional_id IS NOT NULL) OR "
        "(modalidade='AUTORRELATO' AND canal='WHATSAPP' AND registrador_profissional_id IS NULL AND registrador_pessoa_id=respondente_pessoa_id)",
        name='ck_registro_proveniencia_modalidade'),)
