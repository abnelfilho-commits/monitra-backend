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

    def generate(self, db, scope, pts_id, objective_id, planning_id, reviewed=None):
        agenda, plan = self.origin(db, scope, pts_id, objective_id, planning_id, True)
        existing = self.sessions(db, agenda, plan)
        if existing:
            if reviewed is not None:
                expected = [(r.numero_sessao, r.data_agendada, r.hora_inicio, r.hora_fim) for r in existing]
                received = [(r.numero, r.data, r.hora_inicio, r.hora_fim) for r in sorted(reviewed, key=lambda i: i.numero)]
                if expected != received: raise PTSConflict('Cronograma já confirmado com outros dados.')
            return self.output(db, scope, agenda, plan)
        # Reuse the canonical executor and quantity validators without editing planning.
        payload = PlanningInput(**{name:getattr(agenda,name) for name in PlanningInput.model_fields})
        self.planning.validate_executor(db, scope, payload)
        self.planning.quantity(db, scope, payload)
        proposed = self.output(db, scope, agenda, plan).proposta
        if reviewed is not None:
            if sorted(i.numero for i in reviewed) != list(range(1, agenda.quantidade_sessoes + 1)):
                raise PlanningInvalid('Quantidade ou numeração incompatível com o planejamento.')
            ordered = sorted(reviewed, key=lambda i: i.numero)
            for i, item in enumerate(ordered):
                if not agenda.data_inicio <= item.data <= agenda.data_fim:
                    raise PlanningInvalid('Data fora do período do planejamento.')
                if item.hora_inicio.tzinfo or item.hora_fim.tzinfo:
                    raise PlanningInvalid('Informe horários locais sem fuso.')
                start, end = datetime.combine(item.data, item.hora_inicio), datetime.combine(item.data, item.hora_fim)
                if (end - start).total_seconds() != agenda.duracao_minutos * 60:
                    raise PlanningInvalid('Os horários devem respeitar a duração planejada.')
                if i and start < datetime.combine(ordered[i-1].data, ordered[i-1].hora_fim):
                    raise PlanningInvalid('Ocorrências fora de ordem ou sobrepostas.')
            proposed = ordered
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


    def operational_origin(self, db, identity, actor):
        """Resolve persisted ancestry, never an institution supplied by the client."""
        from app.models.contexto_assistencial import ContextoAssistencial
        from app.models.paciente import Paciente
        row = db.execute(select(SessaoAssistencial, AgendaCuidado, PTS, ContextoAssistencial, Paciente)
            .join(AgendaCuidado, AgendaCuidado.id == SessaoAssistencial.agenda_cuidado_id)
            .join(PTS, PTS.id == AgendaCuidado.pts_id)
            .join(ContextoAssistencial, ContextoAssistencial.id == PTS.contexto_assistencial_id)
            .join(Paciente, Paciente.id == ContextoAssistencial.paciente_id)
            .where(SessaoAssistencial.id == identity)).one_or_none()
        if row is None: return None
        session, agenda, plan, context, patient = row
        if plan.modulo_id != 3 or plan.paciente_id != context.paciente_id:
            raise PTSDenied('SESSION_UNAVAILABLE')
        scope = dict(actor=actor, institution=context.instituicao_id, person=patient.pessoa_id, context=context.id)
        self.origin(db, scope, plan.id, agenda.objetivo_id, agenda.id)
        self.sessions(db, agenda, plan)
        return session, agenda, plan, scope

    def personal_sessions(self, db, user):
        from app.models.usuario import Usuario
        from app.models.paciente import Paciente
        from app.models.pessoa import Pessoa
        from app.models.profissional import Profissional
        from app.services.autorizacao_contextual import AutorizacaoContextualService
        from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso
        from app.models.contexto_assistencial import ContextoAssistencialLinha
        from app.models.modular import ModuloClinico
        from sqlalchemy import union_all
        institutions = db.scalars(select(UsuarioInstituicaoAcesso.instituicao_id).where(
            UsuarioInstituicaoAcesso.usuario_id == user.id, UsuarioInstituicaoAcesso.ativo.is_(True))).all()
        if not institutions: return []
        allowed = union_all(*(AutorizacaoContextualService().authorized_context_query(
            actor_id=user.id, capability='ASSISTENCIAL_LER', instituicao_id=i).order_by(None) for i in institutions))
        rows = db.scalars(select(SessaoAssistencial).join(AgendaCuidado, AgendaCuidado.id == SessaoAssistencial.agenda_cuidado_id)
            .join(PTS, PTS.id == AgendaCuidado.pts_id)
            .join(Paciente, Paciente.id == PTS.paciente_id)
            .join(Pessoa, Pessoa.id == Paciente.pessoa_id)
            .join(ContextoAssistencialLinha, (ContextoAssistencialLinha.contexto_assistencial_id == PTS.contexto_assistencial_id)
                  & (ContextoAssistencialLinha.modulo_id == PTS.modulo_id))
            .join(ModuloClinico, ModuloClinico.id == PTS.modulo_id)
            .join(Profissional, Profissional.id == SessaoAssistencial.profissional_id)
            .join(Usuario, Usuario.pessoa_id == Profissional.pessoa_id)
            .where(Usuario.id == user.id, Pessoa.ativo.is_(True), PTS.modulo_id == 3, ContextoAssistencialLinha.ativo.is_(True),
                   ModuloClinico.ativo.is_(True), ModuloClinico.slug == 'saude_mental', PTS.contexto_assistencial_id.in_(allowed))
            .order_by(SessaoAssistencial.data_agendada, SessaoAssistencial.hora_inicio, SessaoAssistencial.id)).all()
        from app.models.institucional import Instituicao
        result, agendas = [], {}
        for row in rows:
            if row.agenda_cuidado_id not in agendas:
                session, agenda, plan, scope = self.operational_origin(db, row.id, user.id)
                display = self.planning.outputs(db, [AgendaCuidado.id == agenda.id])[0]
                context = dict(id=scope['context'], instituicao_id=scope['institution'],
                    instituicao=db.get(Instituicao, scope['institution']).razao_social, modulo_id=3, pts_id=plan.id)
                name = db.get(Pessoa, scope['person']).nome_completo
                writable = self.planning.pts.allowed(db, **scope, capability='ASSISTENCIAL_REGISTRAR') is not None
                agendas[agenda.id] = plan, scope, display, context, name, writable
            plan, scope, display, context, name, writable = agendas[row.agenda_cuidado_id]
            self.output_session(db, row, plan)
            result.append(dict(id=row.id, pessoa_id=scope['person'], pessoa=name,
                paciente=name, contexto=context, pode_registrar=writable,
                agenda_cuidado_id=row.agenda_cuidado_id, profissional_id=row.profissional_id, numero_sessao=row.numero_sessao,
                data_agendada=row.data_agendada, hora_inicio=row.hora_inicio, hora_fim=row.hora_fim,
                duracao_minutos=row.duracao_minutos, status=row.status, atividade=display.atividade_nome))
        return result

    def operational_detail(self, db, identity, actor):
        from app.models.pessoa import Pessoa
        from app.models.institucional import Instituicao
        from app.services.assistential_session_service import AssistentialSessionService
        origin = self.operational_origin(db, identity, actor)
        if origin is None: return None
        row, agenda, plan, scope = origin
        person = db.get(Pessoa, scope['person'])
        display = self.planning.outputs(db, [AgendaCuidado.id == agenda.id])[0]
        rows = self.sessions(db, agenda, plan)
        output = self.output_session(db, row, plan)
        record = db.get(RegistroLongitudinal, row.registro_longitudinal_id) if row.registro_longitudinal_id else None
        following = next((s for s in rows if s.numero_sessao > row.numero_sessao and s.status == 'AGENDADA'), None)
        objective = db.get(PTSObjetivo, agenda.objetivo_id)
        return dict(sessao=dict(id=row.id, numero=row.numero_sessao, status=row.status, data=row.data_agendada,
                hora_inicio=row.hora_inicio, hora_fim=row.hora_fim, duracao_minutos=row.duracao_minutos),
            pessoa=dict(id=person.id, nome=person.nome_completo), paciente=None,
            contexto=dict(id=scope['context'], instituicao_id=scope['institution'],
                instituicao=db.get(Instituicao, scope['institution']).razao_social, modulo_id=3, pts_id=plan.id),
            pode_registrar=self.planning.pts.allowed(db, **scope, capability='ASSISTENCIAL_REGISTRAR') is not None,
            objetivo=dict(id=objective.id, descricao=objective.descricao, status=objective.status, prioridade=objective.prioridade),
            atividade=dict(id=agenda.atividade_id, nome=display.atividade_nome),
            profissional=dict(id=agenda.profissional_id, nome=display.profissional_nome, ocupacao=display.ocupacao_nome),
            registro_longitudinal=dict(id=record.id, data=record.data_registro, origem=record.origem) if record else None,
            narrativa=output.narrativa, proximos_passos=output.proximos_passos, autor_usuario_id=output.autor_usuario_id,
            proxima_sessao=dict(id=following.id, numero=following.numero_sessao, data=following.data_agendada, status=following.status) if following else None,
            resumo=AssistentialSessionService.montar_resumo_sessao(row, SimpleNamespace(nome=person.nome_completo),
                SimpleNamespace(nome=display.atividade_nome), record, [], [], following,
                sum(s.status == 'REALIZADA' for s in rows), len(rows)))

    def operational_mutate(self, db, identity, actor, action=None, attendance=None):
        origin = self.operational_origin(db, identity, actor)
        if origin is None: return None
        row, agenda, plan, scope = origin
        result = self.mutate(db, scope, plan.id, agenda.objetivo_id, agenda.id, identity, action, attendance)
        return next(s for s in result.sessoes if s.id == identity)
