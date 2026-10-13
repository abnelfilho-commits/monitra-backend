"""Canonical MH report: actual scoped persistence, official evidence and PDF."""
import os
import tempfile
import unittest
from contextlib import ExitStack
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from sqlalchemy import text, event
import test_checkin_bem_estar as foundation
import test_assessment_evidence as assessments
import test_planejamento_mental as planning_fixture
from app.services.report_engine import ReportService
from app.services.report_engine.reports.mental_v1 import MENTAL_V1
from app.services.report_engine.models import CanonicalReport
from app.services.care_lines.registry import MENTAL_HEALTH
from app.services.saude_mental import MentalHealthUnavailable
from app.services.clinical_reading import ClinicalReadingService


class DefinitionTests(unittest.TestCase):
    def test_registration_and_required_parameters(self):
        self.assertIs(ReportService().get_definition('CLN-MENTAL-001'), MENTAL_V1)
        self.assertEqual((MENTAL_V1.version, MENTAL_V1.domain, MENTAL_V1.care_line, MENTAL_V1.renderer),
                         ('1.0', 'CLINICAL', 'MENTAL_HEALTH', 'PDF'))
        self.assertTrue(MENTAL_HEALTH.supports('report'))
        for parameters, start in [({},date.today()), ({'contexto_assistencial_id':1},None)]:
            with self.assertRaises(ValueError):
                ReportService().create_context(report_code=MENTAL_V1.code, subject_id=1, requested_by=1,
                    module='MENTAL_HEALTH', period_start=start, period_end=date.today(), parameters=parameters)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class MentalReportTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.CheckinTests.tearDownClass.__func__)
    setUp = foundation.CheckinTests.setUp
    tearDown = foundation.CheckinTests.tearDown
    command_grant = foundation.CheckinTests.command_grant
    path = foundation.CheckinTests.path
    payload = foundation.CheckinTests.payload
    post = foundation.CheckinTests.post
    assessment = assessments.EvidenceHTTPTests.assessment

    def report(self, **changes):
        args = dict(report_code=MENTAL_V1.code, subject_id=self.payload()['paciente_id'], requested_by=self.actor,
                    module='MENTAL_HEALTH', period_start=date.today(), period_end=date.today(),
                    parameters={'contexto_assistencial_id':self.open}, db=self.db)
        args.update(changes)
        return ReportService().generate(**args)

    def test_partial_journey_real_pdf_and_read_only(self):
        statements = []
        def capture(conn, cursor, statement, *args): statements.append(statement.split()[0].upper())
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            with patch.object(self.db,'commit',side_effect=AssertionError('write')), patch.object(self.db,'flush',side_effect=AssertionError('write')):
                c = self.report()
            self.assertIsInstance(c.canonical_report, CanonicalReport)
            self.assertTrue(all(s == 'SELECT' for s in statements), statements)
        finally: event.remove(self.engine, 'before_cursor_execute', capture)
        with tempfile.TemporaryDirectory() as tmp:
            output = ReportService().render(c, str(Path(tmp)/'mental.pdf'))
            self.assertTrue(Path(output).read_bytes().startswith(b'%PDF'))
        self.assertEqual(len(c.canonical_report.sections),12)
        self.assertIn('Sem registros elegíveis',str(c.canonical_report.sections))
        self.assertEqual(c.subject['pessoa_id'],self.person)

    def test_official_reading_period_and_help_not_risk(self):
        payload = self.payload();payload['respostas']['pedido_ajuda']='SIM'
        self.assertEqual(self.post(payload).status_code,201)
        c = self.report()
        d = c.collected_data['MENTAL_HEALTH_PROVIDER']
        expected = ClinicalReadingService().get_contextual_reading(pessoa_id=self.person,contexto_assistencial_id=self.open,
            care_line='MENTAL_HEALTH',checkins=d['checkins'],assessments=d['assessments'],diagnoses=[],interventions=[])
        self.assertEqual(c.clinical_reading,expected)
        self.assertIsNone(c.clinical_reading.risk)
        self.assertIn('Solicitação de apoio autorreferida: Sim',str(c.canonical_report.sections))
        old = self.report(period_start=date.today()-timedelta(days=3),period_end=date.today()-timedelta(days=1))
        self.assertEqual(old.collected_data['MENTAL_HEALTH_PROVIDER']['checkins'],[])
        self.assertIsNone(old.clinical_reading.reference_date)

    def test_whatsapp_self_report_provenance_same_source(self):
        r = self.post();self.assertEqual(r.status_code,201)
        self.db.execute(text("UPDATE registro_proveniencias SET canal='WHATSAPP',modalidade='AUTORRELATO',registrador_profissional_id=NULL,registrador_pessoa_id=:p WHERE registro_id=:r"),dict(p=self.person,r=r.json()['id']))
        self.db.commit()
        c=self.report();rendered=str(c.canonical_report.sections)
        self.assertIn('WHATSAPP',rendered);self.assertIn('AUTORRELATO',rendered)
        self.assertIn(f'registrador: Pessoa respondente #{self.person}',rendered)
        self.assertIsNone(c.collected_data['MENTAL_HEALTH_PROVIDER']['checkins'][0].registrador_profissional_id)

    def test_all_instruments_preserve_persisted_results(self):
        expected={key:self.assessment(key) for key in ('phq9','gad7','cbi')}
        from app.services.clinical_engine.assessments.phq9_engine import PHQ9Engine
        from app.services.clinical_engine.assessments.gad7_engine import GAD7Engine
        from app.services.clinical_engine.assessments.cbi_engine import CBIEngine
        with ExitStack() as stack:
            for engine in (PHQ9Engine, GAD7Engine, CBIEngine):
                stack.enter_context(patch.object(engine, 'executar', side_effect=AssertionError('Must not rescore')))
            c=self.report()
        data=c.collected_data['MENTAL_HEALTH_PROVIDER']['assessments']
        for key in expected:self.assertEqual(data[key]['latest']['result'],expected[key]['resultado'])
        self.assertNotIn('score',data['cbi']['latest']['result'])
        self.assertIn('Burnout Pessoal',str(c.canonical_report.sections))
        from pypdf import PdfReader
        with tempfile.TemporaryDirectory() as tmp:
            output=ReportService().render(c,str(Path(tmp)/'assessments.pdf'))
            contents=' '.join(page.extract_text() for page in PdfReader(output).pages)
            for label in ('PHQ-9','GAD-7','CBI','Burnout Pessoal'):
                self.assertIn(label,contents)

    def test_checkins_and_assessments_other_context_and_dates_excluded(self):
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed));self.db.commit()
        foreign=self.post().json()['id']
        instruments={key:self.assessment(key) for key in ('phq9','gad7','cbi')}
        ids=[foreign]+[r['registro_id'] for r in instruments.values()]
        for identity in ids:
            self.db.execute(text('UPDATE registros_longitudinais SET contexto_assistencial_id=:c WHERE id=:r'),dict(c=self.closed,r=identity))
        self.db.execute(text("UPDATE avaliacoes_clinicas SET resultado=jsonb_set(resultado::jsonb,'{metadata,contexto_assistencial_id}',to_jsonb(CAST(:c AS integer)))::json WHERE registro_id=ANY(:ids)"),dict(c=self.closed,ids=ids))
        self.db.commit()
        own=self.post().json()['id']
        a=self.report().collected_data['MENTAL_HEALTH_PROVIDER']
        b=self.report(parameters={'contexto_assistencial_id':self.closed}).collected_data['MENTAL_HEALTH_PROVIDER']
        self.assertEqual([r.id for r in a['checkins']],[own])
        self.assertEqual([r.id for r in b['checkins']],[foreign])
        for key in instruments:
            self.assertEqual(a['assessments'][key]['applications'],[])
            self.assertEqual(b['assessments'][key]['latest']['application_id'],instruments[key]['id'])
        outside=self.report(parameters={'contexto_assistencial_id':self.closed},period_start=date.today()-timedelta(days=2),period_end=date.today()-timedelta(days=1))
        self.assertTrue(all(not g['applications'] for g in outside.collected_data['MENTAL_HEALTH_PROVIDER']['assessments'].values()))

    def test_denied_missing_admin_and_wrong_subject(self):
        for overrides in [dict(parameters={'contexto_assistencial_id':2147483647}),dict(subject_id=2147483647),
                          dict(parameters={'contexto_assistencial_id':self.contexts[1]}),dict(requested_by=self.platform_admin)]:
            with self.assertRaisesRegex(MentalHealthUnavailable,'REPORT_UNAVAILABLE'):self.report(**overrides)
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.db.commit()
        with self.assertRaisesRegex(MentalHealthUnavailable,'REPORT_UNAVAILABLE'):self.report()

    def test_inactive_line_and_no_patient_module_authority(self):
        self.db.execute(text('DELETE FROM paciente_modulos WHERE paciente_id=:p'),dict(p=self.payload()['paciente_id']));self.db.commit()
        self.assertEqual(self.report().care_line.code,'MENTAL_HEALTH')
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open));self.db.commit()
        with self.assertRaises(MentalHealthUnavailable):self.report()

    def test_two_contexts_same_person_diagnoses_and_interventions_isolated(self):
        patient=self.payload()['paciente_id']
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed))
        for context,label in [(self.open,'CONTEXT_A_ONLY'),(self.closed,'CONTEXT_B_ONLY')]:
            self.db.execute(text("INSERT INTO diagnosticos(paciente_id,modulo_id,contexto_assistencial_id,tipo,status,descricao_clinica,data_diagnostico,medico_nome) VALUES (:p,3,:c,'DIAGNOSTICO','ATIVO',:label,CURRENT_DATE,'Synthetic')"),dict(p=patient,c=context,label=label))
            self.db.execute(text("INSERT INTO intervencoes(paciente_id,modulo_id,contexto_assistencial_id,tipo,descricao,data_intervencao) VALUES (:p,3,:c,'Synthetic',:label,now())"),dict(p=patient,c=context,label=label))
        self.db.commit()
        a=self.report();b=self.report(parameters={'contexto_assistencial_id':self.closed})
        self.assertIn('CONTEXT_A_ONLY',str(a.canonical_report.sections))
        self.assertNotIn('CONTEXT_B_ONLY',str(a.canonical_report.sections))
        self.assertIn('CONTEXT_B_ONLY',str(b.canonical_report.sections))
        self.assertNotIn('CONTEXT_A_ONLY',str(b.canonical_report.sections))
        outside=self.report(period_start=date.today()-timedelta(days=2),period_end=date.today()-timedelta(days=1))
        self.assertNotIn('CONTEXT_A_ONLY',str(outside.canonical_report.sections))


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class PlanningReportTests(unittest.TestCase):
    schema_revision = "head"
    setUpClass = classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.CheckinTests.tearDownClass.__func__)
    tearDown = foundation.CheckinTests.tearDown
    command_grant = foundation.CheckinTests.command_grant
    path = foundation.CheckinTests.path
    setUp = planning_fixture.PlanningTests.setUp
    request = planning_fixture.PlanningTests.request
    create = planning_fixture.PlanningTests.create

    def test_plans_planning_sessions_period_and_ancestry(self):
        response=self.request('POST',self.suffix,self.payload)
        self.assertEqual(response.status_code,201,response.text)
        agenda=response.json()
        patient=self.db.scalar(text('SELECT paciente_id FROM pts WHERE id=:i'),dict(i=self.plan))
        self.db.execute(text("INSERT INTO sessoes_assistenciais(agenda_cuidado_id,paciente_id,profissional_id,numero_sessao,data_agendada,duracao_minutos,status) VALUES (:a,:p,:u,1,CURRENT_DATE,50,'AGENDADA')"),dict(a=agenda['id'],p=patient,u=self.executor));self.db.commit()
        # Planning fixture uses payload as a dictionary, report accepts subject explicitly.
        c=ReportService().generate(report_code=MENTAL_V1.code,subject_id=patient,requested_by=self.actor,module='MENTAL_HEALTH',
            period_start=date.today(),period_end=date.today()+timedelta(days=31),parameters={'contexto_assistencial_id':self.open},db=self.db)
        d=c.collected_data['MENTAL_HEALTH_PROVIDER']
        self.assertEqual([p.id for p in d['plans']],[self.plan]);self.assertEqual([p.id for p in d['planning']],[agenda['id']])
        self.assertEqual(len(d['sessions']),1)
        self.assertIn('status, objetivos e dados cadastrais são os atuais',str(c.canonical_report.sections))

    def test_foreign_plan_and_session_excluded_and_period_applied(self):
        agenda=self.request('POST',self.suffix,self.payload).json()
        patient=self.db.scalar(text('SELECT paciente_id FROM pts WHERE id=:i'),dict(i=self.plan))
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed))
        self.db.execute(text('UPDATE pts SET contexto_assistencial_id=:c WHERE id=:i'),dict(c=self.closed,i=self.plan))
        self.db.execute(text("INSERT INTO sessoes_assistenciais(agenda_cuidado_id,paciente_id,profissional_id,numero_sessao,data_agendada,duracao_minutos,status) VALUES (:a,:p,:u,1,CURRENT_DATE,50,'AGENDADA')"),dict(a=agenda['id'],p=patient,u=self.executor));self.db.commit()
        def generate(context,start,end):
            return ReportService().generate(report_code=MENTAL_V1.code,subject_id=patient,requested_by=self.actor,module='MENTAL_HEALTH',period_start=start,period_end=end,parameters={'contexto_assistencial_id':context},db=self.db).collected_data['MENTAL_HEALTH_PROVIDER']
        a=generate(self.open,date.today(),date.today()+timedelta(days=31))
        self.assertEqual((a['plans'],a['planning'],a['sessions']),([],[],[]))
        b=generate(self.closed,date.today(),date.today()+timedelta(days=31))
        self.assertEqual(len(b['plans']),1);self.assertEqual(len(b['planning']),1);self.assertEqual(len(b['sessions']),1)
        later=generate(self.closed,date.today()+timedelta(days=90),date.today()+timedelta(days=91))
        self.assertEqual(later['planning'],[]);self.assertEqual(later['sessions'],[])
