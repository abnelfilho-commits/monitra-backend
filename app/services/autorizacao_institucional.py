"""Canonical authorization foundation. No consumer migration; caller owns commit."""
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models.usuario import Usuario
from app.models.institucional import Instituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Acesso
from app.schemas.autorizacao_institucional import AcessoCreate, PerfilChange, AutorizacaoConfirmada


class AutorizacaoInstitucionalErro(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class AutorizacaoInstitucionalService:
    @staticmethod
    def _usuario(db, identity):
        # Column query always observes the database, not cached ORM attributes.
        row = db.query(Usuario.id, Usuario.ativo, Usuario.perfil).filter(Usuario.id == identity).first()
        if row is None:
            raise AutorizacaoInstitucionalErro('USER_NOT_FOUND')
        return row

    def _context(self, db, usuario_id, instituicao_id, *, require_active=True):
        if type(instituicao_id) is not int or instituicao_id <= 0:
            raise AutorizacaoInstitucionalErro('EXPLICIT_INSTITUTION_REQUIRED')
        user = self._usuario(db, usuario_id)
        institution = db.query(Instituicao.id, Instituicao.ativo).filter(Instituicao.id == instituicao_id).first()
        if institution is None:
            raise AutorizacaoInstitucionalErro('INSTITUTION_NOT_FOUND')
        if require_active and not user.ativo:
            raise AutorizacaoInstitucionalErro('USER_INACTIVE')
        if require_active and not institution.ativo:
            raise AutorizacaoInstitucionalErro('INSTITUTION_INACTIVE')
        return user

    def _write_gate(self, db, actor_id):
        if db.new or db.dirty or db.deleted:
            raise AutorizacaoInstitucionalErro('CLEAN_SESSION_REQUIRED')
        if db.execute(text('SHOW transaction_isolation')).scalar() != 'read committed':
            raise AutorizacaoInstitucionalErro('READ_COMMITTED_REQUIRED')
        actor = self._usuario(db, actor_id)
        if not actor.ativo or actor.perfil != 'ADMIN':
            raise AutorizacaoInstitucionalErro('ADMIN_REQUIRED')

    @staticmethod
    def _row(db, usuario_id, instituicao_id):
        return db.query(Acesso).filter_by(usuario_id=usuario_id, instituicao_id=instituicao_id).populate_existing().with_for_update().first()

    @staticmethod
    def _same(row, data):
        if row.perfil_institucional != data.perfil_institucional or row.ativo != data.ativo:
            raise AutorizacaoInstitucionalErro('ACCESS_CONFLICT')
        return row

    def create(self, db, payload, *, actor_id):
        data = AcessoCreate.model_validate(payload)
        self._write_gate(db, actor_id)
        self._context(db, data.usuario_id, data.instituicao_id)
        row = self._row(db, data.usuario_id, data.instituicao_id)
        if row is not None:
            return self._same(row, data)
        try:
            with db.begin_nested():
                row = Acesso(**data.model_dump())
                db.add(row)
                db.flush()
                return row
        except IntegrityError as exc:
            # Only this precise UNIQUE violation permits a concurrent reread.
            if (getattr(exc.orig, 'pgcode', None) != '23505' or
                getattr(getattr(exc.orig, 'diag', None), 'constraint_name', None) != 'uq_usuario_instituicao_acesso'):
                raise
            row = self._row(db, data.usuario_id, data.instituicao_id)
            if row is None:
                raise AutorizacaoInstitucionalErro('CONCURRENT_ACCESS_CONFLICT') from exc
            return self._same(row, data)

    def _mutate(self, db, usuario_id, instituicao_id, actor_id, *, active=None, profile=None):
        self._write_gate(db, actor_id)
        # Revocation remains possible even if the account/institution was disabled.
        self._context(db, usuario_id, instituicao_id, require_active=active is not False)
        with db.begin_nested():
            row = self._row(db, usuario_id, instituicao_id)
            if row is None:
                raise AutorizacaoInstitucionalErro('ACCESS_NOT_FOUND')
            if active is not None:
                row.ativo = active
            if profile is not None:
                row.perfil_institucional = profile
            db.flush()
            return row

    def activate(self, db, usuario_id, instituicao_id, *, actor_id):
        return self._mutate(db, usuario_id, instituicao_id, actor_id, active=True)

    def deactivate(self, db, usuario_id, instituicao_id, *, actor_id):
        return self._mutate(db, usuario_id, instituicao_id, actor_id, active=False)

    def change_profile(self, db, usuario_id, instituicao_id, payload, *, actor_id):
        profile = PerfilChange.model_validate(payload).perfil_institucional
        return self._mutate(db, usuario_id, instituicao_id, actor_id, profile=profile)

    def authorize(self, db, usuario_id, instituicao_id):
        user = self._context(db, usuario_id, instituicao_id)
        if user.perfil == 'ADMIN':
            return AutorizacaoConfirmada(usuario_id=user.id, instituicao_id=instituicao_id, admin_global=True)
        row = db.query(Acesso.perfil_institucional).filter_by(usuario_id=usuario_id, instituicao_id=instituicao_id, ativo=True).first()
        if row is None:
            raise AutorizacaoInstitucionalErro('INSTITUTIONAL_ACCESS_DENIED')
        return AutorizacaoConfirmada(usuario_id=user.id, instituicao_id=instituicao_id,
                                    admin_global=False, perfil_institucional=row.perfil_institucional)

    def get(self, db, usuario_id, instituicao_id, *, actor_id):
        actor = self._usuario(db, actor_id)
        if not actor.ativo or actor.perfil != 'ADMIN':
            raise AutorizacaoInstitucionalErro('ADMIN_REQUIRED')
        self._context(db, usuario_id, instituicao_id, require_active=False)
        row = db.query(Acesso).filter_by(usuario_id=usuario_id, instituicao_id=instituicao_id).populate_existing().first()
        if row is None:
            raise AutorizacaoInstitucionalErro('ACCESS_NOT_FOUND')
        return row

    def list(self, db, *, instituicao_id, actor_id):
        actor = self._usuario(db, actor_id)
        if not actor.ativo or actor.perfil != 'ADMIN':
            raise AutorizacaoInstitucionalErro('ADMIN_REQUIRED')
        self._context(db, actor_id, instituicao_id, require_active=False)
        return db.query(Acesso).filter_by(instituicao_id=instituicao_id).order_by(Acesso.id).populate_existing().all()
