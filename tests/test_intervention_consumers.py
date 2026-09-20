"""Existing consumers keep generic selection, dates, counts and session context."""
from datetime import date, datetime, timedelta
from unittest.mock import patch
from sqlalchemy import text, DateTime
from app.models import (Intervencao, PTS, PTSObjetivo, AtividadeTerapeutica,
                        AgendaCuidado, SessaoAssistencial)
from app.services.timeline_service import TimelineService
from app.services.cockpit_gestao_service import CockpitGestaoService
from app.services.cockpit_profissional_service import CockpitProfissionalService
from app.services.assistential_session_service import AssistentialSessionService
from test_interventions import Fixture, DAY


class ConsumerTests(Fixture):
    def seed_interventions(self):
        for index,module in enumerate((1,1,2),1):
            self.db.add(Intervencao(id=index,paciente_id=10,profissional_id=50,modulo_id=module,
                tipo='authored',descricao='Synthetic '+str(index),data_intervencao=datetime.combine(date.today(),DAY.time())))
        self.db.commit()
        self.cardio()

    def typed_execute(self, original):
        # Raw SQL date values are native datetime on PostgreSQL; emulate that driver
        # behavior on SQLite without changing the selected rows or SQL predicates.
        def execute(statement,*args,**kwargs):
            if 'FROM intervencoes' in str(statement):
                statement=statement.columns(data_intervencao=DateTime(),created_at=DateTime())
            return original(statement,*args,**kwargs)
        return execute

    def test_report_keeps_all_generic_and_excludes_cardio(self):
        self.seed_interventions()
        original=self.db.execute
        with patch.object(self.db,'execute',side_effect=self.typed_execute(original)), \
             patch.object(TimelineService,'get_daily_records',return_value=[]), \
             patch.object(TimelineService,'get_assessments',return_value=[]), \
             patch.object(TimelineService,'get_assistential_events',return_value=[]):
            events=TimelineService.get_timeline(self.db,10)
        self.assertEqual(len(events),3)
        self.assertEqual({e['id'] for e in events},{1,2,3})
        self.assertTrue(all(e['tipo_evento']=='INTERVENCAO' for e in events))
        self.assertEqual({e['descricao'] for e in events},{'Synthetic 1','Synthetic 2','Synthetic 3'})

    def test_cockpit_gestao_count_unchanged_by_module(self):
        self.seed_interventions()
        for table,columns in {
            'registros_longitudinais':'paciente_id INTEGER, data_registro DATE',
            'sessoes_assistenciais':'paciente_id INTEGER, status TEXT, data_realizacao DATE',
            'avaliacoes_clinicas':'paciente_id INTEGER, status TEXT, executado_em TIMESTAMP'}.items():
            self.db.execute(text('CREATE TABLE '+table+' ('+columns+')'))
        result=CockpitGestaoService.obter_atividade_assistencial(self.db,self.user)
        self.assertEqual(result['intervencoes'],3)
        self.assertEqual(result['registros_diarios'],0)

    def test_professional_cockpit_keeps_generic_source(self):
        self.seed_interventions()
        from types import SimpleNamespace
        from functools import partial
        from app.services.care_lines import care_line_registry
        from app.services.timeline import sources, professional_activity
        line=care_line_registry.get('NEURO')
        with patch.object(professional_activity, 'COLLECTORS', (partial(sources.generic_interventions, recent_activity=True),)):
            result=professional_activity.recent_neuro_activity(
                self.db,[SimpleNamespace(id=10,nome='Synthetic')],line,care_line_registry)
        # Still one event per patient; Cardio's newer event must not leak.
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['id'],2)
        self.assertEqual(result[0]['care_line'],'NEURO')
        self.assertEqual(result[0]['tipo_evento'],'INTERVENCAO')

    def test_session_keeps_five_recent_generic_without_module_filter(self):
        for model in (PTS,PTSObjetivo,AtividadeTerapeutica,AgendaCuidado,SessaoAssistencial):
            model.__table__.create(self.engine)
        self.db.add(PTS(id=1,paciente_id=10,modulo_id=1,data_inicio=DAY.date()))
        self.db.add(PTSObjetivo(id=1,pts_id=1,descricao='Synthetic'))
        self.db.add(AtividadeTerapeutica(id=1,nome='Synthetic'))
        self.db.add(AgendaCuidado(id=1,pts_id=1,objetivo_id=1,atividade_id=1,ocupacao_id=0,
            frequencia_semanal=1,duracao_minutos=30,data_inicio=DAY.date()))
        self.db.add(SessaoAssistencial(id=1,agenda_cuidado_id=1,paciente_id=10,numero_sessao=1,
            data_agendada=DAY.date(),duracao_minutos=30,status='AGENDADA'))
        for identity in range(1,7):
            self.db.add(Intervencao(id=identity,paciente_id=10,modulo_id=2 if identity%2 else 1,
                tipo='authored',descricao=str(identity),data_intervencao=DAY+timedelta(days=identity)))
        self.db.commit()
        result=AssistentialSessionService.get_session_details(self.db,1)
        self.assertEqual([r['id'] for r in result['intervencoes']],[6,5,4,3,2])
        self.assertEqual(result['resumo']['intervencoes'],5)
