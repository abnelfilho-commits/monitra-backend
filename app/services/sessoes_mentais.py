"""Context adapter over canonical scheduling/session/longitudinal primitives.
Caller owns the transaction. Institution + agenda/session locks serialize writes.
"""
from datetime import datetime
from types import SimpleNamespace
from sqlalchemy import select
from app.models import AgendaCuidado, PTS, SessaoAssistencial, RegistroLongitudinal, RespostaRegistro, CampoFormulario
from app.services.planejamento_mental import PlanningService, PlanningInvalid
from app.models.pts import PTSObjetivo
from app.schemas.planejamento_mental import PlanningInput
from app.services.pts_mental import PTSDenied, PTSConflict
from app.services.scheduling_models import PlanejamentoAssistencial
from app.services.scheduling_engine import SchedulingEngine
from app.services.scheduling_service import SchedulingService
from app.services.session_service import SessionService
from app.services.registros_longitudinais import persistir_registro_longitudinal, extrair_valor
from app.schemas.registros_longitudinais import RegistroLongitudinalCreate, CampoResposta
from app.schemas.sessoes_mentais import CronogramaMentalOut, SessaoMentalOut


class SessoesMentaisService:
    planning = PlanningService()

    def origin(self, db, scope, pts_id, objective_id, planning_id, write=False):
        plan = self.planning.ancestry(db, scope, pts_id, objective_id, write)
        q = select(AgendaCuidado).where(AgendaCuidado.id == planning_id,
            AgendaCuidado.pts_id == pts_id, AgendaCuidado.objetivo_id == objective_id)
        if write: q = q.with_for_update().execution_options(populate_existing=True)
        agenda = db.scalar(q)
        if agenda is None: raise PTSDenied('SESSION_UNAVAILABLE')
        return agenda, plan

    def sessions(self, db, agenda, plan):
        rows = db.scalars(select(SessaoAssistencial).where(SessaoAssistencial.agenda_cuidado_id == agenda.id)
            .order_by(SessaoAssistencial.numero_sessao)).all()
        for row in rows:
            if row.paciente_id != plan.paciente_id or row.profissional_id != agenda.profissional_id:
                raise PTSConflict('SESSION_ANCESTRY_CONFLICT')
        return rows

    def output_session(self, db, row, plan):
        if row.paciente_id != plan.paciente_id:
            raise PTSConflict('SESSION_ANCESTRY_CONFLICT')
        result = SessaoMentalOut.model_validate(row)
        if row.registro_longitudinal_id is not None:
            record = db.get(RegistroLongitudinal, row.registro_longitudinal_id)
            if record is None or record.contexto_assistencial_id != plan.contexto_assistencial_id or record.modulo_id != 3 or record.paciente_id != plan.paciente_id:
                raise PTSConflict('SESSION_RECORD_CONFLICT')
            result.autor_usuario_id = record.criado_por_usuario_id
            for name, answer in db.execute(select(CampoFormulario.nome_campo, RespostaRegistro)
                .join(RespostaRegistro, RespostaRegistro.campo_id == CampoFormulario.id)
                .where(RespostaRegistro.registro_id == record.id)):
                if name == 'narrativa_atendimento': result.narrativa = extrair_valor(answer)
                if name == 'proximos_passos': result.proximos_passos = extrair_valor(answer)
        return result

    def read(self, db, scope, pts_id, objective_id, planning_id):
        agenda, plan = self.origin(db, scope, pts_id, objective_id, planning_id)
        return self.output(db, scope, agenda, plan)

    def output(self, db, scope, agenda, plan):
        rows = self.sessions(db, agenda, plan)
        display = self.planning.outputs(db, [AgendaCuidado.id == agenda.id])[0]
        proposal = [] if rows else SchedulingEngine.generate_sessions(PlanejamentoAssistencial.from_model(agenda))
        if any(agenda.data_fim is None or item.data_agendada > agenda.data_fim for item in proposal):
            raise PlanningInvalid('Cronograma ultrapassa o período do planejamento.')
        return CronogramaMentalOut(pessoa_id=scope['person'], instituicao_id=scope['institution'],
            contexto_assistencial_id=scope['context'], pts_id=plan.id, objetivo_id=agenda.objetivo_id,
            planejamento_id=agenda.id, atividade=display.atividade_nome, ocupacao=display.ocupacao_nome,
            profissional=display.profissional_nome, quantidade_planejada=agenda.quantidade_sessoes,
            quantidade_materializada=len(rows), pode_registrar=self.planning.pts.allowed(db, **scope, capability='ASSISTENCIAL_REGISTRAR') is not None,
            proposta=[dict(numero=i.numero, data=i.data_agendada, duracao_minutos=i.duracao_minutos) for i in proposal],
            sessoes=[self.output_session(db, row, plan) for row in rows])

    def generate(self, db, scope, pts_id, objective_id, planning_id):
        agenda, plan = self.origin(db, scope, pts_id, objective_id, planning_id, True)
        if self.sessions(db, agenda, plan): return self.output(db, scope, agenda, plan)
        # Reuse the canonical executor and quantity validators without editing planning.
        payload = PlanningInput(**{name:getattr(agenda,name) for name in PlanningInput.model_fields})
        self.planning.validate_executor(db, scope, payload)
        self.planning.quantity(db, scope, payload)
        proposed = self.output(db, scope, agenda, plan).proposta
        SchedulingService.confirmar_cronograma(db, agenda, proposed, commit=False)
        return self.output(db, scope, agenda, plan)

    def mutate(self, db, scope, pts_id, objective_id, planning_id, session_id, action=None, attendance=None):
        agenda, plan = self.origin(db, scope, pts_id, objective_id, planning_id, True)
        row = db.scalar(select(SessaoAssistencial).where(SessaoAssistencial.id == session_id,
            SessaoAssistencial.agenda_cuidado_id == agenda.id).with_for_update().execution_options(populate_existing=True))
        if row is None: raise PTSDenied('SESSION_UNAVAILABLE')
        self.sessions(db, agenda, plan)
        self.planning.validate_executor(db, scope, PlanningInput(**{name:getattr(agenda,name) for name in PlanningInput.model_fields}))
        if attendance is not None:
            if row.status != 'EM_ANDAMENTO' or row.registro_longitudinal_id is not None:
                raise PTSConflict('Atendimento já registrado ou sessão fora de atendimento.')
            form, fields = SessionService.form(db, SimpleNamespace(module_id=3))
            answers = [CampoResposta(campo_id=fields['narrativa_atendimento'].id, valor=attendance.narrativa)]
            if attendance.proximos_passos:
                answers.append(CampoResposta(campo_id=fields['proximos_passos'].id, valor=attendance.proximos_passos))
            SessionService.validate_answers(fields, answers)
            record = persistir_registro_longitudinal(db, RegistroLongitudinalCreate(
                paciente_id=plan.paciente_id, modulo_id=3, formulario_id=form.id, origem='PROFISSIONAL',
                data_registro=datetime.now().date(), respostas=answers),
                contexto_assistencial_id=scope['context'], criado_por_usuario_id=scope['actor'])
            row.registro_longitudinal_id = record.id
        else:
            if action == 'finalizar' and row.registro_longitudinal_id is None:
                raise PlanningInvalid('Registre o atendimento antes de finalizar a sessão.')
            SessionService.apply_transition(row, action)
        db.flush()
        return self.output(db, scope, agenda, plan)

    def journey(self, db, scope):
        self.planning.authorize(db, scope)
        rows = db.execute(select(SessaoAssistencial, PTS).join(AgendaCuidado, AgendaCuidado.id == SessaoAssistencial.agenda_cuidado_id)
            .join(PTS, PTS.id == AgendaCuidado.pts_id)
            .join(PTSObjetivo, (PTSObjetivo.id == AgendaCuidado.objetivo_id) & (PTSObjetivo.pts_id == PTS.id)).where(PTS.contexto_assistencial_id == scope['context'], PTS.modulo_id == 3,
            SessaoAssistencial.status == 'REALIZADA', SessaoAssistencial.registro_longitudinal_id.is_not(None))
            .order_by(SessaoAssistencial.data_realizacao.desc(), SessaoAssistencial.id.desc())).all()
        return [self.output_session(db, row, plan) for row, plan in rows]
