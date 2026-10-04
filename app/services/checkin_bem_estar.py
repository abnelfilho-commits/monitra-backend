"""Canonical assisted self-report. Caller owns commit/rollback; no clinical scoring."""
from datetime import timezone
from sqlalchemy import select, func, Date, cast
from app.models.modular import ModuloClinico, FormularioModulo, CampoFormulario, RegistroLongitudinal, RespostaRegistro
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
from app.services.autorizacao_contextual import AutorizacaoContextualService
from app.services.registros_longitudinais import criar_registro_longitudinal
from app.schemas.registros_longitudinais import RegistroLongitudinalCreate, CampoResposta
from app.schemas.checkin_bem_estar import CheckinOut, FormularioCheckin, CampoCheckin, BemEstarJornada
from app.services.checkin_contract import CODE, FIELDS


class CheckinDenied(ValueError):
    pass


class CheckinInvalid(ValueError):
    pass


class CheckinUnavailable(ValueError):
    pass


class CheckinBemEstarService:
    authorization = AutorizacaoContextualService()

    def _scope(self, actor, institution, person, context, capability):
        allowed=self.authorization.authorized_context_query(actor_id=actor, capability=capability, instituicao_id=institution)
        return (select(Contexto).join(Paciente, Paciente.id==Contexto.paciente_id)
                .join(Pessoa,Pessoa.id==Paciente.pessoa_id)
                .where(Contexto.id==context, Contexto.id.in_(allowed), Pessoa.id==person, Pessoa.ativo.is_(True)))

    def _catalog(self, db, lock=False):
        q=select(FormularioModulo).join(ModuloClinico,ModuloClinico.id==FormularioModulo.modulo_id).where(
            FormularioModulo.codigo==CODE,FormularioModulo.modulo_id==3,FormularioModulo.ativo.is_(True),
            FormularioModulo.tipo=='LONGITUDINAL',ModuloClinico.slug=='saude_mental',ModuloClinico.ativo.is_(True))
        if lock:q=q.with_for_update(read=True)
        forms=db.execute(q).scalars().all()
        if len(forms)!=1:raise CheckinUnavailable('CHECKIN_CATALOG_UNAVAILABLE')
        q=select(CampoFormulario).where(CampoFormulario.formulario_id==forms[0].id).order_by(CampoFormulario.ordem,CampoFormulario.id)
        if lock:q=q.with_for_update(read=True)
        fields=db.execute(q.execution_options(populate_existing=True)).scalars().all()
        expected=[(n,l,'radio' if opts else 'textarea',bool(opts),i,[dict(valor=v,label=x) for v,x in opts],True) for i,(n,l,opts) in enumerate(FIELDS,1)]
        actual=[(f.nome_campo,f.label,f.tipo_campo,f.obrigatorio,f.ordem,f.opcoes,f.ativo) for f in fields]
        if actual!=expected:raise CheckinUnavailable('CHECKIN_CATALOG_UNAVAILABLE')
        return forms[0],fields

    def can_write(self, db, *, actor, institution, person, context):
        q=self._scope(actor,institution,person,context,'ASSISTENCIAL_REGISTRAR').join(Linha,Linha.contexto_assistencial_id==Contexto.id).where(Linha.modulo_id==3,Linha.ativo.is_(True))
        return db.execute(q).scalar_one_or_none() is not None

    def read(self, db, *, actor, institution, person, context):
        # Authorization participates in the clinical query itself, before loading answers.
        scope=self._scope(actor,institution,person,context,'ASSISTENCIAL_LER').with_only_columns(Contexto.id)
        q=(select(RegistroLongitudinal,RegistroProveniencia,CampoFormulario.nome_campo,RespostaRegistro.valor_texto)
           .join(RegistroProveniencia,RegistroProveniencia.registro_id==RegistroLongitudinal.id)
           .join(FormularioModulo,FormularioModulo.id==RegistroLongitudinal.formulario_id)
           .join(RespostaRegistro,RespostaRegistro.registro_id==RegistroLongitudinal.id)
           .join(CampoFormulario,CampoFormulario.id==RespostaRegistro.campo_id)
           .where(RegistroLongitudinal.contexto_assistencial_id.in_(scope),RegistroLongitudinal.modulo_id==3,
                  FormularioModulo.codigo==CODE,RegistroProveniencia.respondente_pessoa_id==person)
           .order_by(RegistroLongitudinal.criado_em,RegistroLongitudinal.id,CampoFormulario.ordem))
        items={}
        with db.no_autoflush:
            for r,p,name,value in db.execute(q):
                if r.id not in items:
                    items[r.id]=CheckinOut(id=r.id,data_hora=r.criado_em.replace(tzinfo=timezone.utc),baseline=not items,
                        respondente_pessoa_id=p.respondente_pessoa_id,registrador_profissional_id=p.registrador_profissional_id,
                        canal=p.canal,modalidade=p.modalidade,respostas={})
                items[r.id].respostas[name]=value
        return list(items.values())

    def journey(self, db, **scope):
        with db.no_autoflush:
            allowed=self.can_write(db,**scope)
            form=None
            if allowed:
                try:
                    f,fields=self._catalog(db)
                    form=FormularioCheckin(id=f.id,campos=[CampoCheckin(id=x.id,nome_campo=x.nome_campo,label=x.label,tipo_campo=x.tipo_campo,obrigatorio=x.obrigatorio,opcoes=x.opcoes) for x in fields])
                except CheckinUnavailable:allowed=False
            return BemEstarJornada(pode_registrar=allowed,formulario=form,checkins=self.read(db,**scope))

    @staticmethod
    def _lock(db, model, predicate):
        return db.execute(select(model).where(predicate).order_by(model.id).with_for_update(read=True).execution_options(populate_existing=True)).scalars().all()

    def create(self, db, payload, *, actor, institution, person, context):
        if db.new or db.dirty or db.deleted:raise CheckinInvalid('CLEAN_TRANSACTION_REQUIRED')
        # P0-10: reuse institutional W1B serializer, plus rows for lifecycle paths
        # that do not use that serializer. Identity parents precede their roles.
        PermissaoAssistencialService.lock_institution(db,institution)
        with db.no_autoflush:
            actor_person=db.execute(select(Usuario.pessoa_id).where(Usuario.id==actor)).scalar_one_or_none()
            if actor_person is None:raise CheckinDenied('CHECKIN_UNAVAILABLE')
            self._lock(db,Pessoa,Pessoa.id.in_(sorted({actor_person,person})))
            accounts=self._lock(db,Usuario,Usuario.id==actor)
            if not accounts or accounts[0].pessoa_id!=actor_person:raise CheckinDenied('CHECKIN_UNAVAILABLE')
            self._lock(db,Instituicao,Instituicao.id==institution)
            self._lock(db,Root,Root.instituicao_id==institution)
            # Exclusive context row also serializes concurrent baseline writes.
            c=db.execute(select(Contexto).where(Contexto.id==context,Contexto.instituicao_id==institution).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if c is None:raise CheckinDenied('CHECKIN_UNAVAILABLE')
            self._lock(db,Paciente,Paciente.id==c.paciente_id)
            self._lock(db,Linha,(Linha.contexto_assistencial_id==context)&(Linha.modulo_id==3))
            professionals=self._lock(db,Profissional,Profissional.pessoa_id==actor_person)
            if len(professionals)!=1:raise CheckinDenied('CHECKIN_UNAVAILABLE')
            professional=professionals[0]
            self._lock(db,ProfissionalInstituicao,(ProfissionalInstituicao.profissional_id==professional.id)&(ProfissionalInstituicao.instituicao_id==institution))
            self._lock(db,ContextoProfissional,ContextoProfissional.contexto_assistencial_id==context)
            self._lock(db,ConcessaoAssistencial,(ConcessaoAssistencial.instituicao_id==institution)&(ConcessaoAssistencial.contexto_assistencial_id==context))
            # Fresh predicate after every lock wait: no identity-map eligibility.
            if payload.paciente_id!=c.paciente_id or not self.can_write(db,actor=actor,institution=institution,person=person,context=context):
                raise CheckinDenied('CHECKIN_UNAVAILABLE')
            form,fields=self._catalog(db,lock=True)
            if payload.formulario_id!=form.id or payload.modulo_id!=3:raise CheckinInvalid('INVALID_CHECKIN')
            answers=payload.respostas
            required={n for n,_,opts in FIELDS if opts}
            if not required.issubset(answers) or set(answers)-{n for n,_,_ in FIELDS}:raise CheckinInvalid('INVALID_CHECKIN')
            for name,_,opts in FIELDS:
                if opts and answers[name] not in {v for v,_ in opts}:raise CheckinInvalid('INVALID_CHECKIN')
            description=answers.get('evento_descricao','').strip()
            if len(description)>2000 or (description and answers['evento_relevante']!='SIM'):raise CheckinInvalid('INVALID_CHECKIN')
            now=db.execute(select(func.timezone('UTC',func.clock_timestamp()))).scalar_one()
            canonical=RegistroLongitudinalCreate(paciente_id=c.paciente_id,modulo_id=3,formulario_id=form.id,
                data_registro=now.date(),origem='PROFISSIONAL',respostas=[CampoResposta(campo_id=f.id,valor=description if f.nome_campo=='evento_descricao' else answers[f.nome_campo]) for f in fields if f.nome_campo!='evento_descricao' or description])
        record=criar_registro_longitudinal(db,canonical,commit=False,contexto_assistencial_id=context,criado_por_usuario_id=actor)
        record.criado_em=now
        db.add(RegistroProveniencia(registro_id=record.id,respondente_pessoa_id=person,
            registrador_pessoa_id=actor_person,registrador_profissional_id=professional.id,canal='PORTAL_PROFISSIONAL',modalidade='ASSISTIDO'))
        db.flush()
        # Write and read capabilities are independent: return only this command's result.
        first=db.execute(select(RegistroLongitudinal.id).where(RegistroLongitudinal.contexto_assistencial_id==context,RegistroLongitudinal.modulo_id==3,RegistroLongitudinal.formulario_id==form.id).order_by(RegistroLongitudinal.criado_em,RegistroLongitudinal.id).limit(1)).scalar_one()
        return CheckinOut(id=record.id,data_hora=now.replace(tzinfo=timezone.utc),baseline=first==record.id,
            respondente_pessoa_id=person,registrador_profissional_id=professional.id,canal='PORTAL_PROFISSIONAL',modalidade='ASSISTIDO',
            respostas={r.nome_campo:description if r.nome_campo=='evento_descricao' else answers[r.nome_campo] for r in fields if r.nome_campo!='evento_descricao' or description})
