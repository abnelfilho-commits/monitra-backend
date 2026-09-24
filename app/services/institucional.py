"""Canonical institutional domain. Caller owns the transaction and access policy.

No public router is added until a separate institutional authorization gate.
No legacy record is backfilled, synchronized, or interpreted as permission.
"""
from sqlalchemy import text, or_
from app.models.institucional import (Instituicao, InstituicaoPapel, PacienteInstituicao,
                                     ProfissionalInstituicao, PacienteProfissional)
from app.schemas.institucional import (InstituicaoCreate, PapelCreate, PacienteInstituicaoCreate,
                                      ProfissionalInstituicaoCreate, PacienteProfissionalCreate)


class InstitucionalService:
    CONTRACTS = {
        Instituicao: InstituicaoCreate,
        InstituicaoPapel: PapelCreate,
        PacienteInstituicao: PacienteInstituicaoCreate,
        ProfissionalInstituicao: ProfissionalInstituicaoCreate,
        PacienteProfissional: PacienteProfissionalCreate,
    }

    @staticmethod
    def hierarchy_lock(db):
        # All hierarchy writes through this domain share one transaction lock.
        # Acquire before graph reads, so concurrent READ COMMITTED writers see
        # the preceding committed graph. Reject isolation with stale snapshots.
        if db.execute(text('SHOW transaction_isolation')).scalar() != 'read committed':
            raise ValueError('Hierarquia exige transação READ COMMITTED')
        db.execute(text('SELECT pg_advisory_xact_lock(571001)'))

    @staticmethod
    def validate_parent(db, identity, parent):
        seen = set()
        while parent is not None:
            if parent == identity or parent in seen:
                raise ValueError('Ciclo institucional não permitido')
            seen.add(parent)
            row = db.get(Instituicao, parent, populate_existing=True)
            if row is None:
                raise ValueError('Instituição pai inexistente')
            parent = row.instituicao_pai_id

    def create(self, db, model, payload):
        contract = self.CONTRACTS[model]
        data = contract(**(payload.model_dump() if hasattr(payload, 'model_dump') else payload)).model_dump()
        if model is Instituicao:
            self.hierarchy_lock(db)
            self.validate_parent(db, None, data['instituicao_pai_id'])
        row = model(**data)
        db.add(row)
        db.flush()  # FK/UNIQUE/CHECK/exclusion failures propagate; caller rolls back.
        return row

    def set_parent(self, db, identity, parent):
        self.hierarchy_lock(db)
        row = db.get(Instituicao, identity, populate_existing=True)
        if row is None:
            raise ValueError('Instituição inexistente')
        self.validate_parent(db, identity, parent)
        row.instituicao_pai_id = parent
        db.flush()
        return row

    @staticmethod
    def close(db, model, identity, end):
        if model not in (PacienteInstituicao, ProfissionalInstituicao, PacienteProfissional):
            raise ValueError('Vínculo temporal obrigatório')
        row = db.query(model).filter(model.id == identity).with_for_update().one()
        if end < row.data_inicio:
            raise ValueError('data_fim anterior a data_inicio')
        row.data_fim = end
        # Keep administrative state: inclusive historical validity is preserved.
        db.flush()
        return row

    @staticmethod
    def effective(db, model, reference_date):
        if model not in (PacienteInstituicao, ProfissionalInstituicao, PacienteProfissional):
            raise ValueError('Vínculo temporal obrigatório')
        return db.query(model).filter(model.ativo.is_(True), model.data_inicio <= reference_date,
            or_(model.data_fim.is_(None), model.data_fim >= reference_date))
