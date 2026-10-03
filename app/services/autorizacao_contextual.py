"""Read-only contextual decisions; no clinical resources, commands or legacy ACL.

actor_id must come from the caller's authenticated Usuario session, never from
an untrusted payload. This service rechecks persisted eligibility, not JWTs.
The returned Select yields context IDs, is composable before pagination and
must be executed for each evaluation. It is not a cached authorization result.
"""
from sqlalchemy import Date, and_, cast, false, func, or_, select
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, ProfissionalInstituicao
from app.models.contexto_assistencial import ContextoAssistencial as Contexto
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Raiz
from app.models.permissao_assistencial import CAPACIDADES, ContextoProfissional as Participacao, ConcessaoAssistencial as Grant


class AutorizacaoContextualService:
    @staticmethod
    def _valid_id(value):
        return type(value) is int and 0 < value <= 2147483647

    @staticmethod
    def _current_period(model, today):
        return and_(model.data_inicio <= today,
                    or_(model.data_fim.is_(None), model.data_fim >= today))

    def authorized_context_query(self, *, actor_id, capability, instituicao_id):
        """Select of authorized context IDs, using database state at execution.

        Unknown/invalid inputs yield an empty set, without disclosing existence.
        Clinical grants are independent. Authority provenance is intentionally
        not an eligibility dependency of an already-issued grant.
        """
        query = select(Contexto.id).execution_options(autoflush=False)
        if (not self._valid_id(actor_id) or not self._valid_id(instituicao_id)
                or not isinstance(capability, str) or capability not in CAPACIDADES):
            return query.where(false())

        # Statement time (UTC), not transaction-start date or a Python cache.
        today = cast(func.timezone('UTC', func.statement_timestamp()), Date)
        context_scope = and_(Grant.escopo_tipo == 'CONTEXTO',
                             Grant.contexto_assistencial_id == Contexto.id)
        scope = context_scope
        if capability == 'CONTEXTO_ADMINISTRAR':
            scope = or_(context_scope, and_(Grant.escopo_tipo == 'INSTITUICAO',
                                           Grant.contexto_assistencial_id.is_(None)))

        entitlement = (select(1).select_from(Usuario)
            .join(Pessoa, Pessoa.id == Usuario.pessoa_id)
            .join(Raiz, Raiz.usuario_id == Usuario.id)
            .join(Instituicao, Instituicao.id == Raiz.instituicao_id)
            .join(Grant, and_(Grant.usuario_instituicao_acesso_id == Raiz.id,
                             Grant.instituicao_id == Raiz.instituicao_id))
            .where(Usuario.id == actor_id, Usuario.ativo.is_(True), Pessoa.ativo.is_(True),
                   Raiz.ativo.is_(True), Instituicao.ativo.is_(True),
                   Raiz.instituicao_id == Contexto.instituicao_id,
                   Grant.capacidade == capability, Grant.revogado_em.is_(None), scope)
            .correlate(Contexto))

        if capability != 'CONTEXTO_ADMINISTRAR':
            participation = (select(1).select_from(Participacao)
                .join(ProfissionalInstituicao, and_(
                    ProfissionalInstituicao.id == Participacao.profissional_instituicao_id,
                    ProfissionalInstituicao.instituicao_id == Participacao.instituicao_id))
                .join(Profissional, Profissional.id == ProfissionalInstituicao.profissional_id)
                .where(Participacao.contexto_assistencial_id == Contexto.id,
                       Participacao.instituicao_id == Contexto.instituicao_id,
                       Participacao.invalidado_em.is_(None), Participacao.encerrado_em.is_(None),
                       self._current_period(Participacao, today),
                       ProfissionalInstituicao.ativo.is_(True),
                       self._current_period(ProfissionalInstituicao, today),
                       Profissional.ativo.is_(True), Profissional.pessoa_id == Usuario.pessoa_id)
                .correlate(Contexto, Usuario))
            entitlement = entitlement.where(participation.exists())

        query = query.where(Contexto.instituicao_id == instituicao_id,
                            Contexto.ativo.is_(True), entitlement.exists())
        if capability == 'ASSISTENCIAL_REGISTRAR':
            # W1A defines a context with data_fim as closed, even if future-dated.
            query = query.where(Contexto.data_fim.is_(None), Contexto.data_inicio <= today)
        # Historical patient membership is deliberately not an eligibility gate.
        return query.order_by(Contexto.id)

    def authorize_resource(self, db, *, actor_id, capability, instituicao_id, contexto_assistencial_id):
        """Boolean decision; all denials (including absent contexts) look alike.

        Uses the exact list predicate in a single SELECT. No commit, autoflush,
        ORM identity-map eligibility, positive cache, or clinical data loading.
        A fresh READ COMMITTED statement sees revocations committed elsewhere;
        a caller-owned snapshot retains its normal database isolation semantics.
        """
        if not self._valid_id(contexto_assistencial_id):
            return False
        query = self.authorized_context_query(actor_id=actor_id, capability=capability,
                                               instituicao_id=instituicao_id)
        statement = select(query.where(Contexto.id == contexto_assistencial_id).exists())
        with db.no_autoflush:
            return bool(db.execute(statement.execution_options(autoflush=False)).scalar_one())
