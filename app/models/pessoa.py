"""Canonical human identity; never an authorization or reconciliation source."""
from sqlalchemy import Boolean, CheckConstraint, Column, Date, DateTime, Identity, Integer, String, Text, UniqueConstraint, func, text
from app.database import Base


class Pessoa(Base):
    __tablename__ = "pessoas"
    __table_args__ = (
        UniqueConstraint("cpf", name="uq_pessoas_cpf"),
        CheckConstraint("nome_completo = trim(nome_completo) AND length(nome_completo) > 0", name="ck_pessoas_nome_completo"),
        *(CheckConstraint(f"{field} IS NULL OR ({field} = trim({field}) AND length({field}) > 0)", name=f"ck_pessoas_{field}")
          for field in ("nome_social", "sexo", "email", "telefone")),
        CheckConstraint("cpf IS NULL OR cpf ~ '^[0-9]{11}$'", name="ck_pessoas_cpf_formato").ddl_if(dialect="postgresql"),
        CheckConstraint("atualizado_em >= criado_em", name="ck_pessoas_timestamps"),
    )

    id = Column(Integer, Identity(always=False), primary_key=True)
    nome_completo = Column(Text, nullable=False)
    nome_social = Column(Text)
    data_nascimento = Column(Date)
    sexo = Column(String(32))
    cpf = Column(String(11))
    email = Column(Text)
    telefone = Column(String(32))
    ativo = Column(Boolean, nullable=False, server_default=text("true"))
    criado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
