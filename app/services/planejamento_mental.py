"""Contextual quantitative planning in canonical AgendaCuidado; no sessions or clinic ACL."""
from app.services.atividade_aplicabilidade import applicable_to
from datetime import date
from sqlalchemy import select, or_
from app.models.agenda_cuidado import AgendaCuidado
from app.models.pts import PTS, PTSObjetivo
from app.models.atividade_terapeutica import AtividadeTerapeutica as Activity, OcupacaoProfissional as Occupation, AtividadeOcupacao as Pair
from app.models.profissional import Profissional
from app.models.pessoa import Pessoa
from app.models.institucional import ProfissionalInstituicao as Link
from app.models.sessao_assistencial import SessaoAssistencial
from app.services.pts_mental import PTSMentalService, PTSDenied, PTSConflict
from app.services.planning_occurrences import planned_quantity
from app.schemas.planejamento_mental import PlanningOut


class PlanningInvalid(ValueError):
    pass


class PlanningService:
    pts = PTSMentalService()

    def authorize(self, db, scope, write=False):
        if write:
            return self.pts.locked_context(db,**scope)
        if self.pts.allowed(db,**scope,capability='ASSISTENCIAL_LER') is None:
            raise PTSDenied('PLANNING_UNAVAILABLE')

    def ancestry(self, db, scope, pts_id, objective_id, write=False):
        self.authorize(db,scope,write)
        plan=db.scalar(select(PTS).where(PTS.id==pts_id,PTS.contexto_assistencial_id==scope['context'],PTS.modulo_id==3))
        objective=db.scalar(select(PTSObjetivo.id).where(PTSObjetivo.id==objective_id,PTSObjetivo.pts_id==pts_id))
        if plan is None or objective is None:
            raise PTSDenied('PLANNING_UNAVAILABLE')
        return plan

    def quantity(self, db, scope, payload):
        self.authorize(db,scope)
        try:return planned_quantity(payload.data_inicio,payload.data_fim,payload.frequencia_semanal,payload.duracao_minutos,payload.quantidade_sessoes)
        except ValueError as exc:raise PlanningInvalid(str(exc)) from None

    def candidates(self, db, institution):
        today=date.today()
        return db.execute(select(Link,Profissional).join(Profissional,Profissional.id==Link.profissional_id)
            .join(Pessoa,Pessoa.id==Profissional.pessoa_id).where(Link.instituicao_id==institution,
                Link.ativo.is_(True),Link.data_inicio<=today,or_(Link.data_fim.is_(None),Link.data_fim>=today),
                Profissional.ativo.is_(True),Pessoa.ativo.is_(True)).order_by(Link.id)).all()

    def catalog(self, db, scope):
        self.authorize(db,scope)
        activities=db.scalars(select(Activity).where(applicable_to(3),Activity.ativo.is_(True)).order_by(Activity.nome,Activity.id)).all()
        occupations=db.scalars(select(Occupation).where(Occupation.ativo.is_(True)).order_by(Occupation.nome,Occupation.id)).all()
        pairs=db.execute(select(Pair.atividade_id,Pair.ocupacao_id).where(Pair.atividade_id.in_([a.id for a in activities]))).all()
        return dict(atividades=[dict(id=a.id,nome=a.nome) for a in activities],
            ocupacoes=[dict(id=o.id,nome=o.nome) for o in occupations],
            associacoes=[dict(atividade_id=a,ocupacao_id=o) for a,o in pairs],
            executores=[dict(profissional_id=p.id,nome=p.nome,ocupacao_id=l.ocupacao_id,data_inicio=l.data_inicio,data_fim=l.data_fim) for l,p in self.candidates(db,scope['institution'])])

    def outputs(self, db, conditions):
        rows=db.execute(select(AgendaCuidado,Activity.nome,Occupation.nome,Profissional.nome)
            .join(Activity,Activity.id==AgendaCuidado.atividade_id).join(Occupation,Occupation.id==AgendaCuidado.ocupacao_id)
            .join(Profissional,Profissional.id==AgendaCuidado.profissional_id).where(*conditions).order_by(AgendaCuidado.id)).all()
        return [PlanningOut(**{f:getattr(a,f) for f in PlanningOut.model_fields if f not in ('atividade_nome','ocupacao_nome','profissional_nome')},
                            atividade_nome=an,ocupacao_nome=on,profissional_nome=pn) for a,an,on,pn in rows]

    def list(self, db, scope, pts_id, objective_id):
        self.ancestry(db,scope,pts_id,objective_id)
        return self.outputs(db,[AgendaCuidado.pts_id==pts_id,AgendaCuidado.objetivo_id==objective_id])

    def save(self, db, scope, pts_id, objective_id, payload, planning_id=None):
        self.ancestry(db,scope,pts_id,objective_id,True)
        row=None
        if planning_id is not None:
            row=db.scalar(select(AgendaCuidado).where(AgendaCuidado.id==planning_id,AgendaCuidado.pts_id==pts_id,
                AgendaCuidado.objetivo_id==objective_id).with_for_update())
            if row is None:raise PTSDenied('PLANNING_UNAVAILABLE')
            if db.scalar(select(SessaoAssistencial.id).where(SessaoAssistencial.agenda_cuidado_id==row.id).limit(1)):
                raise PTSConflict('PLANNING_HAS_SESSIONS')
        self.pts._lock(db,Activity,Activity.id==payload.atividade_id)
        self.pts._lock(db,Occupation,Occupation.id==payload.ocupacao_id)
        self.pts._lock(db,Pair,(Pair.atividade_id==payload.atividade_id)&(Pair.ocupacao_id==payload.ocupacao_id))
        activity=db.scalar(select(Activity).where(Activity.id==payload.atividade_id,Activity.ativo.is_(True),applicable_to(3)))
        occupation=db.scalar(select(Occupation.id).where(Occupation.id==payload.ocupacao_id,Occupation.ativo.is_(True)))
        pair=db.scalar(select(Pair.id).where(Pair.atividade_id==payload.atividade_id,Pair.ocupacao_id==payload.ocupacao_id))
        if activity is None or occupation is None or pair is None:
            raise PlanningInvalid('Atividade ou ocupação incompatível com Saúde Mental.')
        executor_person=db.scalar(select(Profissional.pessoa_id).where(Profissional.id==payload.profissional_id))
        if executor_person is not None:self.pts._lock(db,Pessoa,Pessoa.id==executor_person)
        self.pts._lock(db,Profissional,Profissional.id==payload.profissional_id)
        self.pts._lock(db,Link,(Link.profissional_id==payload.profissional_id)&(Link.instituicao_id==scope['institution']))
        eligible=[l for l,p in self.candidates(db,scope['institution']) if p.id==payload.profissional_id
                  and l.ocupacao_id==payload.ocupacao_id and l.data_inicio<=payload.data_inicio
                  and (l.data_fim is None or l.data_fim>=payload.data_fim)]
        if not eligible:raise PlanningInvalid('Executor sem vínculo institucional ativo que cubra a ocupação e todo o período.')
        try:q=planned_quantity(payload.data_inicio,payload.data_fim,payload.frequencia_semanal,payload.duracao_minutos,payload.quantidade_sessoes)
        except ValueError as exc:raise PlanningInvalid(str(exc)) from None
        values=payload.model_dump();values['quantidade_sessoes']=q['quantidade_sessoes']
        if row is None:
            row=AgendaCuidado(pts_id=pts_id,objetivo_id=objective_id,status='PLANEJADO',**values);db.add(row)
        else:
            for field,value in values.items():setattr(row,field,value)
        db.flush()
        return self.outputs(db,[AgendaCuidado.id==row.id])[0]
