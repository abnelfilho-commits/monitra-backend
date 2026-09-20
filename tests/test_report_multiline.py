"""Gate 4: institutional composition, temporal scope, isolation and shared PDF."""
import os
import unittest
from contextlib import ExitStack
from datetime import timedelta
from unittest.mock import patch
from pathlib import Path
from sqlalchemy import text, event
from fastapi import HTTPException
import test_cardio_longitudinal as fixture
from app.models import Diagnostico, Paciente, ProfissionalModulo
from app.services.report_engine.report_service import ReportService
from app.services.report_engine.reports.cln_001 import CLN_001
from app.services.report_engine.reports.cardio_v1 import CARDIO_V1
from app.services.clinical_reading import ClinicalReadingService
from app.routers.pacientes import baixar_relatorio_paciente_pdf

DAY = fixture.DAY

class ReportTests(unittest.TestCase):
    postgres_url = None
    def setUp(self):
        fixture.JourneyTests.setUp(self)
        if not self.postgres_url:
            class BoolOr:
                def __init__(self): self.value = None
                def step(self, value):
                    if value is not None: self.value = bool(self.value) or bool(value)
                def finalize(self): return self.value
            self.db.connection().connection.driver_connection.create_aggregate('BOOL_OR',1,BoolOr)
            # SQLite raw SQL dates are strings; emulate the PostgreSQL driver only.
            from datetime import date, datetime
            from app.services import neuro_engine
            original = neuro_engine.obter_registros_neuro_paciente
            def typed_rows(*args, **kwargs):
                rows = original(*args, **kwargs)
                for row in rows:
                    if isinstance(row.data, str): row.data = date.fromisoformat(row.data)
                    if isinstance(row.created_at, str): row.created_at = datetime.fromisoformat(row.created_at)
                return rows
            adapter = patch.object(neuro_engine, 'obter_registros_neuro_paciente', side_effect=typed_rows)
            adapter.start(); self.addCleanup(adapter.stop)
    tearDown = fixture.JourneyTests.tearDown
    record = fixture.JourneyTests.record

    def report(self, line='CARDIO', pid=3, start=DAY, end=DAY):
        service=ReportService()
        return service.generate(report_code=service.registry.for_care_line(line).code,
            subject_id=pid,requested_by=1,period_start=start,period_end=end,module=line,db=self.db)

    def diagnosis(self, mid, day, label, status='ATIVO'):
        self.db.add(Diagnostico(paciente_id=3,modulo_id=mid,data_diagnostico=day,
            descricao_clinica=label,status=status,medico_nome='Synthetic'))
        self.db.commit()

    def test_same_framework_explicit_composition(self):
        self.assertEqual(CLN_001.renderer,CARDIO_V1.renderer)
        self.assertEqual(len(CLN_001.knowledge_engines),9)
        self.assertEqual(CARDIO_V1.knowledge_engines,[])
        self.assertEqual(self.report('NEURO').care_line.code,'NEURO')
        self.assertEqual(self.report().care_line.code,'CARDIO')

    def test_cardio_never_executes_neuro_providers_or_knowledge(self):
        with ExitStack() as stack:
            for cls in CLN_001.knowledge_engines:
                stack.enter_context(patch.object(cls,'execute',side_effect=AssertionError('Neuro knowledge executed')))
            for cls in CLN_001.providers:
                if cls.code in ('PTS_PROVIDER','SESSION_PROVIDER','ASSESSMENT_PROVIDER'):
                    stack.enter_context(patch.object(cls,'collect',side_effect=AssertionError('Neuro provider executed')))
            c=self.report()
        self.assertNotIn('PTS_PROVIDER',c.collected_data)
        self.assertNotIn('knowledge_engines',c.audit)
        rendered=str(c.canonical_report.sections)
        for value in ('M-CHAT','Denver','PTS','SESSIONS'):
            self.assertNotIn(value,rendered)

    def test_period_and_current_reading_are_independent(self):
        old=self.record(day=DAY,glicemia_jejum=110)
        self.record(day=DAY+timedelta(days=1),glicemia_jejum=250,pressao_sistolica=180,peso=140)
        self.record(mid=1,day=DAY,glicemia_jejum=999)
        c=self.report()
        self.assertEqual([r['id'] for r in c.collected_data['TIMELINE_PROVIDER']],[old.id])
        self.assertEqual(c.clinical_reading,ClinicalReadingService().get_reading(self.db,3,'CARDIO'))
        self.assertEqual(c.clinical_reading.reference_date,DAY+timedelta(days=1))
        self.assertEqual(c.clinical_reading.risk,'critico')
        self.assertIsNone(c.clinical_reading.trend)
        self.assertEqual(len(c.collected_data['EVOLUTION_PROVIDER']),1)

    def test_active_prior_diagnoses_separate_and_line_scoped(self):
        self.diagnosis(2,DAY-timedelta(days=3),'CARDIO PRIOR')
        self.diagnosis(2,DAY,'CARDIO IN PERIOD')
        self.diagnosis(2,DAY+timedelta(days=1),'FUTURE')
        self.diagnosis(2,DAY-timedelta(days=3),'OLD CANCELLED','CANCELADO')
        self.diagnosis(1,DAY,'NEURO ONLY')
        cardio=self.report().collected_data['DIAGNOSIS_PROVIDER']['historico']
        self.assertEqual({r['descricao_clinica'] for r in cardio},{'CARDIO PRIOR','CARDIO IN PERIOD'})
        self.assertEqual({r['temporal_scope'] for r in cardio},{'ACTIVE_BEFORE_PERIOD','IN_PERIOD'})
        neuro=self.report('NEURO').collected_data['DIAGNOSIS_PROVIDER']['historico']
        self.assertEqual([r['descricao_clinica'] for r in neuro],['NEURO ONLY'])

    def test_creation_only_event_is_not_clinical_date(self):
        self.db.execute(text("INSERT INTO intervencoes_cardiometabolicas(id,modulo_id,paciente_id,tipo,descricao,created_at) VALUES(1,2,3,'Synthetic','Technical event',:day)"),{'day':str(DAY)+' 12:00:00'})
        self.db.commit()
        rows=self.report().collected_data['TIMELINE_PROVIDER']
        self.assertEqual(rows[0]['date_basis'],'CREATED_AT')
        self.assertIn('sem data clínica',str(self.report().canonical_report.sections))

    def test_no_data_is_unavailable(self):
        c=self.report(pid=5)
        self.assertIsNone(c.clinical_reading.risk)
        self.assertIsNone(c.clinical_reading.trend)
        self.assertIsNone(c.clinical_reading.reference_date)
        self.assertIn('Indisponível',str(c.canonical_report.sections))
        self.assertEqual(self.report('NEURO',pid=1).clinical_reading.risk,'sem_dados')

    def test_bmi_and_authorship_preserved(self):
        from app.models import Responsavel
        self.db.add(Responsavel(id=9,nome='Synthetic responsible',email='report@example.invalid',
            senha_hash='unused',clinica_id=1,ativo=True))
        self.db.commit()
        for i,origin in enumerate(('PROFISSIONAL','RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP')):
            record = self.record(day=DAY-timedelta(days=i),origin=origin,peso=80,**({'altura':2} if i==0 else {}))
            if i:
                record.criado_por_usuario_id = None
                record.criado_por_responsavel_id = 9
                self.db.commit()
        c=self.report(start=DAY-timedelta(days=2))
        self.assertEqual({e['origem'] for e in c.collected_data['TIMELINE_PROVIDER']},{'PROFISSIONAL','RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP'})
        self.assertEqual([e['actor']['namespace'] for e in c.collected_data['TIMELINE_PROVIDER']],
                         ['usuarios','responsaveis','responsaveis'])
        self.assertEqual([e['imc'] for e in c.collected_data['EVOLUTION_PROVIDER']],[None,None,20])
        self.db.query(Paciente).filter_by(id=3).update({'altura':1.9});self.db.commit()
        self.assertEqual(self.report(start=DAY-timedelta(days=2)).collected_data['EVOLUTION_PROVIDER'],c.collected_data['EVOLUTION_PROVIDER'])

    def test_endpoint_clinic_professional_ambiguity_and_period(self):
        for pid,line,status in ((4,'CARDIO',404),(3,None,409)):
            with self.assertRaises(HTTPException) as exc:
                baixar_relatorio_paciente_pdf(pid,line,DAY,DAY,self.db,self.user)
            self.assertEqual(exc.exception.status_code,status)
        with self.assertRaises(HTTPException) as exc:
            baixar_relatorio_paciente_pdf(3,'CARDIO',DAY,DAY-timedelta(days=1),self.db,self.user)
        self.assertEqual(exc.exception.status_code,422)
        self.db.query(ProfissionalModulo).filter_by(modulo_id=2).delete();self.db.commit()
        with self.assertRaises(HTTPException) as exc:
            baixar_relatorio_paciente_pdf(3,'CARDIO',DAY,DAY,self.db,self.user)
        self.assertEqual(exc.exception.status_code,403)

    def test_cardio_query_count_does_not_grow_per_record(self):
        def count():
            calls=[]
            def log(*args): calls.append(1)
            event.listen(self.engine,'before_cursor_execute',log)
            try: self.report()
            finally: event.remove(self.engine,'before_cursor_execute',log)
            return len(calls)
        self.record(glicemia_jejum=110)
        before=count()
        for i in range(20): self.record(glicemia_jejum=110)
        self.assertEqual(count(),before)

    def seed_neuro(self):
        from app.models import (PTS, PTSObjetivo, AgendaCuidado, SessaoAssistencial,
            OcupacaoProfissional, AtividadeTerapeutica, AvaliacaoClinica)
        self.db.add(OcupacaoProfissional(id=1,nome='Synthetic',ativo=True))
        self.db.add(AtividadeTerapeutica(id=1,nome='Synthetic Neuro',modulo_id=1,ativo=True))
        self.db.flush()
        for mid in (1,2):
            plan=PTS(paciente_id=3,modulo_id=mid,data_inicio=DAY-timedelta(days=10),status='ATIVO')
            self.db.add(plan);self.db.flush()
            goal=PTSObjetivo(pts_id=plan.id,descricao='Synthetic goal '+str(mid),status='ABERTO')
            self.db.add(goal);self.db.flush()
            agenda=AgendaCuidado(pts_id=plan.id,objetivo_id=goal.id,atividade_id=1,ocupacao_id=1,
                profissional_id=1,frequencia_semanal=1,quantidade_sessoes=3,duracao_minutos=30,
                data_inicio=DAY-timedelta(days=5),status='ATIVO')
            self.db.add(agenda);self.db.flush()
            for i,day in enumerate((DAY-timedelta(days=1),DAY,DAY+timedelta(days=1))):
                self.db.add(SessaoAssistencial(agenda_cuidado_id=agenda.id,paciente_id=3,profissional_id=1,
                    numero_sessao=i+1,data_agendada=day,data_realizacao=day,status='REALIZADA',duracao_minutos=30))
        for instrument in ('M-CHAT','DENVER'):
            record=self.record(mid=1)
            self.db.add(AvaliacaoClinica(registro_id=record.id,paciente_id=3,modulo_id=1,
                instrumento=instrument,score=1,classificacao='Synthetic',interpretacao='Synthetic assessment'))
        self.db.commit()

    def test_neuro_keeps_pts_assessments_sessions_in_period(self):
        self.seed_neuro()
        c=self.report('NEURO')
        self.assertEqual(c.collected_data['PTS_PROVIDER']['total_pts'],1)
        self.assertEqual(c.collected_data['PTS_PROVIDER']['pts_ativo']['modulo_id'],1)
        self.assertEqual(c.collected_data['SESSION_PROVIDER']['total_sessoes'],1)
        self.assertEqual({a['instrumento'] for a in c.collected_data['ASSESSMENT_PROVIDER']},{'M-CHAT','DENVER'})
        self.assertEqual(len(c.audit['knowledge_engines']),9)
        cardio=self.report()
        self.assertNotIn('ASSESSMENT_PROVIDER',cardio.collected_data)
        self.assertNotIn('Synthetic assessment',str(cardio.canonical_report.sections))

    def test_legacy_diagnosis_without_line_never_falls_back(self):
        self.assertFalse(Diagnostico.__table__.c.modulo_id.nullable)
        if self.postgres_url:
            # Deliberately degraded synthetic schema to exercise legacy read exclusion.
            self.db.execute(text('ALTER TABLE diagnosticos ALTER COLUMN modulo_id DROP NOT NULL'))
            self.db.commit()
            self.diagnosis(None,DAY,'UNASSIGNED MUST NEVER APPEAR')
            for line in ('NEURO','CARDIO'):
                c=self.report(line)
                self.assertNotIn('UNASSIGNED MUST NEVER APPEAR',str(c.canonical_report.sections))

    def test_shared_pdf_renderer_both_lines(self):
        import tempfile
        self.record(glicemia_jejum=180,peso=80,altura=2)
        self.seed_neuro()
        self.diagnosis(1,DAY,'NEURO ONLY')
        self.diagnosis(2,DAY,'CARDIO ONLY <complemento> & texto')
        folder=Path(os.environ.get('GATE4_PDF_DIR') or tempfile.mkdtemp(prefix='gate4-pdf-'))
        folder.mkdir(parents=True,exist_ok=True)
        for line in ('NEURO','CARDIO'):
            c=self.report(line)
            output=folder/(line.lower()+'.pdf')
            ReportService().render(c,str(output))
            self.assertTrue(output.read_bytes().startswith(b'%PDF'))

@unittest.skipUnless(os.environ.get('CARDIO_GATE4_POSTGRES_URL'),'Disposable PostgreSQL not configured')
class PostgresReportTests(ReportTests):
    postgres_url=os.environ.get('CARDIO_GATE4_POSTGRES_URL')
