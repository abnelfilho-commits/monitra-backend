"""Read composition only. Contextual authorization is owned exclusively by W1B."""
from sqlalchemy import Date, and_, cast, func, select
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.paciente import Paciente
from app.models.institucional import Instituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.contexto_assistencial import ContextoAssistencial as Contexto, ContextoAssistencialLinha as Linha
from app.models.modular import ModuloClinico
from app.services.autorizacao_contextual import AutorizacaoContextualService
from app.services.care_lines.registry import MENTAL_HEALTH
from app.schemas.saude_mental import JornadaMental, PessoasMentais, InstituicaoDisponivel


class MentalHealthUnavailable(ValueError):
    pass


class SaudeMentalService:
    def __init__(self):
        self.authorization = AutorizacaoContextualService()

    def institutions(self, db, *, actor_id):
        # Selection metadata only. A root never authorizes people or a journey.
        q = (select(Instituicao.id, Instituicao.nome_fantasia, Instituicao.razao_social)
             .join(Root, Root.instituicao_id == Instituicao.id)
             .join(Usuario, Usuario.id == Root.usuario_id)
             .where(Usuario.id == actor_id, Usuario.ativo.is_(True), Root.ativo.is_(True),
                    Instituicao.ativo.is_(True)).order_by(Instituicao.razao_social, Instituicao.id))
        with db.no_autoflush:
            return [InstituicaoDisponivel(id=r.id, nome=r.nome_fantasia or r.razao_social)
                    for r in db.execute(q)]

    def _query(self, *, actor_id, institution):
        authorized = self.authorization.authorized_context_query(
            actor_id=actor_id, capability='ASSISTENCIAL_LER', instituicao_id=institution)
        today = cast(func.timezone('UTC', func.statement_timestamp()), Date)
        return (select(Pessoa.id.label('pessoa_id'), Pessoa.nome_completo, Pessoa.nome_social,
                       Contexto.paciente_id, Contexto.instituicao_id,
                       func.coalesce(Instituicao.nome_fantasia, Instituicao.razao_social).label('instituicao_nome'),
                       Contexto.paciente_instituicao_id, Contexto.id.label('contexto_assistencial_id'),
                       Contexto.data_inicio, Contexto.data_fim,
                       Linha.id.label('line_id'), Linha.ativo.label('line_active'), today.label('today'))
                .select_from(Contexto).join(Paciente, Paciente.id == Contexto.paciente_id)
                .join(Pessoa, Pessoa.id == Paciente.pessoa_id)
                .join(Instituicao, Instituicao.id == Contexto.instituicao_id)
                .outerjoin(Linha, and_(Linha.contexto_assistencial_id == Contexto.id,
                                      Linha.modulo_id == MENTAL_HEALTH.module_id))
                .where(Contexto.id.in_(authorized))
                .order_by(Pessoa.nome_completo, Pessoa.id, Contexto.data_inicio.desc(), Contexto.id))

    @staticmethod
    def _catalog(db):
        available = db.execute(select(ModuloClinico.id).where(
            ModuloClinico.id == MENTAL_HEALTH.module_id,
            ModuloClinico.slug == MENTAL_HEALTH.slug, ModuloClinico.ativo.is_(True))).scalar_one_or_none()
        if available is None:
            raise MentalHealthUnavailable('MENTAL_HEALTH_UNAVAILABLE')

    @staticmethod
    def _result(row):
        data = dict(row)
        today = data.pop('today')
        line_id, line_active = data.pop('line_id'), data.pop('line_active')
        return JornadaMental(**data, modulo_id=MENTAL_HEALTH.module_id,
            contexto_estado=('ENCERRADO' if data['data_fim'] is not None else
                             'PROGRAMADO' if data['data_inicio'] > today else 'ABERTO'),
            linha_estado='AUSENTE' if line_id is None else 'ATIVA' if line_active else 'INATIVA')

    def people(self, db, *, actor_id, institution, offset=0):
        with db.no_autoflush:
            self._catalog(db)
            rows = db.execute(self._query(actor_id=actor_id, institution=institution)
                              .offset(offset).limit(51)).mappings().all()
            return PessoasMentais(itens=[self._result(r) for r in rows[:50]], tem_mais=len(rows)>50)

    def journey(self, db, *, actor_id, institution, person, context):
        with db.no_autoflush:
            self._catalog(db)
            row = db.execute(self._query(actor_id=actor_id, institution=institution)
                             .where(Pessoa.id == person, Contexto.id == context)).mappings().one_or_none()
            # Not found and denied are indistinguishable. No prior resource load.
            return self._result(row) if row else None
