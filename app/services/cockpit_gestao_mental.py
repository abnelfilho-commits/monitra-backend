"""Restricted institutional operations, not anonymized clinical statistics."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import Date, select, func, or_
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.profissional import Profissional
from app.models.institucional import Instituicao, PacienteInstituicao, ProfissionalInstituicao
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.contexto_assistencial import ContextoAssistencial as Context, ContextoAssistencialLinha as Line
from app.models.sessao_assistencial import SessaoAssistencial as Session
from app.models.agenda_cuidado import AgendaCuidado as Agenda
from app.models.pts import PTS, PTSObjetivo
from app.services.saude_mental import SaudeMentalService
from app.schemas.cockpit_gestao_mental import CockpitGestaoMentalOut

TZ = ZoneInfo('America/Cuiaba')
COHORT_STATES = ('AGENDADA', 'CONFIRMADA', 'EM_ANDAMENTO', 'REALIZADA', 'FALTOU')


class ManagementDenied(ValueError):
    pass


class ManagementPeriodInvalid(ValueError):
    pass


def today_local():
    return datetime.now(TZ).date()


def closed_weeks(weeks, today):
    if type(weeks) is not int or weeks not in (4, 8, 12):
        raise ManagementPeriodInvalid('COMPLETE_WEEKS_REQUIRED')
    monday = today - timedelta(days=today.weekday())
    return monday - timedelta(weeks=weeks), monday - timedelta(days=1)


class CockpitGestaoMentalService:
    def authorized_institutions(self, db, actor_id, institution=None):
        actor = db.execute(select(Usuario.id, Usuario.perfil, Usuario.ativo,
            Pessoa.ativo.label('pessoa_ativa')).outerjoin(Pessoa, Pessoa.id == Usuario.pessoa_id)
            .where(Usuario.id == actor_id)).one_or_none()
        if actor is None or not actor.ativo:
            raise ManagementDenied('MANAGEMENT_UNAVAILABLE')
        # Explicit management ADMIN rule, not AutorizacaoInstitucional.authorize.
        admin = actor.perfil == 'ADMIN'
        query = select(Instituicao.id).where(Instituicao.ativo.is_(True))
        if not admin:
            if actor.pessoa_ativa is not True:
                raise ManagementDenied('MANAGEMENT_UNAVAILABLE')
            query = query.join(Root, Root.instituicao_id == Instituicao.id).where(
                Root.usuario_id == actor_id, Root.ativo.is_(True), Root.perfil_institucional == 'GESTOR')
        ids = list(db.scalars(query.order_by(Instituicao.id)))
        # No lookup of denied institution and no traversal of instituicao_pai_id.
        if institution is not None:
            if institution not in ids:
                raise ManagementDenied('MANAGEMENT_UNAVAILABLE')
            ids = [institution]
        if not ids and not admin:
            raise ManagementDenied('MANAGEMENT_UNAVAILABLE')
        return ids, admin

    def _aggregate(self, db, ids, start, end, today):
        # Current administrative workforce: not an MH authorization or clinical roster.
        professionals = db.scalar(select(func.count(func.distinct(Profissional.id)))
            .join(ProfissionalInstituicao, ProfissionalInstituicao.profissional_id == Profissional.id)
            .join(Pessoa, Pessoa.id == Profissional.pessoa_id)
            .where(ProfissionalInstituicao.instituicao_id.in_(ids),
                ProfissionalInstituicao.ativo.is_(True),
                ProfissionalInstituicao.data_inicio <= today,
                or_(ProfissionalInstituicao.data_fim.is_(None), ProfissionalInstituicao.data_fim >= today),
                Profissional.ativo.is_(True), Pessoa.ativo.is_(True)))
        # Historical ancestry remains valid after context/line/link closure.
        # EXISTS avoids multiplying sessions through institutional/line joins.
        contexts = (select(Context.id, Context.paciente_id)
            .join(PacienteInstituicao, (PacienteInstituicao.id == Context.paciente_instituicao_id)
                & (PacienteInstituicao.paciente_id == Context.paciente_id)
                & (PacienteInstituicao.instituicao_id == Context.instituicao_id))
            .where(Context.instituicao_id.in_(ids), select(Line.id).where(
                Line.contexto_assistencial_id == Context.id, Line.modulo_id == 3).exists())
            .cte('management_contexts'))
        sessions = (select(Session.id, Session.status, Session.data_agendada, Session.data_realizacao)
            .join(Agenda, Agenda.id == Session.agenda_cuidado_id)
            .join(PTS, PTS.id == Agenda.pts_id)
            .join(PTSObjetivo, (PTSObjetivo.id == Agenda.objetivo_id) & (PTSObjetivo.pts_id == PTS.id))
            .join(contexts, contexts.c.id == PTS.contexto_assistencial_id)
            .where(PTS.modulo_id == 3, PTS.paciente_id == contexts.c.paciente_id,
                Session.paciente_id == contexts.c.paciente_id,
                Session.profissional_id.is_not_distinct_from(Agenda.profissional_id))).cte('management_sessions')
        s = sessions.c

        def weekly(column, predicate):
            # PostgreSQL DATE values have no timezone conversion. Monday buckets.
            week = func.date_trunc('week', column).cast(Date)
            return dict(db.execute(select(week, func.count(func.distinct(s.id)))
                .where(column.between(start, end), predicate).group_by(week)).all())

        programmed = weekly(s.data_agendada, s.status.in_(COHORT_STATES))
        realized = weekly(s.data_realizacao,
            (s.status == 'REALIZADA') & (s.data_realizacao <= today))
        series = []
        day = start
        while day <= end:
            series.append(dict(semana=day, programados=programmed.get(day, 0), realizados=realized.get(day, 0)))
            day += timedelta(days=7)
        return dict(indicadores=dict(instituicoes_ativas=len(ids), profissionais_vinculados=professionals,
                atendimentos_programados=sum(r['programados'] for r in series),
                atendimentos_realizados=sum(r['realizados'] for r in series)),
            atendimentos_programados_realizados=series,
            evolucao_atendimentos=[dict(semana=r['semana'], realizados=r['realizados']) for r in series])

    def compose(self, db, *, actor_id, institution=None, weeks=4):
        with db.no_autoflush:
            ids, admin = self.authorized_institutions(db, actor_id, institution)
            today = today_local()
            start, end = closed_weeks(weeks, today)
            SaudeMentalService._catalog(db)
            result = self._aggregate(db, ids, start, end, today)
            return CockpitGestaoMentalOut(**result, metadados=dict(
                data_inicio=start, data_fim=end, data_consulta=today, semanas=weeks,
                instituicao_ids=ids, escopo='GLOBAL' if admin and institution is None else 'INSTITUICOES_AUTORIZADAS',
                limitacoes=[
                    'Instituições e profissionais representam a situação administrativa atual, independentemente do período.',
                    'Profissionais vinculados não representa profissionais autorizados em Saúde Mental.',
                    'Programados usa data agendada; realizados usa data efetiva. As contagens não devem ser somadas.',
                    'Contagens operacionais restritas, não anonimizadas: existe inferência residual em grupos pequenos e consultas sucessivas.',
                    'Correções nas fontes podem alterar resultados históricos; não há snapshots estatísticos.',
                ]))
