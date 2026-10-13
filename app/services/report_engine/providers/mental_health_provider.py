"""Authorized contextual sources; presentation only, no instrument/clinical rules."""
from datetime import datetime, timezone
from sqlalchemy import select
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso
from app.models.contexto_assistencial import ContextoAssistencial
from app.models.pessoa import Pessoa
from app.services.saude_mental import SaudeMentalService, MentalHealthUnavailable
from app.services.care_lines.registry import MENTAL_HEALTH, care_line_registry, CAP_REPORT
from app.services.checkin_bem_estar import CheckinBemEstarService
from app.services.diagnostico_mental import DiagnosticoMentalService
from app.services.intervencao_mental import IntervencaoMentalService
from app.services.phq9 import PHQ9Service
from app.services.gad7 import GAD7Service
from app.services.cbi import CBIService
from app.services.pts_mental import PTSMentalService
from app.services.planejamento_mental import PlanningService
from app.services.sessoes_mentais import SessoesMentaisService
from app.services.clinical_reading import ClinicalReadingService
from app.services.clinical_reading.providers.assessment_evidence import assessment_evidence
from ..base_provider import BaseProvider, ProviderResult


def resolve_scope(c):
    identity = c.parameters.get('contexto_assistencial_id')
    if (type(identity) is not int or identity <= 0 or c.db is None or
            care_line_registry.get(c.module) != MENTAL_HEALTH or not MENTAL_HEALTH.supports(CAP_REPORT)):
        raise MentalHealthUnavailable('REPORT_UNAVAILABLE')
    service = SaudeMentalService()
    with c.db.no_autoflush:
        service._catalog(c.db)
        # Enumerate only the caller's roots; all resource selection remains inside
        # the existing ASSISTENCIAL_LER query, before loading clinical content.
        institutions = c.db.scalars(select(UsuarioInstituicaoAcesso.instituicao_id).where(
            UsuarioInstituicaoAcesso.usuario_id == c.requested_by,
            UsuarioInstituicaoAcesso.ativo.is_(True))).all()
        for institution in institutions:
            row = c.db.execute(service._query(actor_id=c.requested_by, institution=institution).where(
                ContextoAssistencial.id == identity, ContextoAssistencial.paciente_id == c.subject_id, Pessoa.ativo.is_(True)
            )).mappings().one_or_none()
            if row is not None and row['line_active'] is True:
                c.subject = dict(id=c.subject_id, name=row['nome_social'] or row['nome_completo'],
                    pessoa_id=row['pessoa_id'], contexto_assistencial_id=identity,
                    instituicao_id=institution, instituicao=row['instituicao_nome'])
                return MENTAL_HEALTH
    raise MentalHealthUnavailable('REPORT_UNAVAILABLE')


def clinical_date(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).date() if value.tzinfo else value.date()
    return value


def in_period(c, value):
    return value is not None and c.period_start <= clinical_date(value) <= c.period_end


def overlaps(c, start, end):
    return start <= c.period_end and (end is None or end >= c.period_start)


class MentalHealthProvider(BaseProvider):
    code = 'MENTAL_HEALTH_PROVIDER'
    required = True

    def collect(self, c):
        resolve_scope(c)
        scope = dict(actor=c.requested_by, institution=c.subject['instituicao_id'],
                     person=c.subject['pessoa_id'], context=c.subject['contexto_assistencial_id'])
        with c.db.no_autoflush:
            checkins = [r for r in CheckinBemEstarService().journey(c.db, **scope).checkins if in_period(c, r.data_hora)]
            diagnoses = [r for r in DiagnosticoMentalService().journey(c.db, **scope).itens if in_period(c, r.data_diagnostico)]
            interventions = [r for r in IntervencaoMentalService().journey(c.db, **scope).itens if in_period(c, r.data_intervencao)]
            applications = {name: [r for r in service().journey(c.db, **scope).itens if in_period(c, r.data_hora)]
                            for name, service in (('phq9', PHQ9Service), ('gad7', GAD7Service), ('cbi', CBIService))}
            evidence = assessment_evidence(pessoa_id=scope['person'], contexto_assistencial_id=scope['context'],
                instituicao_id=scope['institution'], applications=applications)
            c.clinical_reading = ClinicalReadingService().get_contextual_reading(
                pessoa_id=scope['person'], contexto_assistencial_id=scope['context'], care_line=MENTAL_HEALTH.code,
                checkins=checkins, assessments=evidence, diagnoses=diagnoses, interventions=interventions)
            plans, planning, sessions = [], [], []
            planner, session_service = PlanningService(), SessoesMentaisService()
            for plan in PTSMentalService().journey(c.db, **scope).itens:
                if overlaps(c, plan.data_inicio, plan.data_fim):
                    plans.append(plan)
                for objective in plan.objetivos:
                    for agenda in planner.list(c.db, scope, plan.id, objective.id):
                        if overlaps(c, agenda.data_inicio, agenda.data_fim):
                            planning.append(agenda)
                        # Canonical origin/ancestry and output validation, no parallel session SQL.
                        model, parent = session_service.origin(c.db, scope, plan.id, objective.id, agenda.id)
                        for row in session_service.sessions(c.db, model, parent):
                            if in_period(c, row.data_realizacao or row.data_agendada):
                                sessions.append(session_service.output_session(c.db, row, parent))
            data = dict(checkins=checkins, assessments=evidence, diagnoses=diagnoses,
                        interventions=interventions, plans=plans, planning=planning,
                        sessions=sorted(sessions, key=lambda r: (r.data_realizacao or r.data_agendada, r.id)))
        return ProviderResult(self.code, self.version, data=data)
