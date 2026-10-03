"""Structural invariants; caller owns transaction and future authorization."""
from sqlalchemy.exc import IntegrityError
from app.models.contexto_assistencial import ContextoAssistencial as Contexto, ContextoAssistencialLinha as Linha
from app.models.institucional import PacienteInstituicao
from app.models.paciente import Paciente
from app.models.pessoa import Pessoa
from app.models.usuario import Usuario
from app.models.modular import ModuloClinico
from app.schemas.contexto_assistencial import ContextoCreate, ContextoClose, ContextoLinhaCreate


class ContextoAssistencialErro(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class ContextoAssistencialService:
    @staticmethod
    def _row(db, model, identity):
        if type(identity) is not int or identity <= 0:
            raise ContextoAssistencialErro('INVALID_ID')
        row = db.query(model).filter(model.id == identity).populate_existing().with_for_update().first()
        if row is None:
            raise ContextoAssistencialErro('RESOURCE_NOT_FOUND')
        return row

    @staticmethod
    def _period(link, start, end):
        if not link.ativo or start < link.data_inicio or (
                link.data_fim is not None and (end is None or end > link.data_fim)):
            raise ContextoAssistencialErro('LINK_PERIOD_OR_STATE_CONFLICT')

    @staticmethod
    def _flush(db, row, constraint, code, sqlstate):
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError as exc:
            if (getattr(exc.orig, 'pgcode', None) == sqlstate and
                getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None) == constraint):
                raise ContextoAssistencialErro(code) from exc
            raise
        return row

    def create(self, db, payload, *, actor_id):
        data = ContextoCreate.model_validate(payload)
        self._row(db, Usuario, actor_id)  # Provenance only; no ADMIN bypass or grant.
        link = self._row(db, PacienteInstituicao, data.paciente_instituicao_id)
        patient = self._row(db, Paciente, link.paciente_id)
        if patient.pessoa_id is None or db.get(Pessoa, patient.pessoa_id) is None:
            raise ContextoAssistencialErro('EXPLICIT_PERSON_REQUIRED')
        self._period(link, data.data_inicio, data.data_fim)
        row = Contexto(paciente_instituicao_id=link.id, paciente_id=link.paciente_id,
            instituicao_id=link.instituicao_id, data_inicio=data.data_inicio,
            data_fim=data.data_fim, criado_por_usuario_id=actor_id)
        return self._flush(db, row, 'ex_contexto_vigencia', 'CONTEXT_PERIOD_CONFLICT', '23P01')

    def close(self, db, identity, payload):
        end = ContextoClose.model_validate(payload).data_fim
        row = self._row(db, Contexto, identity)
        if not row.ativo:
            raise ContextoAssistencialErro('CONTEXT_INVALIDATED')
        if row.data_fim is not None:
            if row.data_fim == end:
                return row
            raise ContextoAssistencialErro('CONTEXT_ALREADY_CLOSED')
        if end < row.data_inicio:
            raise ContextoAssistencialErro('INVALID_PERIOD')
        link = self._row(db, PacienteInstituicao, row.paciente_instituicao_id)
        self._period(link, row.data_inicio, end)
        with db.begin_nested():
            row.data_fim = end
            db.flush()
        return row

    def invalidate(self, db, identity):
        row = self._row(db, Contexto, identity)
        with db.begin_nested():
            row.ativo = False
            db.flush()
        return row

    def add_line(self, db, payload):
        data = ContextoLinhaCreate.model_validate(payload)
        context = self._row(db, Contexto, data.contexto_assistencial_id)
        if not context.ativo or context.data_fim is not None:
            raise ContextoAssistencialErro('CONTEXT_NOT_OPEN')
        self._row(db, ModuloClinico, data.modulo_id)
        return self._flush(db, Linha(**data.model_dump()), 'uq_contexto_linha', 'CONTEXT_LINE_DUPLICATE', '23505')

    def deactivate_line(self, db, context_id, line_id):
        self._row(db, Contexto, context_id)
        row = self._row(db, Linha, line_id)
        if row.contexto_assistencial_id != context_id:
            raise ContextoAssistencialErro('CONTEXT_LINE_MISMATCH')
        with db.begin_nested():
            row.ativo = False
            db.flush()
        return row
