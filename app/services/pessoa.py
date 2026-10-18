"""Internal domain only. Caller owns transaction and access policy.

No router, automatic association, deduplication, or legacy synchronization.
"""
from datetime import datetime, timezone
from sqlalchemy import func, literal_column, or_
from app.models.pessoa import Pessoa
from app.schemas.pessoa import PessoaCreate, PessoaDados


class PessoaService:
    @staticmethod
    def create(db, payload):
        data = payload.model_dump() if isinstance(payload, PessoaCreate) else payload
        validated = PessoaCreate.model_validate(data)
        row = Pessoa(**validated.model_dump())
        db.add(row)
        db.flush()  # UNIQUE conflict propagates; never returns an existing person.
        return row

    @staticmethod
    def update(db, identity, changes):
        allowed = set(PessoaCreate.model_fields)
        if not isinstance(changes, dict) or set(changes) - allowed or "cpf" in changes:
            raise ValueError("Campos de Pessoa inválidos")
        row = db.query(Pessoa).filter(Pessoa.id == identity).with_for_update().one()
        data = {field: getattr(row, field) for field in allowed}
        data.update(changes)
        validated = PessoaDados.model_validate(data)
        for field, value in validated.model_dump().items():
            setattr(row, field, value)
        row.atualizado_em = max(row.criado_em, datetime.now(timezone.utc))
        db.flush()
        return row


    @staticmethod
    def get(db, identity):
        return db.query(Pessoa).filter(Pessoa.id == identity).one_or_none()

    @staticmethod
    def list(db, *, offset=0, limit=50, nome=None, cpf=None):
        query = db.query(Pessoa)
        if nome:
            # Native PostgreSQL UTF8 functions; no unaccent extension required.
            # NFD separates accents from letters, including decomposed input.
            def folded(value):
                return func.lower(func.regexp_replace(
                    func.normalize(value, literal_column("NFD")),
                    "[\u0300-\u036f\u1ab0-\u1aff\u1dc0-\u1dff\u20d0-\u20ff\ufe20-\ufe2f]", "", "g"))

            term = folded(nome)
            # strpos treats %, _ and backslashes literally (no wildcard input).
            query = query.filter(or_(
                func.strpos(folded(Pessoa.nome_completo), term) > 0,
                func.strpos(folded(Pessoa.nome_social), term) > 0))
        if cpf:
            query = query.filter(Pessoa.cpf == cpf)
        return query.order_by(Pessoa.id).offset(offset).limit(limit).all()
