"""Authorization belongs to a digital account, never a human role or membership."""
from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, UniqueConstraint, CheckConstraint, text
from app.database import Base


class UsuarioInstituicaoAcesso(Base):
    __tablename__ = 'usuario_instituicao_acessos'
    id = Column(Integer, primary_key=True)
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='RESTRICT'), nullable=False)
    instituicao_id = Column(Integer, ForeignKey('instituicoes.id', ondelete='RESTRICT'), nullable=False, index=True)
    perfil_institucional = Column(String(16), nullable=False)
    ativo = Column(Boolean, nullable=False, server_default=text('false'))
    __table_args__ = (
        UniqueConstraint('usuario_id', 'instituicao_id', name='uq_usuario_instituicao_acesso'),
        CheckConstraint("perfil_institucional IN ('GESTOR', 'PROFISSIONAL', 'SUPORTE')", name='ck_acesso_perfil_institucional'),
    )
