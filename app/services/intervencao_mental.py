"""Context-first interventions. W1B authorization and caller-owned transaction."""
from datetime import timezone
from sqlalchemy import select
from app.models.contexto_assistencial import ContextoAssistencial as Contexto, ContextoAssistencialLinha as Linha
from app.models.modular import ModuloClinico
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.paciente import Paciente
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, ProfissionalInstituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.permissao_assistencial import ContextoProfissional, ConcessaoAssistencial
from app.models.intervencao import Intervencao
from app.services.permissao_assistencial import PermissaoAssistencialService
from app.services.autorizacao_contextual import AutorizacaoContextualService
from app.schemas.intervencao_mental import IntervencaoMentalOut, IntervencoesJornada


class InterventionDenied(ValueError):
    pass


class IntervencaoMentalService:
    authorization = AutorizacaoContextualService()

    def scope(self, actor, institution, person, context, capability):
        allowed = self.authorization.authorized_context_query(actor_id=actor, capability=capability, instituicao_id=institution)
        return (select(Contexto).join(Paciente, Paciente.id == Contexto.paciente_id)
                .join(Pessoa, Pessoa.id == Paciente.pessoa_id)
                .join(Linha, Linha.contexto_assistencial_id == Contexto.id)
                .join(ModuloClinico, ModuloClinico.id == Linha.modulo_id)
                .where(Contexto.id == context, Contexto.id.in_(allowed), Pessoa.id == person,
                       Pessoa.ativo.is_(True), Linha.modulo_id == 3, Linha.ativo.is_(True),
                       ModuloClinico.slug == 'saude_mental', ModuloClinico.ativo.is_(True)))

    @staticmethod
    def output(row, person, author_name=None):
        return IntervencaoMentalOut(
            id=row.id, pessoa_id=person, contexto_assistencial_id=row.contexto_assistencial_id,
            modulo_id=row.modulo_id, tipo=row.tipo, descricao=row.descricao,
            # Contextual writes normalize to UTC in the historical timestamp column.
            data_intervencao=row.data_intervencao.replace(tzinfo=timezone.utc),
            created_at=row.created_at, registrador_usuario_id=row.profissional_id,
            registrador_profissional_id=row.registrador_profissional_id, registrador_nome=author_name)

    def journey(self, db, *, actor, institution, person, context):
        with db.no_autoflush:
            scope = self.scope(actor, institution, person, context, 'ASSISTENCIAL_LER').with_only_columns(Contexto.id)
            rows = db.execute(select(Intervencao).where(Intervencao.contexto_assistencial_id.in_(scope),
                Intervencao.modulo_id == 3).order_by(Intervencao.created_at.desc(), Intervencao.id.desc())).scalars().all()
            allowed = db.execute(self.scope(actor,institution,person,context,'ASSISTENCIAL_REGISTRAR')).scalar_one_or_none() is not None
            author_ids = {r.registrador_profissional_id for r in rows if r.registrador_profissional_id is not None}
            authors = dict(db.execute(select(Profissional.id, Pessoa.nome_completo).join(Pessoa, Pessoa.id == Profissional.pessoa_id)
                                     .where(Profissional.id.in_(author_ids))).all()) if author_ids else {}
            return IntervencoesJornada(pode_registrar=allowed, total=len(rows),
                itens=[self.output(r, person, authors.get(r.registrador_profissional_id)) for r in rows])

    @staticmethod
    def _lock(db, model, predicate):
        return db.execute(select(model).where(predicate).order_by(model.id).with_for_update(read=True).execution_options(populate_existing=True)).scalars().all()

    def create(self, db, payload, *, actor, institution, person, context):
        if db.new or db.dirty or db.deleted:
            raise InterventionDenied('CLEAN_TRANSACTION_REQUIRED')
        PermissaoAssistencialService.lock_institution(db, institution)
        with db.no_autoflush:
            actor_person=db.execute(select(Usuario.pessoa_id).where(Usuario.id==actor)).scalar_one_or_none()
            if actor_person is None:raise InterventionDenied('INTERVENTION_UNAVAILABLE')
            self._lock(db,Pessoa,Pessoa.id.in_(sorted({actor_person,person})))
            accounts=self._lock(db,Usuario,Usuario.id==actor)
            if not accounts or accounts[0].pessoa_id!=actor_person:raise InterventionDenied('INTERVENTION_UNAVAILABLE')
            self._lock(db,Instituicao,Instituicao.id==institution)
            self._lock(db,Root,Root.instituicao_id==institution)
            # Stabilize Context and Line alongside the institutional W1B serializer.
            c=db.execute(select(Contexto).where(Contexto.id==context,Contexto.instituicao_id==institution).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if c is None:raise InterventionDenied('INTERVENTION_UNAVAILABLE')
            self._lock(db,Paciente,Paciente.id==c.paciente_id)
            self._lock(db,Linha,(Linha.contexto_assistencial_id==context)&(Linha.modulo_id==3))
            professionals=self._lock(db,Profissional,Profissional.pessoa_id==actor_person)
            if len(professionals)!=1:raise InterventionDenied('INTERVENTION_UNAVAILABLE')
            professional=professionals[0]
            self._lock(db,ProfissionalInstituicao,(ProfissionalInstituicao.profissional_id==professional.id)&(ProfissionalInstituicao.instituicao_id==institution))
            self._lock(db,ContextoProfissional,ContextoProfissional.contexto_assistencial_id==context)
            self._lock(db,ConcessaoAssistencial,(ConcessaoAssistencial.instituicao_id==institution)&(ConcessaoAssistencial.contexto_assistencial_id==context))
            # Fresh predicate after every lock wait: no identity-map eligibility.
            if db.execute(self.scope(actor,institution,person,context,"ASSISTENCIAL_REGISTRAR")).scalar_one_or_none() is None:
                raise InterventionDenied('INTERVENTION_UNAVAILABLE')

            self._lock(db, ModuloClinico, ModuloClinico.id == 3)
            if db.execute(self.scope(actor,institution,person,context,"ASSISTENCIAL_REGISTRAR")).scalar_one_or_none() is None:
                raise InterventionDenied('INTERVENTION_UNAVAILABLE')
            row = Intervencao(contexto_assistencial_id=context, paciente_id=c.paciente_id, modulo_id=3,
                profissional_id=actor, registrador_profissional_id=professional.id,
                tipo=payload.tipo, descricao=payload.descricao,
                data_intervencao=payload.data_intervencao.astimezone(timezone.utc).replace(tzinfo=None))
            db.add(row)
            db.flush()
            name = db.execute(select(Pessoa.nome_completo).where(Pessoa.id == actor_person)).scalar_one()
            return self.output(row, person, name)
