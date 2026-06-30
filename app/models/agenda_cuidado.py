from sqlalchemy import Column, Integer, String, Text, Date, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base


class AgendaCuidado(Base):
    __tablename__ = "agenda_cuidados"

    id = Column(Integer, primary_key=True, index=True)

    pts_id = Column(Integer, ForeignKey("pts.id"), nullable=False)
    objetivo_id = Column(Integer, ForeignKey("pts_objetivos.id"), nullable=False)

    atividade_id = Column(
        Integer,
        ForeignKey("atividades_terapeuticas.id"),
        nullable=False
    )

    ocupacao_id = Column(
        Integer,
        ForeignKey("ocupacoes_profissionais.id"),
        nullable=False
    )

    frequencia_semanal = Column(Integer, nullable=False)
    duracao_minutos = Column(Integer, nullable=False)

    data_inicio = Column(Date, nullable=False)
    data_fim = Column(Date, nullable=True)

    status = Column(String(30), nullable=False, default="PLANEJADO")

    observacoes = Column(Text, nullable=True)
    
    status_execucao = Column(
        String(30),
        default="PLANEJADO"
    )

    data_realizacao = Column(Date)

    observacao_execucao = Column(Text)

    created_at = Column(DateTime, server_default=func.now())    

    pts = relationship("PTS")
    objetivo = relationship("PTSObjetivo")
    atividade = relationship("AtividadeTerapeutica")
    ocupacao = relationship("OcupacaoProfissional")