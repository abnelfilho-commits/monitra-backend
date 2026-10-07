"""Authorized GAD-7 orchestration over the universal assessment framework."""
from datetime import timezone
from sqlalchemy import select, func
from app.models.modular import ModuloClinico, FormularioModulo, CampoFormulario, RegistroLongitudinal
from app.models.registro_proveniencia import RegistroProveniencia
from app.models.contexto_assistencial import ContextoAssistencial as Contexto, ContextoAssistencialLinha as Linha
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.paciente import Paciente
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, ProfissionalInstituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.permissao_assistencial import ContextoProfissional, ConcessaoAssistencial
from app.services.permissao_assistencial import PermissaoAssistencialService
from app.services.registros_longitudinais import persistir_registro_longitudinal
from app.schemas.registros_longitudinais import RegistroLongitudinalCreate, CampoResposta
from app.schemas.checkin_bem_estar import FormularioCheckin, CampoCheckin
from app.schemas.gad7 import GAD7Out, GAD7Jornada
from app.models.avaliacao_clinica import AvaliacaoClinica
from app.services.clinical_engine.context import AssessmentContext
from app.services.clinical_engine.assessment_service import executar_avaliacao_clinica
from app.services.clinical_engine.assessment_repository import AssessmentRepository
from app.services.gad7_contract import CODE, FIELDS, INSTRUCTION


class GAD7Denied(ValueError):
    pass


class GAD7Invalid(ValueError):
    pass


class GAD7Unavailable(ValueError):
    pass


from app.services.phq9 import PHQ9Service


class GAD7Service(PHQ9Service):
    def _catalog(self, db, lock=False):
        q=select(FormularioModulo).join(ModuloClinico,ModuloClinico.id==FormularioModulo.modulo_id).where(
            FormularioModulo.codigo==CODE,FormularioModulo.modulo_id==3,FormularioModulo.ativo.is_(True),
            FormularioModulo.tipo=='ASSESSMENT',ModuloClinico.slug=='saude_mental',ModuloClinico.ativo.is_(True))
        if lock:q=q.with_for_update(read=True)
        forms=db.execute(q).scalars().all()
        if len(forms)!=1:raise GAD7Unavailable('GAD7_CATALOG_UNAVAILABLE')
        q=select(CampoFormulario).where(CampoFormulario.formulario_id==forms[0].id).order_by(CampoFormulario.ordem,CampoFormulario.id)
        if lock:q=q.with_for_update(read=True)
        fields=db.execute(q.execution_options(populate_existing=True)).scalars().all()
        expected=[(n,l,'radio' if opts else 'textarea',bool(opts),i,[dict(valor=v,label=x) for v,x in opts],True) for i,(n,l,opts) in enumerate(FIELDS,1)]
        actual=[(f.nome_campo,f.label,f.tipo_campo,f.obrigatorio,f.ordem,f.opcoes,f.ativo) for f in fields]
        if actual!=expected:raise GAD7Unavailable('GAD7_CATALOG_UNAVAILABLE')
        return forms[0],fields

    def read(self, db, *, actor, institution, person, context):
        # Authorization participates in the clinical query itself, before loading answers.
        scope=self._scope(actor,institution,person,context,'ASSISTENCIAL_LER').with_only_columns(Contexto.id)
        q=(select(AvaliacaoClinica, RegistroLongitudinal, RegistroProveniencia)
           .join(RegistroLongitudinal, RegistroLongitudinal.id==AvaliacaoClinica.registro_id)
           .join(RegistroProveniencia, RegistroProveniencia.registro_id==RegistroLongitudinal.id)
           .where(RegistroLongitudinal.contexto_assistencial_id.in_(scope), RegistroLongitudinal.modulo_id==3,
                  AvaliacaoClinica.instrumento=='GAD7', AvaliacaoClinica.modulo_id==3,
                  AvaliacaoClinica.paciente_id==RegistroLongitudinal.paciente_id, RegistroProveniencia.respondente_pessoa_id==person)
           .order_by(RegistroLongitudinal.criado_em.desc(), AvaliacaoClinica.id.desc()))
        return [GAD7Out(id=a.id,registro_id=r.id,data_hora=r.criado_em.replace(tzinfo=timezone.utc),
                       registrador_usuario_id=r.criado_por_usuario_id,registrador_profissional_id=p.registrador_profissional_id,
                       resultado=a.resultado) for a,r,p in db.execute(q)]

    def journey(self, db, **scope):
        with db.no_autoflush:
            allowed=self.can_write(db,**scope)
            form=None
            if allowed:
                try:
                    f,fields=self._catalog(db)
                    form=FormularioCheckin(id=f.id,campos=[CampoCheckin(id=x.id,nome_campo=x.nome_campo,label=x.label,tipo_campo=x.tipo_campo,obrigatorio=x.obrigatorio,opcoes=x.opcoes) for x in fields])
                except GAD7Unavailable:allowed=False
            return GAD7Jornada(pode_registrar=allowed,formulario=form,instrucoes=INSTRUCTION,itens=self.read(db,**scope))

    def create(self, db, payload, *, actor, institution, person, context):
        if db.new or db.dirty or db.deleted:raise GAD7Invalid('CLEAN_TRANSACTION_REQUIRED')
        # P0-10: reuse institutional W1B serializer, plus rows for lifecycle paths
        # that do not use that serializer. Identity parents precede their roles.
        PermissaoAssistencialService.lock_institution(db,institution)
        with db.no_autoflush:
            actor_person=db.execute(select(Usuario.pessoa_id).where(Usuario.id==actor)).scalar_one_or_none()
            if actor_person is None:raise GAD7Denied('GAD7_UNAVAILABLE')
            self._lock(db,Pessoa,Pessoa.id.in_(sorted({actor_person,person})))
            accounts=self._lock(db,Usuario,Usuario.id==actor)
            if not accounts or accounts[0].pessoa_id!=actor_person:raise GAD7Denied('GAD7_UNAVAILABLE')
            self._lock(db,Instituicao,Instituicao.id==institution)
            self._lock(db,Root,Root.instituicao_id==institution)
            # Exclusive context row stabilizes the clinical context during assessment creation.
            c=db.execute(select(Contexto).where(Contexto.id==context,Contexto.instituicao_id==institution).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if c is None:raise GAD7Denied('GAD7_UNAVAILABLE')
            self._lock(db,Paciente,Paciente.id==c.paciente_id)
            self._lock(db,Linha,(Linha.contexto_assistencial_id==context)&(Linha.modulo_id==3))
            professionals=self._lock(db,Profissional,Profissional.pessoa_id==actor_person)
            if len(professionals)!=1:raise GAD7Denied('GAD7_UNAVAILABLE')
            professional=professionals[0]
            self._lock(db,ProfissionalInstituicao,(ProfissionalInstituicao.profissional_id==professional.id)&(ProfissionalInstituicao.instituicao_id==institution))
            self._lock(db,ContextoProfissional,ContextoProfissional.contexto_assistencial_id==context)
            self._lock(db,ConcessaoAssistencial,(ConcessaoAssistencial.instituicao_id==institution)&(ConcessaoAssistencial.contexto_assistencial_id==context))
            # Fresh predicate after every lock wait: no identity-map eligibility.
            if not self.can_write(db,actor=actor,institution=institution,person=person,context=context):
                raise GAD7Denied('GAD7_UNAVAILABLE')
            form,fields=self._catalog(db,lock=True)
            answers=payload.respostas
            now=db.execute(select(func.timezone('UTC',func.clock_timestamp()))).scalar_one()
            canonical=RegistroLongitudinalCreate(paciente_id=c.paciente_id,modulo_id=3,formulario_id=form.id,
                data_registro=now.date(),origem='PROFISSIONAL',respostas=[CampoResposta(campo_id=f.id,valor=answers[f.nome_campo]) for f in fields])
        record=persistir_registro_longitudinal(db,canonical,contexto_assistencial_id=context,criado_por_usuario_id=actor)
        record.criado_em=now
        db.add(RegistroProveniencia(registro_id=record.id,respondente_pessoa_id=person,
            registrador_pessoa_id=actor_person,registrador_profissional_id=professional.id,canal='PORTAL_PROFISSIONAL',modalidade='ASSISTIDO'))
        db.flush()
        assessment_context=AssessmentContext(registro_id=record.id,instrumento='GAD7',respostas=dict(answers),
            paciente_id=c.paciente_id,modulo_id=3,profissional_id=actor,formulario_id=form.id,
            data_registro=str(now.date()),metadata={'contexto_assistencial_id':context})
        result=executar_avaliacao_clinica(assessment_context)
        assessment=AssessmentRepository.salvar_avaliacao(db,assessment_context,result,commit=False)
        return GAD7Out(id=assessment.id,registro_id=record.id,data_hora=now.replace(tzinfo=timezone.utc),
            registrador_usuario_id=actor,registrador_profissional_id=professional.id,resultado=result)
