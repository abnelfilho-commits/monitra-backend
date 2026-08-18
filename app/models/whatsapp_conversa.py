from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    DateTime,
    ForeignKey,
    JSON,
)
from sqlalchemy.sql import func

from app.database import Base


class WhatsAppConversa(Base):
    __tablename__ = "whatsapp_conversas"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    responsavel_id = Column(
        Integer,
        ForeignKey("responsaveis.id"),
        nullable=False,
        index=True,
    )

    paciente_id = Column(
        Integer,
        ForeignKey("pacientes.id"),
        nullable=True,
        index=True,
    )

    telefone = Column(
        String(30),
        nullable=False,
        index=True,
    )

    etapa_atual = Column(
        String(50),
        nullable=False,
        default="INICIO",
    )

    data_referencia = Column(
        Date,
        nullable=True,
    )

    respostas_json = Column(
        JSON,
        nullable=False,
        default=dict,
    )

    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )