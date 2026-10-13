"""Read-only professional MH composition. Authorization precedes every source.

Counts are independent of display limits. No clinical scoring, completion of
missing evidence, historical authorization reconstruction or persisted cockpit.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from sqlalchemy import select, union_all, false, func, case, cast, DateTime, literal
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.models.contexto_assistencial import ContextoAssistencial as Context, ContextoAssistencialLinha as Line
from app.models.paciente import Paciente
from app.models.pessoa import Pessoa
from app.models.institucional import Instituicao
from app.models.modular import ModuloClinico, RegistroLongitudinal as Record, FormularioModulo
from app.models.avaliacao_clinica import AvaliacaoClinica as Assessment
from app.models.registro_proveniencia import RegistroProveniencia
from app.models.diagnostico import Diagnostico
from app.models.intervencao import Intervencao
from app.models.sessao_assistencial import SessaoAssistencial as Session
from app.models.pts import PTS, PTSObjetivo
from app.models.agenda_cuidado import AgendaCuidado as Agenda
from app.models.atividade_terapeutica import AtividadeTerapeutica
from app.services.autorizacao_contextual import AutorizacaoContextualService
from app.services.sessoes_mentais import SessoesMentaisService
from app.services.checkin_bem_estar import CheckinBemEstarService
from app.services.clinical_reading import ClinicalReadingService
from app.services.saude_mental import SaudeMentalService
from app.schemas.cockpit_mental import CockpitMentalOut

TZ = ZoneInfo('America/Cuiaba')
OPEN_SESSIONS = ('AGENDADA', 'CONFIRMADA', 'EM_ANDAMENTO')


def now_local():
    return datetime.now(TZ)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class CockpitMentalService:
    authorization = AutorizacaoContextualService()

    def allowed(self, actor, institutions, capability):
        queries = [self.authorization.authorized_context_query(actor_id=actor, capability=capability,
                   instituicao_id=i).order_by(None) for i in institutions]
        return union_all(*queries) if queries else select(Context.id).where(false())

    def contexts(self, db, actor, institution):
        q = select(Root.instituicao_id).where(Root.usuario_id == actor, Root.ativo.is_(True))
        if institution is not None: q = q.where(Root.instituicao_id == institution)
        institutions = list(db.scalars(q))
        allowed = self.allowed(actor, institutions, 'ASSISTENCIAL_LER')
        return (select(Context.id, Context.paciente_id, Context.instituicao_id,
                    Context.data_inicio, Context.data_fim, Pessoa.id.label('pessoa_id'),
                    func.coalesce(Pessoa.nome_social, Pessoa.nome_completo).label('pessoa'),
                    func.coalesce(Instituicao.nome_fantasia, Instituicao.razao_social).label('instituicao'))
            .join(Paciente, Paciente.id == Context.paciente_id).join(Pessoa, Pessoa.id == Paciente.pessoa_id)
            .join(Instituicao, Instituicao.id == Context.instituicao_id)
            .join(Line, (Line.contexto_assistencial_id == Context.id) & (Line.modulo_id == 3))
            .join(ModuloClinico, ModuloClinico.id == Line.modulo_id)
            .where(Context.id.in_(allowed), Pessoa.ativo.is_(True), Line.ativo.is_(True),
                   ModuloClinico.ativo.is_(True), ModuloClinico.slug == 'saude_mental').cte('cockpit_contexts')), institutions

    @staticmethod
    def reference(row):
        return dict(pessoa_id=row['pessoa_id'], pessoa=row['pessoa'], instituicao_id=row['instituicao_id'],
                    instituicao=row['instituicao'], contexto_assistencial_id=row['id'])

    def compose(self, db, *, user, institution=None, reference_date=None, limit=10):
        with db.no_autoflush:
            return self._compose(db, user, institution, reference_date or now_local().date(), limit)

    def _compose(self, db, user, institution, day, limit):
        SaudeMentalService._catalog(db)
        start_day = day - timedelta(days=29)
        start = datetime.combine(start_day, time.min, TZ).astimezone(timezone.utc).replace(tzinfo=None)
        end = datetime.combine(day + timedelta(days=1), time.min, TZ).astimezone(timezone.utc).replace(tzinfo=None)
        contexts, institutions = self.contexts(db, user.id, institution)
        population = {r['id']: dict(r) for r in db.execute(select(contexts)).mappings()}
        people_count = len({r['pessoa_id'] for r in population.values() if r['data_fim'] is None and r['data_inicio'] <= day})
        writable = set(db.scalars(self.allowed(user.id, institutions, 'ASSISTENCIAL_REGISTRAR')))
        # Reuse the personal assignment/authorization query, without loading a
        # session detail or its narrative for every agenda row.
        personal = SessoesMentaisService().personal_query(db, user)
        session_query = (personal.order_by(None).join(contexts, contexts.c.id == PTS.contexto_assistencial_id)
            .join(PTSObjetivo, (PTSObjetivo.id == Agenda.objetivo_id) & (PTSObjetivo.pts_id == PTS.id))
            .join(AtividadeTerapeutica, AtividadeTerapeutica.id == Agenda.atividade_id)
            .where(Session.paciente_id == contexts.c.paciente_id, PTS.paciente_id == contexts.c.paciente_id,
                   Session.profissional_id == Agenda.profissional_id)
            .with_only_columns(Session.id.label('sessao_id'), PTS.contexto_assistencial_id.label('context_id'),
                Session.data_agendada, Session.data_realizacao, Session.hora_inicio, Session.hora_fim,
                Session.duracao_minutos, Session.status, AtividadeTerapeutica.nome.label('atividade'))).cte('cockpit_sessions')
        s = session_query.c
        today = (s.data_agendada == day) & s.status.in_(OPEN_SESSIONS)
        future = (s.data_agendada > day) & s.status.in_(OPEN_SESSIONS)
        done = (s.data_realizacao == day) & (s.status == 'REALIZADA')
        counts = db.execute(select(*(func.count().filter(condition) for condition in (today, done, future))).select_from(session_query)).one()
        def session_list(condition):
            rows = db.execute(select(session_query).where(condition).order_by(s.data_agendada,
                s.hora_inicio.asc().nulls_last(), s.sessao_id).limit(limit+1)).mappings().all()
            return [dict(**self.reference(population[r['context_id']]),
                         **{k:v for k,v in r.items() if k not in ('context_id','data_realizacao')},
                         pode_registrar=r['context_id'] in writable) for r in rows[:limit]], len(rows)>limit
        agenda, more_agenda = session_list(today)
        upcoming, more_upcoming = session_list(future)
        reasons = []
        def reason(context_id, code, timestamp, source, identity, dimensions=()):
            reasons.append(dict(**self.reference(population[context_id]), codigo=code, data=utc(timestamp),
                                fonte=source, referencia_id=identity, dimensoes=list(dimensions)))
        # Complete canonical ordinal history is necessary for the official
        # dimension comparison; only contexts with recent observations are read.
        recent_contexts = (select(Record.contexto_assistencial_id).join(FormularioModulo, FormularioModulo.id == Record.formulario_id)
            .where(FormularioModulo.codigo == 'BEM_ESTAR_V1', Record.modulo_id == 3,
                   Record.criado_em >= start, Record.criado_em < end))
        recent_scope = select(contexts).where(contexts.c.id.in_(recent_contexts)).subquery()
        checkins = CheckinBemEstarService().read_authorized_batch(db, recent_scope, before=end)
        for context_id, records in checkins.items():
            reading = ClinicalReadingService().get_contextual_reading(pessoa_id=population[context_id]['pessoa_id'],
                contexto_assistencial_id=context_id, care_line='MENTAL_HEALTH', checkins=records)
            for request in reading.evidence['help_requests']:
                stamp = datetime.fromisoformat(request['date'])
                if utc(start) <= stamp < utc(end): reason(context_id,'APOIO_AUTORREFERIDO',stamp,'CHECKIN',request['record_id'])
            changed = [key for key,value in reading.evidence['dimensions'].items()
                       if value['state'] in ('PIORA_OBSERVACIONAL','MELHORA_OBSERVACIONAL','OSCILACAO')]
            if changed and records:
                last = records[-1]
                if utc(start) <= last.data_hora < utc(end):
                    reason(context_id,'MUDANCA_OBSERVACIONAL',last.data_hora,'CHECKIN',last.id,changed)
        assessments = (select(Assessment.id, Assessment.instrumento, Record.criado_em, contexts.c.id.label('context_id'),
                              Assessment.resultado['alertas'].label('alerts'))
            .join(Record, Record.id == Assessment.registro_id).join(contexts, contexts.c.id == Record.contexto_assistencial_id)
            .join(RegistroProveniencia, RegistroProveniencia.registro_id == Record.id)
            .where(Assessment.modulo_id == 3, Record.modulo_id == 3, Assessment.paciente_id == contexts.c.paciente_id,
                   Record.paciente_id == contexts.c.paciente_id, RegistroProveniencia.respondente_pessoa_id == contexts.c.pessoa_id,
                   Assessment.instrumento.in_(('PHQ9','GAD7','CBI')), Record.criado_em >= start, Record.criado_em < end))
        for r in db.execute(assessments).mappings():
            if isinstance(r['alerts'], list) and any(isinstance(a,str) and a.strip() for a in r['alerts']):
                reason(r['context_id'],'INSTRUMENTO_REVISAO',r['criado_em'],r['instrumento'],r['id'])
        # An open persisted session before the reference civil day is an objective
        # pending outcome, not a clinical continuity score. No arbitrary grace period.
        pending = db.execute(select(s.context_id, s.sessao_id, s.data_agendada).where(
            s.data_agendada < day, s.status.in_(OPEN_SESSIONS))).all()
        for context_id, identity, scheduled in pending:
            reason(context_id,'SESSAO_SEM_DESFECHO',datetime.combine(scheduled,time.min,TZ),'SESSAO',identity)
        grouped = {}
        for item in reasons:
            entry = grouped.setdefault(item['pessoa_id'], dict(pessoa_id=item['pessoa_id'],pessoa=item['pessoa'],
                evidencia_mais_recente=item['data'],motivos=[]))
            entry['motivos'].append(item)
            entry['evidencia_mais_recente'] = max(entry['evidencia_mais_recente'],item['data'])
        for entry in grouped.values():
            entry['motivos'].sort(key=lambda r:(-r['data'].timestamp(),r['contexto_assistencial_id'],r['codigo'],r['referencia_id']))
        people = sorted(grouped.values(),key=lambda r:(-r['evidencia_mais_recente'].timestamp(),r['pessoa_id']))
        events = self.events(db, contexts, session_query, start, end, start_day, day, limit)
        return CockpitMentalOut(resumo=dict(pessoas_em_acompanhamento=people_count,atendimentos_hoje=counts[0],
            realizados_hoje=counts[1],proximos_atendimentos=counts[2]),agenda_hoje=agenda,proximos_atendimentos=upcoming,
            pessoas_para_acompanhamento=people[:limit],atividade_recente=[dict(**self.reference(population[r['context_id']]),
                tipo=r['tipo'], referencia_id=r['referencia_id'], data=utc(r['data']) if r['precisao']=='INSTANTE' else datetime.combine(r['data'].date(),time.min,TZ),
                precisao=r['precisao']) for r in events[:limit]],
            metadados=dict(data_referencia=day,fuso=TZ.key,instituicao_id=institution,limit=limit,
                inicio_janela_evidencias=start_day,tem_mais=dict(agenda_hoje=more_agenda,proximos_atendimentos=more_upcoming,
                    pessoas_para_acompanhamento=len(people)>limit,atividade_recente=len(events)>limit),
                limitacoes=['Data de referência não reconstrói autorização nem status históricos.',
                    'Apoio autorreferido não possui estado canônico de resolução; fora de 30 dias não é presumido pendente.',
                    'Instrumentos entram como motivo somente quando possuem alertas persistidos; nenhuma faixa nova é calculada.',
                    'Realização de sessão possui precisão de data, sem horário efetivo obrigatório.']))

    def events(self, db, contexts, sessions, start, end, first_day, day, limit):
        def event_query(model, stamp, kind, precision):
            return (select(model.id.label('referencia_id'), model.contexto_assistencial_id.label('context_id'),
                    cast(stamp,DateTime).label('data'),literal(kind).label('tipo'),literal(precision).label('precisao'))
                .join(contexts,contexts.c.id==model.contexto_assistencial_id)
                .where(model.modulo_id==3,model.paciente_id==contexts.c.paciente_id))
        checkins = (event_query(Record,Record.criado_em,'CHECKIN','INSTANTE')
            .join(FormularioModulo,FormularioModulo.id==Record.formulario_id)
            .join(RegistroProveniencia,RegistroProveniencia.registro_id==Record.id)
            .where(FormularioModulo.codigo=='BEM_ESTAR_V1',RegistroProveniencia.respondente_pessoa_id==contexts.c.pessoa_id,
                   Record.criado_em>=start,Record.criado_em<end))
        instruments = (select(Assessment.id.label('referencia_id'),Record.contexto_assistencial_id.label('context_id'),
            Record.criado_em.label('data'),Assessment.instrumento.label('tipo'),literal('INSTANTE').label('precisao'))
            .join(Record,Record.id==Assessment.registro_id).join(contexts,contexts.c.id==Record.contexto_assistencial_id)
            .join(RegistroProveniencia,RegistroProveniencia.registro_id==Record.id)
            .where(Assessment.modulo_id==3,Record.modulo_id==3,Assessment.paciente_id==contexts.c.paciente_id,
                   Record.paciente_id==contexts.c.paciente_id,RegistroProveniencia.respondente_pessoa_id==contexts.c.pessoa_id,
                   Assessment.instrumento.in_(('PHQ9','GAD7','CBI')),Record.criado_em>=start,Record.criado_em<end))
        diagnoses=event_query(Diagnostico,Diagnostico.data_diagnostico,'DIAGNOSTICO','DATA').where(
            Diagnostico.data_diagnostico>=first_day,Diagnostico.data_diagnostico<=day)
        interventions=event_query(Intervencao,Intervencao.data_intervencao,'INTERVENCAO','INSTANTE').where(
            Intervencao.data_intervencao>=start,Intervencao.data_intervencao<end)
        s=sessions.c
        completed=select(s.sessao_id.label('referencia_id'),s.context_id,cast(s.data_realizacao,DateTime).label('data'),
            literal('SESSAO').label('tipo'),literal('DATA').label('precisao')).where(
                s.status=='REALIZADA',s.data_realizacao>=first_day,s.data_realizacao<=day)
        all_events=union_all(checkins,instruments,diagnoses,interventions,completed).subquery()
        # Date-only events sort at the beginning of their local civil day.
        ordering=case((all_events.c.precisao=='DATA',func.timezone('UTC',func.timezone(TZ.key,all_events.c.data))),else_=all_events.c.data)
        return db.execute(select(all_events).order_by(ordering.desc(),all_events.c.tipo,all_events.c.context_id,
            all_events.c.referencia_id.desc()).limit(limit+1)).mappings().all()
