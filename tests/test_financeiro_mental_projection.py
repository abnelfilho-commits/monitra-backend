"""Focused institutional MH eligibility tests using the existing economic fixture."""
import os
import unittest
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import text
import test_financeiro_institutional_projection as foundation


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class MentalProjectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): foundation.InstitutionalPostgresTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): foundation.InstitutionalPostgresTests.tearDownClass.__func__(cls)
    def setUp(self): foundation.InstitutionalPostgresTests.setUp(self)
    def tearDown(self): foundation.InstitutionalPostgresTests.tearDown(self)
    session = foundation.InstitutionalPostgresTests.session
    request = foundation.InstitutionalPostgresTests.request
    institution_request = foundation.InstitutionalPostgresTests.institution_request
    run_preview = foundation.InstitutionalPostgresTests.run_preview

    def contextualize(self, *, institution=None, line_active=True, module=3):
        institution = institution or self.owner
        with self.engine.begin() as c:
            link = c.execute(text("SELECT id FROM paciente_instituicoes WHERE paciente_id=:p AND instituicao_id=:i"),dict(p=self.patient,i=institution)).scalar()
            if link is None:
                link = c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'BENEFICIARIO',:d) RETURNING id"),dict(p=self.patient,i=institution,d=self.today)).scalar()
            context = c.execute(text("INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,criado_por_usuario_id) VALUES (:v,:p,:i,:d,:u) RETURNING id"),dict(v=link,p=self.patient,i=institution,d=self.today,u=self.actor)).scalar()
            c.execute(text("INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,:m,:a)"),dict(c=context,m=module,a=line_active))
            c.execute(text('UPDATE pts SET contexto_assistencial_id=:c,modulo_id=:m WHERE paciente_id=:p'),dict(c=context,m=module,p=self.patient))
        return context

    def assert_excluded(self):
        result=self.run_preview(modulo_id=3)
        self.assertEqual(result.resumo.pacientes_economicos,1)
        self.assertEqual(result.resumo.quantidade_considerada,0)
        self.assertEqual(result.detalhes,())
        self.assertEqual(result.pacientes[0].agendas_sem_sessoes_elegiveis,())

    def test_valid_context_uses_same_economic_resolution_and_status_period(self):
        neuro=self.run_preview()
        self.contextualize()
        mental=self.run_preview(modulo_id=3)
        self.assertEqual(mental.detalhes[0].item,neuro.detalhes[0].item)
        self.assertEqual(mental.detalhes[0].evidencia,neuro.detalhes[0].evidencia)
        self.assertEqual(mental.detalhes[0].modulo_id,3)
        self.session(self.start+timedelta(days=1),'CONFIRMADA')
        self.session(self.start+timedelta(days=2),'REALIZADA')
        self.session(self.end+timedelta(days=1))
        result=self.run_preview(modulo_id=3)
        self.assertEqual(result.resumo.quantidade_considerada,2)
        self.assertEqual(result.resumo.subtotal_precificado,Decimal('20.20'))
        self.assertEqual(result.resumo.quantidade_considerada,len(result.detalhes))
        self.assertEqual(self.run_preview().detalhes,())

    def test_foreign_institution_excluded(self):
        self.contextualize(institution=self.other)
        self.assert_excluded()

    def test_inactive_mental_line_excluded(self):
        self.contextualize(line_active=False)
        self.assert_excluded()

    def test_mental_pts_without_context_excluded(self):
        with self.engine.begin() as c:
            c.execute(text('UPDATE pts SET modulo_id=3 WHERE paciente_id=:p'),dict(p=self.patient))
        self.assert_excluded()

    def test_gap_never_generates_financial_quantity(self):
        self.contextualize()
        with self.engine.begin() as c:
            c.execute(text('DELETE FROM sessoes_assistenciais WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
        result=self.run_preview(modulo_id=3)
        self.assertEqual(result.resumo.quantidade_considerada,0)
        self.assertIsNone(result.resumo.subtotal_precificado)
        self.assertEqual(result.pacientes[0].agendas_sem_sessoes_elegiveis,(self.agenda,))

    def test_session_patient_inconsistency_refused(self):
        self.contextualize()
        with self.engine.begin() as c:
            other=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Other') RETURNING id").scalar()
            c.execute(text('UPDATE sessoes_assistenciais SET paciente_id=:p WHERE agenda_cuidado_id=:a'),dict(p=other,a=self.agenda))
        with self.assertRaisesRegex(ValueError,'Ancestralidade'):
            self.run_preview(modulo_id=3)

    def test_objective_ancestry_inconsistency_refused_even_without_sessions(self):
        self.contextualize()
        with self.engine.begin() as c:
            pts=c.execute(text('INSERT INTO pts(paciente_id,modulo_id) VALUES (:p,1) RETURNING id'),dict(p=self.patient)).scalar()
            c.execute(text('UPDATE pts_objetivos SET pts_id=:p WHERE id=(SELECT objetivo_id FROM agenda_cuidados WHERE id=:a)'),dict(p=pts,a=self.agenda))
        with self.assertRaisesRegex(ValueError,'Ancestralidade'):
            self.run_preview(modulo_id=3)
        with self.engine.begin() as c:
            c.execute(text('DELETE FROM sessoes_assistenciais WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
        with self.assertRaisesRegex(ValueError,'Ancestralidade'):
            self.run_preview(modulo_id=3)

    def test_neuro_still_requires_null_context(self):
        self.assertEqual(self.run_preview().resumo.quantidade_considerada,1)
        self.contextualize(module=1)
        self.assertEqual(self.run_preview().detalhes,())
