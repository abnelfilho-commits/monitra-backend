"""W1B administrative commands only. Caller owns transaction; no resource evaluator."""
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, ProfissionalInstituicao
from app.models.contexto_assistencial import ContextoAssistencial
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.permissao_assistencial import ContextoProfissional as Participation, ConcessaoAssistencial as Grant, AutoridadeDelegacao as Authority
from app.schemas.permissao_assistencial import ParticipationCreate, ParticipationClose, GrantCommand, AuthorityCommand, RevocationCommand


class PermissaoAssistencialErro(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class PermissaoAssistencialService:
    @staticmethod
    def _id(value):
        if type(value) is not int or not 0 < value <= 2147483647:
            raise PermissaoAssistencialErro('INVALID_ID')

    @classmethod
    def lock_institution(cls, db, institution):
        cls._id(institution)
        if db.execute(text('SHOW transaction_isolation')).scalar() != 'read committed':
            raise PermissaoAssistencialErro('READ_COMMITTED_REQUIRED')
        # Existing PostgreSQL advisory-lock pattern, namespaced by institution.
        db.execute(text('SELECT pg_advisory_xact_lock(572002, :institution)'), {'institution': institution})

    @classmethod
    def _row(cls, db, model, identity):
        cls._id(identity)
        row = db.query(model).filter_by(id=identity).populate_existing().first()
        if row is None:
            raise PermissaoAssistencialErro('RESOURCE_NOT_FOUND')
        return row

    @staticmethod
    def _now():
        return datetime.now(timezone.utc)

    def _person(self, db, user):
        if user.pessoa_id is None:
            raise PermissaoAssistencialErro('VALID_PERSON_REQUIRED')
        person = self._row(db, Pessoa, user.pessoa_id)
        if not person.ativo:
            raise PermissaoAssistencialErro('VALID_PERSON_REQUIRED')

    def _gate(self, db, actor_id, institution, *, admin=False, inactive_institution=False):
        if db.new or db.dirty or db.deleted:
            raise PermissaoAssistencialErro('CLEAN_SESSION_REQUIRED')
        self.lock_institution(db, institution)
        # Same order for every command and the G2.C root-deactivation integration.
        db.query(Root).filter_by(instituicao_id=institution).order_by(Root.id).populate_existing().with_for_update().all()
        actor = self._row(db, Usuario, actor_id)
        if not actor.ativo or (admin and actor.perfil != 'ADMIN'):
            raise PermissaoAssistencialErro('ADMIN_REQUIRED' if admin else 'ACTOR_INACTIVE')
        inst = self._row(db, Instituicao, institution)
        if not inactive_institution and not inst.ativo:
            raise PermissaoAssistencialErro('INSTITUTION_INACTIVE')
        if not admin:
            self._person(db, actor)
        return actor

    def _root(self, db, identity, institution):
        root = self._row(db, Root, identity)
        if root.instituicao_id != institution:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        if not root.ativo:
            raise PermissaoAssistencialErro('ROOT_INACTIVE')
        user = self._row(db, Usuario, root.usuario_id)
        if not user.ativo:
            raise PermissaoAssistencialErro('USER_INACTIVE')
        self._person(db, user)
        return root

    def _context(self, db, identity, institution):
        context = self._row(db, ContextoAssistencial, identity)
        if context.instituicao_id != institution:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        if not context.ativo:
            raise PermissaoAssistencialErro('CONTEXT_INVALIDATED')
        return context

    def _eligible_authorities(self, db, institution, actor_id=None):
        query = db.query(Authority).join(Root, Root.id == Authority.usuario_instituicao_acesso_id).join(
            Usuario, Usuario.id == Root.usuario_id).join(Pessoa, Pessoa.id == Usuario.pessoa_id).filter(
                Authority.instituicao_id == institution, Root.instituicao_id == institution,
                Authority.revogado_em.is_(None), Root.ativo.is_(True), Usuario.ativo.is_(True), Pessoa.ativo.is_(True))
        if actor_id is not None:
            query = query.filter(Usuario.id == actor_id)
        rows = query.order_by(Authority.id).populate_existing().all()
        # Only metadata; contextual envelopes on invalidated contexts are ineligible.
        contexts = {r.id for r in db.query(ContextoAssistencial.id).filter(
            ContextoAssistencial.instituicao_id == institution, ContextoAssistencial.ativo.is_(True)).all()}
        return [r for r in rows if r.envelope_tipo == 'INSTITUICAO' or r.contexto_assistencial_id in contexts]

    def _authority(self, db, actor_id, institution, capability, scope, context):
        for row in self._eligible_authorities(db, institution, actor_id):
            if row.capacidade_delegavel == capability and (row.envelope_tipo == 'INSTITUICAO' or
                    (scope == 'CONTEXTO' and row.contexto_assistencial_id == context)):
                return row
        raise PermissaoAssistencialErro('AUTHORITY_DENIED')

    def _participation_authority(self, db, actor_id, institution, context):
        row = db.query(Grant.id).join(Root, Root.id == Grant.usuario_instituicao_acesso_id).filter(
            Root.usuario_id == actor_id, Root.instituicao_id == institution, Root.ativo.is_(True),
            Grant.instituicao_id == institution, Grant.capacidade == 'CONTEXTO_ADMINISTRAR',
            Grant.revogado_em.is_(None),
            ((Grant.escopo_tipo == 'INSTITUICAO') | ((Grant.escopo_tipo == 'CONTEXTO') & (Grant.contexto_assistencial_id == context)))).first()
        if row is None:
            raise PermissaoAssistencialErro('CONTEXT_ADMINISTRATION_DENIED')

    def create_participation(self, db, payload, *, actor_id):
        data = ParticipationCreate.model_validate(payload)
        self._gate(db, actor_id, data.instituicao_id)
        self._context(db, data.contexto_assistencial_id, data.instituicao_id)
        self._participation_authority(db, actor_id, data.instituicao_id, data.contexto_assistencial_id)
        link = self._row(db, ProfissionalInstituicao, data.profissional_instituicao_id)
        if link.instituicao_id != data.instituicao_id:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        professional = self._row(db, Profissional, link.profissional_id)
        if not professional.ativo:
            raise PermissaoAssistencialErro('PROFESSIONAL_INACTIVE')
        self._person(db, professional)
        today = self._now().date()
        if (not link.ativo or link.data_inicio > today or (link.data_fim is not None and link.data_fim < today)
                or data.data_inicio < link.data_inicio or (link.data_fim is not None and (data.data_fim is None or data.data_fim > link.data_fim))):
            raise PermissaoAssistencialErro('PROFESSIONAL_LINK_INELIGIBLE')
        row = Participation(**data.model_dump(exclude={'motivo'}), criado_por_usuario_id=actor_id, motivo_criacao=data.motivo)
        try:
            with db.begin_nested():
                db.add(row); db.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, 'pgcode', None) == '23P01' and getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None) == 'ex_participacao_vigencia':
                raise PermissaoAssistencialErro('PARTICIPATION_PERIOD_CONFLICT') from exc
            raise
        return row

    def _participation(self, db, data, actor_id):
        self._gate(db, actor_id, data.instituicao_id)
        row = self._row(db, Participation, data.id)
        if row.instituicao_id != data.instituicao_id:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        self._context(db, row.contexto_assistencial_id, data.instituicao_id)
        self._participation_authority(db, actor_id, data.instituicao_id, row.contexto_assistencial_id)
        return row

    def close_participation(self, db, payload, *, actor_id):
        data = ParticipationClose.model_validate(payload)
        row = self._participation(db, data, actor_id)
        if row.invalidado_em is not None:
            raise PermissaoAssistencialErro('PARTICIPATION_INVALIDATED')
        if row.encerrado_em is not None:
            if row.data_fim == data.data_fim:
                return row
            raise PermissaoAssistencialErro('PARTICIPATION_ALREADY_CLOSED')
        if data.data_fim < row.data_inicio or (row.data_fim is not None and data.data_fim > row.data_fim):
            raise PermissaoAssistencialErro('INVALID_PERIOD')
        with db.begin_nested():
            row.data_fim = data.data_fim
            row.encerrado_por_usuario_id = actor_id; row.encerrado_em = self._now(); row.motivo_encerramento = data.motivo
            db.flush()
        return row

    def invalidate_participation(self, db, payload, *, actor_id):
        data = RevocationCommand.model_validate(payload)
        row = self._participation(db, data, actor_id)
        if row.invalidado_em is None:
            with db.begin_nested():
                row.invalidado_por_usuario_id = actor_id; row.invalidado_em = self._now(); row.motivo_invalidacao = data.motivo
                db.flush()
        return row

    def grant(self, db, payload, *, actor_id):
        data = GrantCommand.model_validate(payload)
        self._gate(db, actor_id, data.instituicao_id)
        target = self._root(db, data.usuario_instituicao_acesso_id, data.instituicao_id)
        if target.usuario_id == actor_id:
            raise PermissaoAssistencialErro('SELF_GRANT_DENIED')
        if data.contexto_assistencial_id is not None:
            self._context(db, data.contexto_assistencial_id, data.instituicao_id)
        authority = self._authority(db, actor_id, data.instituicao_id, data.capacidade, data.escopo_tipo, data.contexto_assistencial_id)
        row = db.query(Grant).filter_by(usuario_instituicao_acesso_id=target.id, capacidade=data.capacidade,
            escopo_tipo=data.escopo_tipo, contexto_assistencial_id=data.contexto_assistencial_id, revogado_em=None).populate_existing().first()
        if row is not None:
            return row  # Original provenance/motive is intentionally preserved.
        with db.begin_nested():
            row = Grant(**data.model_dump(exclude={'motivo'}), autoridade_delegacao_id=authority.id,
                        concedido_por_usuario_id=actor_id, motivo_concessao=data.motivo)
            db.add(row); db.flush()
        return row

    @staticmethod
    def _revoke(row, actor_id, now, reason, origin):
        if row.revogado_em is None:
            row.revogado_por_usuario_id = actor_id; row.revogado_em = now
            row.motivo_revogacao = reason; row.revogacao_origem = origin

    def revoke(self, db, payload, *, actor_id):
        data = RevocationCommand.model_validate(payload)
        self._gate(db, actor_id, data.instituicao_id)
        row = self._row(db, Grant, data.id)
        if row.instituicao_id != data.instituicao_id:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        self._authority(db, actor_id, data.instituicao_id, row.capacidade, row.escopo_tipo, row.contexto_assistencial_id)
        with db.begin_nested():
            self._revoke(row, actor_id, self._now(), data.motivo, 'ADMINISTRATIVA'); db.flush()
        return row

    def _nominate(self, db, payload, actor_id, origin):
        data = AuthorityCommand.model_validate(payload)
        self._gate(db, actor_id, data.instituicao_id, admin=True)
        target = self._root(db, data.usuario_instituicao_acesso_id, data.instituicao_id)
        if target.usuario_id == actor_id:
            raise PermissaoAssistencialErro('SELF_DELEGATION_DENIED')
        history = db.query(Authority.id).filter_by(instituicao_id=data.instituicao_id).first()
        if origin == 'BOOTSTRAP' and history is not None:
            raise PermissaoAssistencialErro('BOOTSTRAP_ALREADY_PERFORMED')
        if origin == 'RECOVERY' and history is None:
            raise PermissaoAssistencialErro('INITIAL_BOOTSTRAP_REQUIRED')
        eligible = self._eligible_authorities(db, data.instituicao_id)
        for envelope in data.envelopes:
            if envelope.contexto_assistencial_id is not None:
                self._context(db, envelope.contexto_assistencial_id, data.instituicao_id)
            if origin == 'RECOVERY' and any(a.capacidade_delegavel == envelope.capacidade_delegavel and (
                    a.envelope_tipo == 'INSTITUICAO' or envelope.envelope_tipo == 'INSTITUICAO' or
                    a.contexto_assistencial_id == envelope.contexto_assistencial_id) for a in eligible):
                raise PermissaoAssistencialErro('ELIGIBLE_AUTHORITY_EXISTS')
        operation = uuid4(); now = self._now(); rows = []
        with db.begin_nested():
            for envelope in data.envelopes:
                row = Authority(**envelope.model_dump(), instituicao_id=data.instituicao_id,
                    usuario_instituicao_acesso_id=target.id, origem=origin, operacao_id=operation,
                    concedido_por_usuario_id=actor_id, concedido_em=now, motivo_concessao=data.motivo)
                db.add(row); db.flush(); rows.append(row)
        return rows

    def bootstrap(self, db, payload, *, actor_id):
        return self._nominate(db, payload, actor_id, 'BOOTSTRAP')

    def recovery(self, db, payload, *, actor_id):
        return self._nominate(db, payload, actor_id, 'RECOVERY')

    def revoke_authority(self, db, payload, *, actor_id):
        data = RevocationCommand.model_validate(payload)
        self._gate(db, actor_id, data.instituicao_id, admin=True, inactive_institution=True)
        row = self._row(db, Authority, data.id)
        if row.instituicao_id != data.instituicao_id:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        if self._row(db, Root, row.usuario_instituicao_acesso_id).usuario_id == actor_id:
            raise PermissaoAssistencialErro('SELF_AUTHORITY_REVOCATION_DENIED')
        with db.begin_nested():
            self._revoke(row, actor_id, self._now(), data.motivo, 'ADMINISTRATIVA'); db.flush()
        return row

    def revoke_root_dependents(self, db, root_id, *, instituicao_id, actor_id):
        self._gate(db, actor_id, instituicao_id, admin=True, inactive_institution=True)
        root = self._row(db, Root, root_id)
        if root.instituicao_id != instituicao_id:
            raise PermissaoAssistencialErro('INSTITUTION_MISMATCH')
        now = self._now()
        with db.begin_nested():
            for model in (Grant, Authority):
                rows = db.query(model).filter_by(usuario_instituicao_acesso_id=root.id, revogado_em=None).order_by(model.id).populate_existing().all()
                for row in rows:
                    self._revoke(row, actor_id, now, 'Desativação explícita do acesso institucional', 'RAIZ_DESATIVADA')
                db.flush()
