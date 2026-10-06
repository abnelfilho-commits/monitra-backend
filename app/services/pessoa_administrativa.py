"""Read-only projections by explicit pessoa_id, including inactive history.

No matching by name/contact, no clinical reads, no entitlement inference.
"""
from sqlalchemy import func
from app.models.pessoa import Pessoa
from app.models.usuario import Usuario
from app.models.paciente import Paciente
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, PacienteInstituicao, ProfissionalInstituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso
from app.services.autorizacao_institucional import AutorizacaoInstitucionalService, AutorizacaoInstitucionalErro


class PessoaAdministrativaErro(ValueError):
    pass


class PessoaAdministrativaService:
    @staticmethod
    def _guard(db, person_id, actor_id):
        actor = AutorizacaoInstitucionalService._usuario(db, actor_id)
        if not actor.ativo or actor.perfil != 'ADMIN':
            raise AutorizacaoInstitucionalErro('ADMIN_REQUIRED')
        if db.query(Pessoa.id).filter(Pessoa.id == person_id).one_or_none() is None:
            raise PessoaAdministrativaErro('PERSON_NOT_FOUND')

    @staticmethod
    def _institution_columns():
        return (func.coalesce(Instituicao.nome_fantasia, Instituicao.razao_social).label('instituicao_nome'),
                Instituicao.ativo.label('instituicao_ativa'))

    def acessos(self, db, person_id, *, actor_id):
        with db.no_autoflush:
            self._guard(db, person_id, actor_id)
            user = db.query(Usuario.id, Usuario.email, Usuario.ativo).filter(Usuario.pessoa_id == person_id).one_or_none()
            rows = []
            if user is not None:
                access = UsuarioInstituicaoAcesso
                rows = db.query(access.id, access.usuario_id, access.instituicao_id,
                    access.perfil_institucional, access.ativo, *self._institution_columns()).join(
                    Instituicao, Instituicao.id == access.instituicao_id).filter(
                    access.usuario_id == user.id).order_by(access.instituicao_id, access.id).all()
            return dict(pessoa_id=person_id, usuario=dict(user._mapping) if user else None,
                        autorizacoes=[dict(row._mapping) for row in rows])

    def vinculos(self, db, person_id, *, actor_id):
        with db.no_autoflush:
            self._guard(db, person_id, actor_id)
            result = dict(pessoa_id=person_id)
            for role, link, key, output, extra in (
                (Paciente, PacienteInstituicao, 'paciente_id', 'pacientes', PacienteInstituicao.tipo_vinculo),
                (Profissional, ProfissionalInstituicao, 'profissional_id', 'profissionais', ProfissionalInstituicao.ocupacao_id),
            ):
                record = db.query(role.id, role.ativo).filter(role.pessoa_id == person_id).one_or_none()
                identity = record.id if record is not None else None
                result[key] = identity
                if role is Profissional:
                    result['profissional_ativo'] = record.ativo if record is not None else None
                rows = []
                if identity is not None:
                    rows = db.query(link.id, getattr(link, key), link.instituicao_id, extra,
                        link.data_inicio, link.data_fim, link.ativo, *self._institution_columns()).join(
                        Instituicao, Instituicao.id == link.instituicao_id).filter(
                        getattr(link, key) == identity).order_by(link.instituicao_id, link.data_inicio, link.id).all()
                result[output] = [dict(row._mapping) for row in rows]
            return result
