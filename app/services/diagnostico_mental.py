"""Context-first diagnoses. W1B authorization and caller-owned transaction."""
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
from app.models.diagnostico import Diagnostico
from app.services.permissao_assistencial import PermissaoAssistencialService
from app.services.autorizacao_contextual import AutorizacaoContextualService
from app.services.diagnostico_service import DiagnosticoService
from app.schemas.diagnostico import DiagnosticoCreate
from app.schemas.diagnostico_mental import DiagnosticoMentalOut, DiagnosticosJornada


class DiagnosisDenied(ValueError):
    pass


class DiagnosticoMentalService:
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
    def output(row, person):
        data = {name: getattr(row, name) for name in DiagnosticoMentalOut.model_fields if name != 'pessoa_id'}
        data['created_at'] = row.created_at.replace(tzinfo=timezone.utc)
        return DiagnosticoMentalOut(**data, pessoa_id=person)

    def journey(self, db, *, actor, institution, person, context):
        with db.no_autoflush:
            scope = self.scope(actor, institution, person, context, 'ASSISTENCIAL_LER').with_only_columns(Contexto.id)
            rows = db.execute(select(Diagnostico).where(Diagnostico.contexto_assistencial_id.in_(scope),
                Diagnostico.modulo_id == 3).order_by(Diagnostico.created_at.desc(), Diagnostico.id.desc())).scalars().all()
            allowed = db.execute(self.scope(actor,institution,person,context,'ASSISTENCIAL_REGISTRAR')).scalar_one_or_none() is not None
            return DiagnosticosJornada(pode_registrar=allowed, itens=[self.output(r, person) for r in rows])

    @staticmethod
    def _lock(db, model, predicate):
        return db.execute(select(model).where(predicate).order_by(model.id).with_for_update(read=True).execution_options(populate_existing=True)).scalars().all()

    def create(self, db, payload, *, actor, institution, person, context):
        if db.new or db.dirty or db.deleted:
            raise DiagnosisDenied('CLEAN_TRANSACTION_REQUIRED')
        PermissaoAssistencialService.lock_institution(db, institution)
        with db.no_autoflush:
            actor_person=db.execute(select(Usuario.pessoa_id).where(Usuario.id==actor)).scalar_one_or_none()
            if actor_person is None:raise DiagnosisDenied('DIAGNOSIS_UNAVAILABLE')
            self._lock(db,Pessoa,Pessoa.id.in_(sorted({actor_person,person})))
            accounts=self._lock(db,Usuario,Usuario.id==actor)
            if not accounts or accounts[0].pessoa_id!=actor_person:raise DiagnosisDenied('DIAGNOSIS_UNAVAILABLE')
            self._lock(db,Instituicao,Instituicao.id==institution)
            self._lock(db,Root,Root.instituicao_id==institution)
            # Stabilize Context and Line alongside the institutional W1B serializer.
            c=db.execute(select(Contexto).where(Contexto.id==context,Contexto.instituicao_id==institution).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if c is None:raise DiagnosisDenied('DIAGNOSIS_UNAVAILABLE')
            self._lock(db,Paciente,Paciente.id==c.paciente_id)
            self._lock(db,Linha,(Linha.contexto_assistencial_id==context)&(Linha.modulo_id==3))
            professionals=self._lock(db,Profissional,Profissional.pessoa_id==actor_person)
            if len(professionals)!=1:raise DiagnosisDenied('DIAGNOSIS_UNAVAILABLE')
            professional=professionals[0]
            self._lock(db,ProfissionalInstituicao,(ProfissionalInstituicao.profissional_id==professional.id)&(ProfissionalInstituicao.instituicao_id==institution))
            self._lock(db,ContextoProfissional,ContextoProfissional.contexto_assistencial_id==context)
            self._lock(db,ConcessaoAssistencial,(ConcessaoAssistencial.instituicao_id==institution)&(ConcessaoAssistencial.contexto_assistencial_id==context))
            # Fresh predicate after every lock wait: no identity-map eligibility.
            if db.execute(self.scope(actor,institution,person,context,"ASSISTENCIAL_REGISTRAR")).scalar_one_or_none() is None:
                raise DiagnosisDenied('DIAGNOSIS_UNAVAILABLE')

            self._lock(db, ModuloClinico, ModuloClinico.id == 3)
            if db.execute(self.scope(actor,institution,person,context,"ASSISTENCIAL_REGISTRAR")).scalar_one_or_none() is None:
                raise DiagnosisDenied('DIAGNOSIS_UNAVAILABLE')
            canonical = DiagnosticoCreate(**payload.model_dump(), paciente_id=c.paciente_id, care_line='MENTAL_HEALTH')
            row = DiagnosticoService._criar_contextual(db, canonical, contexto_assistencial_id=context, modulo_id=3)
            row.registrador_usuario_id = actor
            row.registrador_profissional_id = professional.id
            db.flush()
            return self.output(row, person)
