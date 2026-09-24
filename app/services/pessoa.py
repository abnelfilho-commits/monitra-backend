"""Internal domain only. Caller owns transaction and access policy.

No router, automatic association, deduplication, or legacy synchronization.
"""
from datetime import datetime, timezone
from app.models.pessoa import Pessoa
from app.schemas.pessoa import PessoaCreate


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
        if not isinstance(changes, dict) or set(changes) - allowed:
            raise ValueError("Campos de Pessoa inválidos")
        row = db.query(Pessoa).filter(Pessoa.id == identity).with_for_update().one()
        data = {field: getattr(row, field) for field in allowed}
        data.update(changes)
        validated = PessoaCreate.model_validate(data)
        for field, value in validated.model_dump().items():
            setattr(row, field, value)
        row.atualizado_em = max(row.criado_em, datetime.now(timezone.utc))
        db.flush()
        return row
