"""Contextual adapter for canonical PTS tables; no legacy resolver or clinic ACL.
Caller owns commit/rollback. Existing W1B serializer + context lock protect writes.
"""
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
from app.services.permissao_assistencial import PermissaoAssistencialService
from app.services.autorizacao_contextual import AutorizacaoContextualService


from datetime import date
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from app.models.pts import PTS, PTSObjetivo
from app.schemas.pts_mental import PTSMentalOut, PTSMentalJornada
from app.services.diagnostico_mental import DiagnosticoMentalService


class PTSDenied(ValueError):
    pass


class PTSConflict(ValueError):
    pass


class PTSMentalService:
    # Universal active-line W1B scope; no diagnosis writes or clinical inference.
    scope = DiagnosticoMentalService.scope
    authorization = AutorizacaoContextualService()
    _lock = staticmethod(DiagnosticoMentalService._lock)

    def allowed(self, db, *, actor, institution, person, context, capability):
        return db.execute(self.scope(actor,institution,person,context,capability)).scalar_one_or_none()

    def output(self, row, person, institution):
        return PTSMentalOut(**{name:getattr(row,name) for name in PTSMentalOut.model_fields
                             if name not in ('pessoa_id','instituicao_id')},pessoa_id=person,instituicao_id=institution)

    def journey(self, db, *, actor, institution, person, context):
        with db.no_autoflush:
            if self.allowed(db,actor=actor,institution=institution,person=person,context=context,capability='ASSISTENCIAL_LER') is None:
                raise PTSDenied('PTS_UNAVAILABLE')
            rows=db.execute(select(PTS).options(selectinload(PTS.objetivos)).where(
                PTS.contexto_assistencial_id==context,PTS.modulo_id==3).order_by(PTS.data_inicio.desc(),PTS.id.desc())).scalars().all()
            return PTSMentalJornada(pode_registrar=self.allowed(db,actor=actor,institution=institution,person=person,context=context,capability='ASSISTENCIAL_REGISTRAR') is not None,
                itens=[self.output(r,person,institution) for r in rows])

    def locked_context(self, db, *, actor, institution, person, context):
        if db.new or db.dirty or db.deleted:
            raise PTSDenied('CLEAN_TRANSACTION_REQUIRED')
        PermissaoAssistencialService.lock_institution(db, institution)
        with db.no_autoflush:
            actor_person=db.execute(select(Usuario.pessoa_id).where(Usuario.id==actor)).scalar_one_or_none()
            if actor_person is None:raise PTSDenied('PTS_UNAVAILABLE')
            self._lock(db,Pessoa,Pessoa.id.in_(sorted({actor_person,person})))
            accounts=self._lock(db,Usuario,Usuario.id==actor)
            if not accounts or accounts[0].pessoa_id!=actor_person:raise PTSDenied('PTS_UNAVAILABLE')
            self._lock(db,Instituicao,Instituicao.id==institution)
            self._lock(db,Root,Root.instituicao_id==institution)
            # Stabilize Context and Line alongside the institutional W1B serializer.
            c=db.execute(select(Contexto).where(Contexto.id==context,Contexto.instituicao_id==institution).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if c is None:raise PTSDenied('PTS_UNAVAILABLE')
            self._lock(db,Paciente,Paciente.id==c.paciente_id)
            self._lock(db,Linha,(Linha.contexto_assistencial_id==context)&(Linha.modulo_id==3))
            professionals=self._lock(db,Profissional,Profissional.pessoa_id==actor_person)
            if len(professionals)!=1:raise PTSDenied('PTS_UNAVAILABLE')
            professional=professionals[0]
            self._lock(db,ProfissionalInstituicao,(ProfissionalInstituicao.profissional_id==professional.id)&(ProfissionalInstituicao.instituicao_id==institution))
            self._lock(db,ContextoProfissional,ContextoProfissional.contexto_assistencial_id==context)
            self._lock(db,ConcessaoAssistencial,(ConcessaoAssistencial.instituicao_id==institution)&(ConcessaoAssistencial.contexto_assistencial_id==context))
            if self.allowed(db,actor=actor,institution=institution,person=person,context=context,capability='ASSISTENCIAL_REGISTRAR') is None:
                raise PTSDenied('PTS_UNAVAILABLE')
            return c

    def mutate(self, db, payload=None, *, actor, institution, person, context, action, pts_id=None, objective_id=None):
        c=self.locked_context(db,actor=actor,institution=institution,person=person,context=context)
        if action=='create':
            row=PTS(paciente_id=c.paciente_id,contexto_assistencial_id=context,modulo_id=3,
                    criado_por_usuario_id=actor,status='ATIVO',**payload.model_dump())
            db.add(row)
        else:
            row=db.execute(select(PTS).where(PTS.id==pts_id,PTS.contexto_assistencial_id==context,
                PTS.modulo_id==3).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
            if row is None:raise PTSDenied('PTS_UNAVAILABLE')
        if action in ('create','reopen'):
            with db.no_autoflush:
                conflict=db.execute(select(PTS.id).where(PTS.contexto_assistencial_id==context,
                    PTS.modulo_id==3,PTS.status=='ATIVO',PTS.id!=row.id) if row.id else select(PTS.id).where(
                    PTS.contexto_assistencial_id==context,PTS.modulo_id==3,PTS.status=='ATIVO')).first()
            if conflict:raise PTSConflict('ACTIVE_PTS_EXISTS')
        if action in ('close','reopen'):
            row.status='ENCERRADO' if action=='close' else 'ATIVO'
            row.data_fim=date.today() if action=='close' else None
        elif action=='update':
            for field,value in payload.model_dump().items():setattr(row,field,value)
        elif action=='objective_create':
            db.add(PTSObjetivo(pts_id=row.id,**payload.model_dump()))
        elif action=='objective_update':
            objective=db.execute(select(PTSObjetivo).where(PTSObjetivo.id==objective_id,PTSObjetivo.pts_id==row.id).with_for_update()).scalar_one_or_none()
            if objective is None:raise PTSDenied('PTS_UNAVAILABLE')
            for field,value in payload.model_dump(exclude_unset=True).items():
                if value is not None:setattr(objective,field,value)
            objective.updated_at=func.now()
        if action!='create':row.updated_at=func.now()
        db.flush()
        db.expire(row,['objetivos'])
        return self.output(row,person,institution)
