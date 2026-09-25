"""Canonical institutional domain. Caller owns the transaction and access policy.

No public router is added until a separate institutional authorization gate.
No legacy record is backfilled, synchronized, or interpreted as permission.
"""
from datetime import date
from sqlalchemy import text, or_
from sqlalchemy.exc import IntegrityError
from app.models.institucional import (Instituicao, InstituicaoPapel, PacienteInstituicao,
                                     ProfissionalInstituicao, PacienteProfissional)
from app.schemas.institucional import (InstituicaoCreate, PapelCreate, PacienteInstituicaoCreate,
                                      ProfissionalInstituicaoCreate, PacienteProfissionalCreate)
from app.models.usuario import Usuario
from app.models.institucional_operacao import InstitucionalOperacao


class InstitucionalErro(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


LINKS = {
    PacienteInstituicao: ('PACIENTE_INSTITUICAO', 'paciente_instituicao_id', ('paciente_id', 'instituicao_id', 'tipo_vinculo')),
    ProfissionalInstituicao: ('PROFISSIONAL_INSTITUICAO', 'profissional_instituicao_id', ('profissional_id', 'instituicao_id', 'ocupacao_id')),
    PacienteProfissional: ('PACIENTE_PROFISSIONAL', 'paciente_profissional_id', ('paciente_id', 'profissional_instituicao_id')),
}
EXCLUSIONS = {'ex_paciente_instituicao_vigencia', 'ex_profissional_instituicao_vigencia', 'ex_paciente_profissional_vigencia'}


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

    def create(self, db, model, payload, *, actor_id=None, motivo=None):
        contract = self.CONTRACTS[model]
        data = contract(**(payload.model_dump() if hasattr(payload, 'model_dump') else payload)).model_dump()
        if model in LINKS:
            self._write_gate(db, actor_id, motivo)
            try:
                with db.begin_nested():
                    return self._create_link(db, model, data, actor_id, motivo)
            except IntegrityError as exc:
                # Only the frozen G1 exclusion constraints mean period conflict.
                if getattr(exc.orig, 'pgcode', None) == '23P01' and getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None) in EXCLUSIONS:
                    raise InstitucionalErro('PERIOD_CONFLICT') from exc
                raise
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
    def _admin(db, actor_id):
        if not db.query(Usuario).filter_by(id=actor_id, ativo=True, perfil='ADMIN').first():
            raise InstitucionalErro('ADMIN_REQUIRED')

    def _write_gate(self, db, actor_id, motivo):
        # No implicit flush of unrelated caller changes at SAVEPOINT entry.
        if db.new or db.dirty or db.deleted:
            raise InstitucionalErro('CLEAN_SESSION_REQUIRED')
        if not isinstance(motivo, str) or not motivo.strip():
            raise InstitucionalErro('REASON_REQUIRED')
        if db.execute(text('SHOW transaction_isolation')).scalar() != 'read committed':
            raise InstitucionalErro('READ_COMMITTED_REQUIRED')
        # Deliberately coarse domain lock: all canonical mutations use the same
        # order, including parent CLOSE/INVALIDATE and child CREATE. No stale
        # repeatable-read snapshots and no SELECT-before-INSERT race.
        db.execute(text('SELECT pg_advisory_xact_lock(572001)'))
        self._admin(db, actor_id)

    @staticmethod
    def _row(db, model, identity):
        row = db.query(model).filter_by(id=identity).populate_existing().with_for_update().first()
        if row is None:
            raise InstitucionalErro('LINK_NOT_FOUND')
        return row

    @staticmethod
    def _snapshot(row):
        # Domain keys and temporal state only; no personal attributes/credentials.
        return {c.name: (getattr(row, c.name).isoformat() if isinstance(getattr(row, c.name), date) else getattr(row, c.name))
                for c in row.__table__.columns if c.name not in ('criado_em', 'atualizado_em')}

    def _audit(self, db, row, actor, reason, operation, result, previous):
        kind, column, _ = LINKS[type(row)]
        institution = (db.get(ProfissionalInstituicao, row.profissional_instituicao_id).instituicao_id
                       if isinstance(row, PacienteProfissional) else row.instituicao_id)
        db.add(InstitucionalOperacao(ator_usuario_id=actor, instituicao_id=institution,
            operacao=operation, tipo_alvo=kind, **{column: row.id}, motivo=reason.strip(),
            resultado=result, estado_anterior=previous, estado_final=self._snapshot(row)))
        db.flush()

    @staticmethod
    def _contains(parent, start, end):
        return parent.ativo and start >= parent.data_inicio and (
            parent.data_fim is None or (end is not None and end <= parent.data_fim))

    def _create_link(self, db, model, data, actor, reason):
        if model is PacienteProfissional:
            patient = self._row(db, PacienteInstituicao, data['paciente_instituicao_id'])
            professional = self._row(db, ProfissionalInstituicao, data['profissional_instituicao_id'])
            if patient.paciente_id != data['paciente_id']:
                raise InstitucionalErro('PATIENT_MISMATCH')
            if patient.instituicao_id != professional.instituicao_id:
                raise InstitucionalErro('INSTITUTION_MISMATCH')
            if not all(self._contains(p, data['data_inicio'], data['data_fim']) for p in (patient, professional)):
                raise InstitucionalErro('PARENT_PERIOD_OR_STATE_CONFLICT')
        keys = LINKS[model][2]  # Exactly the G1 EXCLUDE equality keys.
        candidates = db.query(model).filter_by(**{k: data[k] for k in keys}).populate_existing().all()
        for row in candidates:
            same = all(getattr(row, k) == v for k, v in data.items())
            if same:
                return row  # Semantic idempotence: no write and no new audit event.
            overlap = ((row.data_fim is None or data['data_inicio'] <= row.data_fim) and
                       (data['data_fim'] is None or row.data_inicio <= data['data_fim']))
            if row.ativo and overlap:
                raise InstitucionalErro('PERIOD_CONFLICT')
        row = model(**data)
        db.add(row)
        db.flush()
        self._audit(db, row, actor, reason, 'CREATE_LINK', 'CREATED', None)
        return row

    @staticmethod
    def _dependencies(db, row, end=None, invalidating=False):
        if isinstance(row, PacienteProfissional):
            return
        child = PacienteProfissional
        field = child.paciente_instituicao_id if isinstance(row, PacienteInstituicao) else child.profissional_instituicao_id
        direct = db.query(child).filter(field == row.id, child.ativo.is_(True))
        if not invalidating:
            direct = direct.filter(or_(child.data_fim.is_(None), child.data_fim > end))
        if direct.first() is not None:
            raise InstitucionalErro('DEPENDENT_LINK_CONFLICT')
        if not isinstance(row, PacienteInstituicao):
            return  # Professional side always uses the existing explicit FK.
        legacy = db.query(child).join(ProfissionalInstituicao,
            child.profissional_instituicao_id == ProfissionalInstituicao.id).filter(
                child.paciente_id == row.paciente_id, child.paciente_instituicao_id.is_(None),
                ProfissionalInstituicao.instituicao_id == row.instituicao_id, child.ativo.is_(True))
        # D2: INVALIDATE affects the whole original period; CLOSE affects only
        # (requested end, original end]. Inclusive date boundaries stay intact.
        if invalidating:
            legacy = legacy.filter(or_(child.data_fim.is_(None), child.data_fim >= row.data_inicio))
        else:
            legacy = legacy.filter(or_(child.data_fim.is_(None), child.data_fim > end))
        if row.data_fim is not None:
            legacy = legacy.filter(child.data_inicio <= row.data_fim)
        if legacy.first() is not None:
            raise InstitucionalErro('LEGACY_CONTEXT_UNRESOLVED')

    def close(self, db, model, identity, end, *, actor_id=None, motivo=None):
        if model not in LINKS or type(end) is not date:
            raise InstitucionalErro('INVALID_CLOSE')
        self._write_gate(db, actor_id, motivo)
        with db.begin_nested():
            row = self._row(db, model, identity)
            if not row.ativo:
                raise InstitucionalErro('LINK_INVALIDATED')
            if end < row.data_inicio:
                raise InstitucionalErro('INVALID_PERIOD')
            if row.data_fim == end:
                return row
            if row.data_fim is not None:
                raise InstitucionalErro('CLOSE_CONFLICT')  # No silent overwrite/reopening.
            self._dependencies(db, row, end=end)
            before = self._snapshot(row)
            row.data_fim = end
            db.flush()
            self._audit(db, row, actor_id, motivo, 'CLOSE_LINK', 'CLOSED', before)
            return row

    def invalidate(self, db, model, identity, *, actor_id=None, motivo=None):
        if model not in LINKS:
            raise InstitucionalErro('INVALID_TARGET')
        self._write_gate(db, actor_id, motivo)
        with db.begin_nested():
            row = self._row(db, model, identity)
            if not row.ativo:
                return row
            self._dependencies(db, row, invalidating=True)
            before = self._snapshot(row)
            row.ativo = False
            db.flush()
            self._audit(db, row, actor_id, motivo, 'INVALIDATE_LINK', 'INVALIDATED', before)
            return row

    def get(self, db, model, identity, *, actor_id):
        if model not in LINKS:
            raise InstitucionalErro('INVALID_TARGET')
        self._admin(db, actor_id)
        row = db.get(model, identity, populate_existing=True)
        if row is None:
            raise InstitucionalErro('LINK_NOT_FOUND')
        return row

    def list(self, db, model, *, instituicao_id, actor_id):
        if model not in LINKS or instituicao_id is None:
            raise InstitucionalErro('EXPLICIT_INSTITUTION_REQUIRED')
        self._admin(db, actor_id)
        query = db.query(model)
        if model is PacienteProfissional:
            query = query.join(ProfissionalInstituicao).filter(ProfissionalInstituicao.instituicao_id == instituicao_id)
        else:
            query = query.filter(model.instituicao_id == instituicao_id)
        return query.order_by(model.id).populate_existing().all()

    @staticmethod
    def state(row, reference_date):
        if not row.ativo:
            return 'INVALIDADO'
        if row.data_inicio > reference_date:
            return 'FUTURO'
        if row.data_fim is not None and row.data_fim < reference_date:
            return 'ENCERRADO'
        return 'VIGENTE'

    @staticmethod
    def effective(db, model, reference_date):
        if model not in (PacienteInstituicao, ProfissionalInstituicao, PacienteProfissional):
            raise ValueError('Vínculo temporal obrigatório')
        return db.query(model).filter(model.ativo.is_(True), model.data_inicio <= reference_date,
            or_(model.data_fim.is_(None), model.data_fim >= reference_date))
