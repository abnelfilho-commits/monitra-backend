"""Gate B: pure mathematics and a real disposable PostgreSQL 18 snapshot."""
import os
import unittest
from datetime import date, timedelta
from decimal import Decimal, localcontext
from unittest.mock import patch

from sqlalchemy import text, event
from sqlalchemy.orm import Session
from app.models.financeiro import (PrecoServico, TabelaPrecoVersao, ServicoEconomico,
                                  MapeamentoAgendaServico, PacienteContrato)
from app.schemas.financeiro import PreviewRequest
from app.services.financeiro.calculator import subtotal
from app.services.financeiro.projection import FinancialProjectionService
import test_financeiro_postgres as foundation


class ProjectionMathTests(unittest.TestCase):
    def test_decimal_half_up_and_zero(self):
        self.assertEqual(subtotal(Decimal('1.005')), Decimal('1.01'))
        self.assertEqual(subtotal(Decimal('2.675')), Decimal('2.68'))
        self.assertEqual(subtotal(Decimal('0')), Decimal('0.00'))
        self.assertEqual(subtotal(Decimal('0.10'), 3), Decimal('0.30'))
        with localcontext() as ctx:
            ctx.prec = 3
            self.assertEqual(subtotal(Decimal('999999999999.99'), 3), Decimal('2999999999999.97'))

    def test_no_float_negative_nonfinite_or_fractional_quantity(self):
        for value in (0.1, '1.00', Decimal('-1'), Decimal('NaN'), Decimal('Infinity')):
            with self.assertRaises(ValueError): subtotal(value)
        for qty in (0, -1, 1.5, True):
            with self.assertRaises(ValueError): subtotal(Decimal('1'), qty)

    def test_explicit_context_and_horizon(self):
        data=dict(paciente_id=1, contrato_id=1, instituicao_id=1,
                  data_inicio=date(2030,1,1), data_fim=date(2030,1,31))
        for key in data:
            with self.assertRaises(ValueError): PreviewRequest(**{k:v for k,v in data.items() if k!=key})
        with self.assertRaises(ValueError): PreviewRequest(**dict(data,data_fim=date(2029,1,1)))
        with self.assertRaises(ValueError): PreviewRequest(**dict(data,ator_usuario_id=1))


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Requires disposable PostgreSQL 18')
class ProjectionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): foundation.FinancialPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls): foundation.FinancialPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        foundation.FinancialPostgresTests.setUp(self)
        self.start=date(self.today.year+1,1,1)
        self.end=date(self.start.year,12,31)
        self.projection=FinancialProjectionService()
        self.service.create(self.db,PrecoServico,dict(versao_id=self.vid,servico_id=self.sid,valor_base='10.10'))
        self.service.publish_version(self.db,self.vid,actor_id=self.actor)
        self.service.publish_contract(self.db,self.cid,actor_id=self.actor)
        self.service.create(self.db,PacienteContrato,dict(paciente_id=self.patient,contrato_id=self.cid,inicio=self.today))
        self.service.create(self.db,MapeamentoAgendaServico,dict(agenda_cuidado_id=self.agenda,servico_id=self.sid))
        self.db.commit()
        with self.engine.begin() as c:
            # The Gate A fixture uses a test module; make the synthetic PTS explicitly Neuro.
            c.exec_driver_sql("INSERT INTO modulos_clinicos(id,nome,slug) VALUES (1,'Neuro','neurodesenvolvimento') ON CONFLICT(id) DO UPDATE SET slug='neurodesenvolvimento'")
            c.execute(text('UPDATE pts SET modulo_id=1 WHERE paciente_id=:p'),dict(p=self.patient))
        self.session(self.start)

    def tearDown(self): foundation.FinancialPostgresTests.tearDown(self)

    def request(self,**changes):
        return dict(dict(paciente_id=self.patient,contrato_id=self.cid,instituicao_id=self.owner,
                         data_inicio=self.start,data_fim=self.end),**changes)

    def session(self,day,status='AGENDADA',agenda=None,patient=None,duration=45):
        with self.engine.begin() as c:
            return c.execute(text("INSERT INTO sessoes_assistenciais(agenda_cuidado_id,paciente_id,numero_sessao,data_agendada,duracao_minutos,status) SELECT :a,:p,coalesce(max(numero_sessao),0)+1,:d,:duration,:status FROM sessoes_assistenciais WHERE agenda_cuidado_id=:a RETURNING id"),
                dict(a=agenda or self.agenda,p=patient or self.patient,d=day,duration=duration,status=status)).scalar()

    def preview(self,**changes):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            tx=c.begin();c.exec_driver_sql('SET TRANSACTION READ ONLY')
            try:
                with Session(bind=c) as db:
                    result=self.projection.preview(db,self.request(**changes))
                    self.assertTrue(tx.is_active)
                    self.assertEqual(c.exec_driver_sql('SHOW transaction_read_only').scalar(),'on')
                    return result
            finally:tx.rollback()

    def new_version(self,day,price=None,service=None,number=2,publish=True):
        version=self.service.create(self.db,TabelaPrecoVersao,dict(tabela_id=self.tid,numero=number,vigente_desde=day))
        vid=version.id
        if price is not None:
            self.service.create(self.db,PrecoServico,dict(versao_id=vid,servico_id=service or self.sid,valor_base=price))
        if publish:self.service.publish_version(self.db,vid,actor_id=self.actor)
        self.db.commit();return vid

    def assert_pending(self,result,code):
        self.assertEqual(result.itens[0].estado,'PENDENTE')
        self.assertEqual(result.itens[0].pendencia,code)
        self.assertIsNone(result.itens[0].subtotal)
        self.assertIsNone(result.itens[0].preco_unitario)
        self.assertIsNone(result.subtotal_precificado)

    def test_base_price_quantities_provenance_and_determinism(self):
        self.session(self.start+timedelta(days=1),'CONFIRMADA')
        result=self.preview()
        self.assertEqual(result.subtotal_precificado,Decimal('20.20'))
        self.assertEqual(result.cobertura.sessoes_precificadas,2)
        self.assertEqual([i.quantidade for i in result.itens],[1,1])
        self.assertEqual(result.itens[0].tabela_id,self.tid)
        self.assertEqual(result.itens[0].versao_id,self.vid)
        self.assertIsNotNone(result.itens[0].preco_id)
        self.assertEqual(result.model_dump_json(),self.preview().model_dump_json())

    def test_price_change_boundary_monthly_and_annual(self):
        feb=date(self.start.year,2,1)
        self.session(feb-timedelta(days=1));self.session(feb)
        self.session(date(self.start.year,12,31))
        new=self.new_version(feb,'20.20')
        result=self.preview()
        self.assertEqual([i.versao_id for i in result.itens],[self.vid,self.vid,new,new])
        self.assertEqual(result.subtotal_precificado,Decimal('60.60'))
        self.assertEqual([(t.mes,t.subtotal_precificado) for t in result.totais_por_mes],
            [(f'{self.start.year}-01',Decimal('20.20')),(f'{self.start.year}-02',Decimal('20.20')),(f'{self.start.year}-12',Decimal('20.20'))])

    def test_missing_price_does_not_fallback_and_partial_result(self):
        day=self.start+timedelta(days=1);self.session(day);self.new_version(day)
        result=self.preview()
        self.assertEqual(result.subtotal_precificado,Decimal('10.10'))
        self.assertEqual(result.itens[1].pendencia,'NO_PRICE')
        self.assertIsNone(result.itens[1].subtotal)
        self.assertEqual(result.cobertura.sessoes_pendentes,1)
        self.assertEqual(result.cobertura.sessoes_mapeadas,2)

    def test_zero_price_is_calculated(self):
        self.new_version(self.start,'0')
        result=self.preview()
        self.assertEqual(result.itens[0].estado,'CALCULADO')
        self.assertEqual(result.subtotal_precificado,Decimal('0.00'))

    def test_absent_mapping(self):
        with self.engine.begin() as c:c.execute(text('DELETE FROM mapeamentos_agenda_servico WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
        result=self.preview();self.assert_pending(result,'NO_ECONOMIC_SERVICE_MAPPING')
        self.assertEqual(result.cobertura.sessoes_mapeadas,0)

    def test_incompatible_duration_or_inactive_service(self):
        with self.engine.begin() as c:c.execute(text('UPDATE sessoes_assistenciais SET duracao_minutos=30 WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
        self.assert_pending(self.preview(),'INCOMPATIBLE_ECONOMIC_SERVICE_MAPPING')
        with self.engine.begin() as c:
            c.execute(text('UPDATE sessoes_assistenciais SET duracao_minutos=45 WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
            c.execute(text('UPDATE servicos_economicos SET ativo=false WHERE id=:s'),dict(s=self.sid))
        self.assert_pending(self.preview(),'INCOMPATIBLE_ECONOMIC_SERVICE_MAPPING')

    def test_no_version_at_economic_date(self):
        # Version begins today; valid past sessions and explicitly selected historical contract still need a price.
        from app.models.financeiro import ContratoFinanceiro
        past=self.today-timedelta(days=10)
        contract=self.service.create(self.db,ContratoFinanceiro,dict(pagador_instituicao_id=self.owner,codigo='PAST',edicao=1,tabela_preco_id=self.tid,inicio=past))
        cid=contract.id;self.service.publish_contract(self.db,cid,actor_id=self.actor)
        self.service.create(self.db,PacienteContrato,dict(paciente_id=self.patient,contrato_id=cid,inicio=past));self.db.commit()
        self.session(past)
        self.assert_pending(self.preview(contrato_id=cid,data_inicio=past,data_fim=past),'NO_APPLICABLE_PRICE_TABLE_VERSION')

    def test_missing_or_foreign_contract_and_institution(self):
        for changes in (dict(contrato_id=999999),dict(instituicao_id=self.other),dict(instituicao_id=999999)):
            result=self.preview(**changes);self.assert_pending(result,'NO_CONTRACT')
            self.assertIsNone(result.itens[0].tabela_id)
        with self.engine.begin() as c:c.execute(text('DELETE FROM paciente_contratos WHERE paciente_id=:p'),dict(p=self.patient))
        self.assert_pending(self.preview(),'NO_CONTRACT')

    def test_link_period_is_inclusive(self):
        with self.engine.begin() as c:c.execute(text('UPDATE paciente_contratos SET inicio=:d,fim=:d WHERE paciente_id=:p'),dict(d=self.start,p=self.patient))
        self.session(self.start+timedelta(days=1))
        result=self.preview()
        self.assertEqual(result.itens[0].estado,'CALCULADO')
        self.assertEqual(result.itens[1].pendencia,'NO_CONTRACT')

    def test_no_frequency_extrapolation_and_empty_coverage(self):
        with self.engine.begin() as c:
            c.execute(text('UPDATE agenda_cuidados SET frequencia_semanal=7,quantidade_sessoes=999 WHERE id=:a'),dict(a=self.agenda))
            c.execute(text("UPDATE sessoes_assistenciais SET status='REALIZADA' WHERE agenda_cuidado_id=:a"),dict(a=self.agenda))
        result=self.preview()
        self.assertEqual(result.itens,())
        self.assertIsNone(result.subtotal_precificado)
        self.assertEqual(result.cobertura.aplicabilidade,'N/A')
        self.assertEqual(result.cobertura.agendas_sem_sessoes_elegiveis,(self.agenda,))

    def test_only_eligible_status_and_requested_horizon(self):
        for state in ('REALIZADA','REAGENDADA','CANCELADA','EM_ANDAMENTO','FALTOU'):
            self.session(self.start,state)
        self.session(self.start-timedelta(days=1));self.session(self.end+timedelta(days=1))
        self.assertEqual(self.preview().cobertura.sessoes_elegiveis,1)

    def test_readonly_session_required_and_dirty_session_refused(self):
        with Session(self.engine) as db:
            with self.assertRaises(ValueError):self.projection.preview(db,self.request())
            db.add(ServicoEconomico(codigo='NEVER_WRITTEN'))
            with self.assertRaises(ValueError):self.projection.preview(db,self.request())
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM servicos_economicos WHERE codigo='NEVER_WRITTEN'").scalar(),0)

    def test_no_writes_or_commit_and_all_rows_preserved(self):
        def snapshot():
            with self.engine.connect() as c:
                tables=c.exec_driver_sql("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").scalars().all()
                return {t:c.exec_driver_sql('SELECT row_to_json(x)::text FROM public.'+t+' x ORDER BY 1').scalars().all() for t in tables}
        before=snapshot();sql=[]
        def capture(conn,cursor,statement,parameters,context,many):sql.append(statement.strip().split()[0].upper())
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            with patch.object(Session,'commit',side_effect=AssertionError('No commit')):
                self.preview()
        finally:event.remove(self.engine,'before_cursor_execute',capture)
        self.assertTrue(set(sql)<= {'SET','SHOW','SELECT'})
        self.assertEqual(before,snapshot())

    def test_neuro_only_and_no_clinical_line_inference(self):
        with self.engine.begin() as c:c.execute(text('UPDATE pts SET modulo_id=NULL WHERE paciente_id=:p'),dict(p=self.patient))
        self.assertEqual(self.preview().itens,())
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO modulos_clinicos(id,nome,slug) VALUES (2,'Cardio','cardiometabolico') ON CONFLICT(id) DO NOTHING")
            c.execute(text('UPDATE pts SET modulo_id=2 WHERE paciente_id=:p'),dict(p=self.patient))
        self.assertEqual(self.preview().itens,())

    def test_multiple_services_and_mapping_compatibility(self):
        second=self.service.create(self.db,ServicoEconomico,dict(codigo='OTHER',descricao='Other',ocupacao_id=self.occupation,duracao_minutos=45));sid=second.id
        self.db.commit()
        with self.engine.begin() as c:
            agenda=c.execute(text('INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio) SELECT pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio FROM agenda_cuidados WHERE id=:a RETURNING id'),dict(a=self.agenda)).scalar()
        self.service.create(self.db,MapeamentoAgendaServico,dict(agenda_cuidado_id=agenda,servico_id=sid))
        version=self.service.create(self.db,TabelaPrecoVersao,dict(tabela_id=self.tid,numero=2,vigente_desde=self.start))
        for service,amount in ((self.sid,'10.10'),(sid,'30.30')):
            self.service.create(self.db,PrecoServico,dict(versao_id=version.id,servico_id=service,valor_base=amount))
        self.service.publish_version(self.db,version.id,actor_id=self.actor);self.db.commit()
        self.session(self.start,agenda=agenda)
        result=self.preview()
        self.assertEqual(result.subtotal_precificado,Decimal('40.40'))
        self.assertEqual(len(result.totais_por_servico),2)

    def test_invalid_ancestry_fails_without_economic_code_invention(self):
        with self.engine.begin() as c:
            other=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar()
            c.execute(text('UPDATE sessoes_assistenciais SET paciente_id=:p WHERE agenda_cuidado_id=:a'),dict(p=other,a=self.agenda))
        with self.assertRaises(ValueError):self.preview()

    def test_draft_version_does_not_replace_published_price(self):
        self.new_version(self.start,'99.99',publish=False)
        self.assertEqual(self.preview().subtotal_precificado,Decimal('10.10'))

    def test_draft_contract_and_contract_end(self):
        from app.models.financeiro import ContratoFinanceiro
        row=self.service.create(self.db,ContratoFinanceiro,dict(pagador_instituicao_id=self.owner,codigo='SHORT',edicao=1,tabela_preco_id=self.tid,inicio=self.start,fim=self.start))
        cid=row.id
        self.service.create(self.db,PacienteContrato,dict(paciente_id=self.patient,contrato_id=cid,inicio=self.today))
        self.db.commit()
        self.assert_pending(self.preview(contrato_id=cid),'NO_CONTRACT')
        self.service.publish_contract(self.db,cid,actor_id=self.actor);self.db.commit()
        self.session(self.start+timedelta(days=1))
        result=self.preview(contrato_id=cid)
        self.assertEqual(result.itens[0].estado,'CALCULADO')
        self.assertEqual(result.itens[1].pendencia,'NO_CONTRACT')

    def test_wrong_occupation_and_agenda_duration_are_pending(self):
        with self.engine.begin() as c:
            occupation=c.exec_driver_sql("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Other synthetic') RETURNING id").scalar()
            c.execute(text('UPDATE agenda_cuidados SET ocupacao_id=:o WHERE id=:a'),dict(o=occupation,a=self.agenda))
        self.assert_pending(self.preview(),'INCOMPATIBLE_ECONOMIC_SERVICE_MAPPING')
        with self.engine.begin() as c:
            c.execute(text('UPDATE agenda_cuidados SET ocupacao_id=:o,duracao_minutos=30 WHERE id=:a'),dict(o=self.occupation,a=self.agenda))
        self.assert_pending(self.preview(),'INCOMPATIBLE_ECONOMIC_SERVICE_MAPPING')

    def test_truly_empty_plan_and_unknown_patient(self):
        with self.engine.begin() as c:
            patient=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Empty synthetic') RETURNING id").scalar()
        result=self.preview(paciente_id=patient)
        self.assertEqual(result.itens,())
        self.assertEqual(result.cobertura.agendas_sem_sessoes_elegiveis,())
        self.assertIsNone(result.subtotal_precificado)
        with self.assertRaises(ValueError):self.preview(paciente_id=999999)

    def test_calendar_leap_day_and_year_boundary(self):
        year=self.start.year
        while year % 4 or (year % 100==0 and year % 400!=0):year+=1
        days=(date(year,2,28),date(year,2,29),date(year,3,1),date(year,12,31),date(year+1,1,1))
        for day in days:self.session(day)
        result=self.preview(data_inicio=days[0],data_fim=days[-1])
        self.assertEqual(result.cobertura.sessoes_elegiveis,5)
        self.assertEqual(result.subtotal_precificado,Decimal('50.50'))
        self.assertEqual([x.quantidade_considerada for x in result.totais_por_mes],[2,1,1,1])

    def test_repeatable_snapshot_does_not_mix_concurrent_mapping_change(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            tx=c.begin();c.exec_driver_sql('SET TRANSACTION READ ONLY')
            try:
                with Session(bind=c) as db:
                    first=self.projection.preview(db,self.request())
                    with self.engine.begin() as writer:
                        writer.execute(text('DELETE FROM mapeamentos_agenda_servico WHERE agenda_cuidado_id=:a'),dict(a=self.agenda))
                    second=self.projection.preview(db,self.request())
                    self.assertEqual(first.model_dump_json(),second.model_dump_json())
            finally:tx.rollback()
        self.assert_pending(self.preview(),'NO_ECONOMIC_SERVICE_MAPPING')
