from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base

class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    senha_hash = Column(String, nullable=False)
    perfil = Column(String, default="PROFISSIONAL")

    clinica_id = Column(Integer, ForeignKey("clinicas.id"))
    profissional_id = Column(Integer, ForeignKey("profissionais.id"), nullable=True)

    clinica = relationship("Clinica")
    profissional = relationship("Profissional")

    ativo = Column(Boolean, default=True)

    

