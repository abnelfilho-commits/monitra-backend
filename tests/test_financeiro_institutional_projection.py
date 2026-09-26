"""Gate C: batch population and exact drill-down in disposable PostgreSQL 18."""
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch

from sqlalchemy import event, text
from sqlalchemy.orm import Session

import test_financeiro_projection as individual
from app.models.financeiro import PacienteContrato, ServicoEconomico
from app.schemas.financeiro import InstitutionalPreviewRequest
from app.services.financeiro.calculator import summarize
from app.services.financeiro.institutional_projection import InstitutionalProjectionService


class InstitutionalContractTests(unittest.TestCase):
    def test_explicit_context_horizon_and_no_extra_inference(self):
        payload = dict(instituicao_id=1, contrato_id=2, modulo_id=1,
                       data_inicio='2030-01-01', data_fim='2030-12-31')
        for key in payload:
            with self.assertRaises(ValueError):
                InstitutionalPreviewRequest(**{k: v for k, v in payload.items() if k != key})
        for extra in (dict(clinica_id=1), dict(paciente_id=1), dict(data_fim='2029-12-31')):
            with self.assertRaises(ValueError):
                InstitutionalPreviewRequest(**dict(payload, **extra))


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Requires disposable PostgreSQL 18')
class InstitutionalPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): individual.ProjectionPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls): individual.ProjectionPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        individual.ProjectionPostgresTests.setUp(self)
        self.institutional = InstitutionalProjectionService()

    def tearDown(self): individual.ProjectionPostgresTests.tearDown(self)

    session = individual.ProjectionPostgresTests.session
    new_version = individual.ProjectionPostgresTests.new_version
    request = individual.ProjectionPostgresTests.request

    def institution_request(self, **changes):
        payload = self.request()
        payload.pop('paciente_id')
        return dict(payload, modulo_id=1, **changes)

    def run_preview(self, batch_size=200, **changes):
        payload = dict(self.institution_request(), **changes)
        return self.institutional.run(self.engine, payload, batch_size=batch_size)

    def add_patient(self, *, linked=True, care=True, mapped=True, start=None, end=None):
        with self.engine.begin() as c:
            pid = c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar()
            agenda = None
            if care:
                pts = c.execute(text('INSERT INTO pts(paciente_id,modulo_id) VALUES (:p,1) RETURNING id'), dict(p=pid)).scalar()
                obj = c.execute(text("INSERT INTO pts_objetivos(pts_id,descricao) VALUES (:p,'Synthetic') RETURNING id"), dict(p=pts)).scalar()
                agenda = c.execute(text('INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio) SELECT :pts,:obj,atividade_id,ocupacao_id,2,45,data_inicio FROM agenda_cuidados WHERE id=:a RETURNING id'), dict(pts=pts,obj=obj,a=self.agenda)).scalar()
                if mapped:
                    c.execute(text('INSERT INTO mapeamentos_agenda_servico(agenda_cuidado_id,servico_id) VALUES (:a,:s)'), dict(a=agenda,s=self.sid))
            if linked:
                c.execute(text('INSERT INTO paciente_contratos(paciente_id,contrato_id,inicio,fim) VALUES (:p,:c,:start,:end)'), dict(p=pid,c=self.cid,start=start or self.today,end=end))
        if care:
            self.session(self.start, agenda=agenda, patient=pid)
        return pid, agenda

    def test_composition_matches_individuals_exactly(self):
        second, _ = self.add_patient(mapped=False)
        third, _ = self.add_patient(care=False)
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            tx = c.begin()
            c.exec_driver_sql('SET TRANSACTION READ ONLY')
            try:
                with Session(bind=c) as db:
                    result = self.institutional.preview(db,self.institution_request(),batch_size=2)
                    for pid in (self.patient, second, third):
                        expected = self.projection.preview(db,self.request(paciente_id=pid))
                        self.assertEqual(tuple(d.item for d in result.drill_down(paciente_id=pid)),expected.itens)
                    self.assertTrue(tx.is_active)
            finally:
                tx.rollback()
        self.assertEqual(result.resumo.pacientes_economicos,3)
        self.assertEqual(result.resumo.pacientes_sem_sessoes,1)
        self.assertEqual(result.resumo.pacientes_somente_pendentes,1)
        self.assertEqual(result.resumo.subtotal_precificado,Decimal('10.10'))
        self.assertEqual(result.resumo.cobertura_percentual,Decimal('50'))

    def test_every_dimension_reconciles_to_same_result(self):
        self.add_patient(mapped=False)
        self.session(date(self.start.year,2,1))
        self.new_version(date(self.start.year,2,1),'20.20')
        result = self.run_preview()
        groups = [(p, dict(paciente_id=p.paciente_id)) for p in result.pacientes]
        groups += [(m,dict(mes=m.mes)) for m in result.totais_por_mes]
        groups += [(s,dict(servico_id=s.servico_id)) for s in result.totais_por_servico]
        groups += [(p,dict(pendencia=p.codigo)) for p in result.pendencias]
        groups += [(result.resumo,dict(modulo_id=1,contrato_id=self.cid))]
        for aggregate, filters in groups:
            actual = summarize(d.item for d in result.drill_down(**filters))
            for key,value in actual.items(): self.assertEqual(getattr(aggregate,key),value)
        self.assertNotIn('detalhes',result.executive())
        self.assertEqual(len(result.drill_down(tabela_id=self.tid,versao_id=self.vid)),1)
        self.assertEqual(result.drill_down(modulo_id=2),())
        self.assertEqual(result.resumo.completude,'COM_PENDENCIAS')

    def test_population_from_contract_not_pts_or_institutional_link(self):
        excluded,_ = self.add_patient(linked=False)
        included,_ = self.add_patient(care=False)
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM paciente_instituicoes').scalar(),0)
        result=self.run_preview()
        self.assertEqual({p.paciente_id for p in result.pacientes},{self.patient,included})
        self.assertNotIn(excluded,{d.paciente_id for d in result.detalhes})

    def test_link_intersection_inclusive_and_dedup(self):
        excluded,_ = self.add_patient(start=self.end+timedelta(days=1))
        boundary,_ = self.add_patient(start=self.end,end=self.end)
        with self.engine.begin() as c:
            c.execute(text('UPDATE paciente_contratos SET fim=:d WHERE paciente_id=:p'),dict(d=self.start,p=self.patient))
            c.execute(text('INSERT INTO paciente_contratos(paciente_id,contrato_id,inicio) VALUES (:p,:c,:d)'),dict(p=self.patient,c=self.cid,d=self.start+timedelta(days=2)))
        self.session(self.start+timedelta(days=1))
        result=self.run_preview()
        self.assertEqual({p.paciente_id for p in result.pacientes},{self.patient,boundary})
        self.assertNotIn(excluded,{p.paciente_id for p in result.pacientes})
        gap=result.drill_down(paciente_id=self.patient)[1]
        self.assertEqual(gap.item.pendencia,'NO_CONTRACT')
        self.assertEqual(len(gap.evidencia.vinculos),2)

    def test_invalid_economic_context_fails_not_empty_preview(self):
        for changes in (dict(instituicao_id=self.other),dict(contrato_id=99999)):
            with self.assertRaises(ValueError):self.run_preview(**changes)

    def test_module_explicit_and_no_mental_health_placeholder(self):
        for module in (2,3,999):
            with self.assertRaises(ValueError):self.run_preview(modulo_id=module)
        with self.engine.begin() as c:
            c.execute(text('UPDATE pts SET modulo_id=NULL WHERE paciente_id=:p'),dict(p=self.patient))
        result=self.run_preview()
        self.assertEqual(result.resumo.pacientes_economicos,1)
        self.assertEqual(result.resumo.pacientes_sem_sessoes,1)
        self.assertEqual(result.detalhes,())

    def test_empty_population_and_absent_price_are_not_zero(self):
        with self.engine.begin() as c:c.exec_driver_sql('DELETE FROM paciente_contratos')
        result=self.run_preview()
        self.assertEqual(result.resumo.pacientes_economicos,0)
        self.assertIsNone(result.resumo.subtotal_precificado)
        self.assertIsNone(result.resumo.cobertura_percentual)
        self.assertEqual(result.resumo.completude,'SEM_SESSOES')

    def test_new_price_missing_never_falls_back_and_evidence_preserved(self):
        self.new_version(self.start)
        result=self.run_preview()
        detail=result.detalhes[0]
        self.assertEqual(detail.item.pendencia,'NO_PRICE')
        self.assertIsNone(result.resumo.subtotal_precificado)
        self.assertEqual(detail.evidencia.servico_duracao_minutos,45)
        self.assertEqual(detail.evidencia.duracao_agenda,45)
        self.assertEqual(result.resumo.cobertura_percentual,0)

    def test_known_zero_price_remains_calculated(self):
        self.new_version(self.start,'0')
        result=self.run_preview()
        self.assertEqual(result.resumo.subtotal_precificado,Decimal('0.00'))
        self.assertEqual(result.resumo.completude,'PRECIFICADO')

    def test_batch_reads_constant_per_batch_and_output_independent_of_batch(self):
        self.add_patient();self.add_patient();self.add_patient()
        statements=[]
        def capture(c,cursor,statement,*args):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            large=self.run_preview(batch_size=100)
            count=len(statements);statements.clear()
            small=self.run_preview(batch_size=1)
            self.assertEqual(len(statements)-count,3*8)
        finally:event.remove(self.engine,'before_cursor_execute',capture)
        self.assertEqual(large,small)
        for value in (0,-1,True,1.5):
            with self.assertRaises(ValueError):self.run_preview(batch_size=value)

    def test_immutable_details_work_after_transaction_closed(self):
        result=self.run_preview()
        with self.assertRaises(ValueError):result.detalhes[0].item.subtotal=Decimal('900')
        with self.assertRaises(ValueError):result.detalhes[0].evidencia.vinculos[0].inicio=self.end
        with patch.object(self.engine,'connect',side_effect=AssertionError('No SQL for navigation')):
            self.assertEqual(len(result.drill_down(paciente_id=self.patient)),1)
            self.assertEqual(result.executive()['resumo']['quantidade_precificada'],1)

    def test_concurrent_change_snapshot_then_new_preview(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            tx=c.begin();c.exec_driver_sql('SET TRANSACTION READ ONLY')
            try:
                with Session(bind=c) as db:
                    before=self.institutional.preview(db,self.institution_request())
                    with self.engine.begin() as other:
                        other.execute(text('DELETE FROM mapeamentos_agenda_servico WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
                    after=self.institutional.preview(db,self.institution_request())
                    self.assertEqual(before,after)
            finally:tx.rollback()
        new=self.run_preview()
        self.assertEqual(before.resumo.subtotal_precificado,Decimal('10.10'))
        self.assertIsNone(new.resumo.subtotal_precificado)
        self.assertEqual(new.detalhes[0].item.pendencia,'NO_ECONOMIC_SERVICE_MAPPING')

    def test_readonly_and_clean_session_mandatory(self):
        with Session(self.engine) as db:
            with self.assertRaises(ValueError):self.institutional.preview(db,self.institution_request())
            db.add(ServicoEconomico(codigo='NEVER_WRITTEN'))
            with self.assertRaises(ValueError):self.institutional.preview(db,self.institution_request())

    def test_no_writes_all_rows_and_no_commit(self):
        def snapshot():
            with self.engine.connect() as c:
                tables=c.exec_driver_sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").scalars().all()
                return {t:c.exec_driver_sql('SELECT row_to_json(x)::text FROM public.'+t+' x ORDER BY 1').scalars().all() for t in tables}
        before=snapshot();sql=[];commits=[]
        def capture(c,cursor,statement,*args):sql.append(statement.strip().split()[0].upper())
        def commit(c):commits.append(True)
        event.listen(self.engine,'before_cursor_execute',capture);event.listen(self.engine,'commit',commit)
        try:self.run_preview()
        finally:
            event.remove(self.engine,'before_cursor_execute',capture);event.remove(self.engine,'commit',commit)
        self.assertTrue(set(sql)<= {'SET','SHOW','SELECT'})
        self.assertEqual(commits,[])
        self.assertEqual(snapshot(),before)

    def test_failure_in_later_batch_returns_no_partial_result(self):
        other,agenda=self.add_patient()
        with self.engine.begin() as c:
            c.execute(text('UPDATE sessoes_assistenciais SET paciente_id=:p WHERE agenda_cuidado_id=:a'),dict(p=self.patient,a=agenda))
        with self.assertRaises(ValueError):self.run_preview(batch_size=1)
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT 1').scalar(),1)
