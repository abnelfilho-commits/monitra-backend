"""Legacy compatibility using the disposable C2 PostgreSQL fixture, no migrations."""
import unittest
from datetime import date
from types import SimpleNamespace
from sqlalchemy import text, event
import test_consolidacao_mensal as fixture
from app.services.demanda_mensal import DemandaMensalService


class LegacyTests(unittest.TestCase):
    setUp = fixture.ConsolidacaoTests.setUp
    cleanup = fixture.ConsolidacaoTests.cleanup
    write = fixture.ConsolidacaoTests.write
    demand = fixture.ConsolidacaoTests.demand
    read = fixture.ConsolidacaoTests.read

    def legacy(self, estimated=False):
        self.demand(estimated=estimated)
        self.write('UPDATE pts SET modulo_id=1, contexto_assistencial_id=NULL')

    def direct(self, institution=3):
        return DemandaMensalService().calculate(self.db, instituicao_id=institution,
                                               mes_referencia='2026-11')

    def blocked(self, code):
        r = self.direct()
        self.assertIsNone(r['total_minutos_vigentes_projetados'])
        self.assertTrue(r['subtotais_parciais'])
        self.assertIn(code, [p['codigo'] for p in r['pendencias']])
        return r

    def test_eligible_persisted_and_occupation_totals(self):
        self.legacy()
        r = self.read()
        self.assertEqual(r['demanda_mensal_projetada'],45)
        self.assertEqual(r['ocupacoes'][0]['demanda_mensal_projetada'],45)
        self.assertEqual(r['ocupacoes'][0]['ocupacao_id'],1)
        self.assertEqual(r['qualidade_demanda'],'CONCLUSIVO')
        self.assertEqual(self.db.execute(text('SELECT contexto_assistencial_id FROM pts')).scalar(),None)

    def test_estimated_legacy_uses_existing_engine(self):
        self.legacy(estimated=True)
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],45)
        self.assertEqual(self.direct()['qualidade'],'ESTIMADO')

    def test_non_neuro_legacy_excluded(self):
        self.legacy(); self.write('UPDATE pts SET modulo_id=3')
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],0)

    def test_foreign_institution_isolated(self):
        self.legacy()
        r=self.direct(4)
        self.assertEqual(r['total_minutos_vigentes_projetados'],0)
        self.assertEqual(r['pendencias'],[])
        self.assertEqual(self.read(instituicao_id=4)['ocupacoes'],[])

    def test_no_link_not_attributed(self):
        self.legacy(); self.write('DELETE FROM paciente_instituicoes')
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],0)

    def test_inactive_link_excluded(self):
        self.legacy(); self.write('UPDATE paciente_instituicoes SET ativo=false')
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],0)

    def test_competing_institution_blocks_without_identifiers(self):
        self.legacy()
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2026-11-15',null)")
        r=self.blocked('LEGADO_VINCULO_AMBIGUO')
        self.assertEqual(r['pendencias'][0]['agenda_id'], 1)
        self.assertNotIn('agenda_id', str(self.read()))
        self.assertIsNone(self.read()['ocupacoes'][0]['demanda_mensal_projetada'])

    def test_same_institution_duplicate_links_block(self):
        self.legacy()
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,3,true,'2026-01-01',null)")
        self.blocked('LEGADO_VINCULO_AMBIGUO')

    def test_non_overlapping_foreign_link_does_not_block(self):
        self.legacy()
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2027-01-01',null)")
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],45)

    def test_partial_coverage_blocks_even_when_session_is_covered(self):
        self.legacy(); self.write("UPDATE paciente_instituicoes SET data_fim='2026-11-02'")
        self.blocked('LEGADO_COBERTURA_INCOMPLETA')

    def test_coverage_gap_not_stitched(self):
        self.legacy(); self.write("UPDATE paciente_instituicoes SET data_fim='2026-11-10'")
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,3,true,'2026-11-12',null)")
        self.blocked('LEGADO_VINCULO_AMBIGUO')

    def test_session_outside_planning_checked(self):
        self.legacy();self.write("UPDATE sessoes_assistenciais SET data_agendada='2026-12-01'")
        self.blocked('OCORRENCIA_FORA_DA_VIGENCIA')

    def test_foreign_link_outside_month_but_inside_planning_blocks(self):
        self.legacy(); self.write("UPDATE agenda_cuidados SET data_fim='2026-12-31'")
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2026-12-01',null)")
        self.blocked('LEGADO_VINCULO_AMBIGUO')

    def test_invalid_link_dates_block(self):
        self.legacy(); self.write("UPDATE paciente_instituicoes SET data_inicio=NULL")
        self.blocked('LEGADO_COBERTURA_INCOMPLETA')

    def test_invalid_session_duration_reuses_validation(self):
        self.legacy(); self.write('UPDATE sessoes_assistenciais SET duracao_minutos=99')
        self.blocked('DATA_OU_DURACAO_INCONSISTENTE')

    def test_invalid_objective_ancestry_reuses_validation(self):
        self.legacy(); self.write('UPDATE pts_objetivos SET pts_id=99')
        self.blocked('ANCESTRALIDADE_INCONSISTENTE')

    def test_states_preserved(self):
        self.legacy();self.write("UPDATE sessoes_assistenciais SET status='CANCELADA'")
        r=self.direct()
        self.assertEqual(r['total_minutos_vigentes_projetados'],0)
        self.assertEqual(r['por_status']['CANCELADA']['quantidade'],1)

    def test_contextual_copy_blocks_double_count(self):
        self.legacy()
        self.write("INSERT INTO pts VALUES (2,21,1,2,'2026-01-01',null,'ATIVO')")
        self.write("INSERT INTO pts_objetivos VALUES (2,2,'ABERTO')")
        self.write("INSERT INTO agenda_cuidados SELECT 2,2,2,atividade_id,ocupacao_id,profissional_id,frequencia_semanal,quantidade_sessoes,duracao_minutos,data_inicio,data_fim,status FROM agenda_cuidados WHERE id=1")
        self.write("INSERT INTO sessoes_assistenciais SELECT 2,2,numero_sessao,data_agendada,hora_inicio,hora_fim,duracao_minutos,status,paciente_id,profissional_id,sessao_origem_id FROM sessoes_assistenciais WHERE id=1")
        r=self.blocked('POSSIVEL_DUPLICIDADE_SEMANTICA')
        self.assertEqual(r['minutos_vigentes_persistidos'],0)

    def test_contextual_path_not_reassigned_by_legacy_links(self):
        self.demand()
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2026-01-01',null)")
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],45)

    def test_inclusive_coverage_boundaries(self):
        self.legacy()
        self.write("UPDATE paciente_instituicoes SET data_inicio='2026-11-01', data_fim='2026-11-30'")
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],45)

    def test_two_occupations_sum_and_filter(self):
        self.legacy()
        self.write("INSERT INTO agenda_cuidados SELECT 2,pts_id,objetivo_id,atividade_id,2,profissional_id,frequencia_semanal,quantidade_sessoes,duracao_minutos,data_inicio,data_fim,status FROM agenda_cuidados WHERE id=1")
        self.write("INSERT INTO sessoes_assistenciais SELECT 2,2,numero_sessao,data_agendada,hora_inicio,hora_fim,duracao_minutos,status,paciente_id,profissional_id,sessao_origem_id FROM sessoes_assistenciais WHERE id=1")
        r=self.read()
        self.assertEqual(r['demanda_mensal_projetada'],90)
        self.assertEqual(sum(o['demanda_mensal_projetada'] for o in r['ocupacoes']),90)
        self.assertEqual(self.read(ocupacao_id=2)['demanda_mensal_projetada'],45)

    def open_plan(self, estimated=False):
        self.legacy(estimated=estimated)
        self.write('UPDATE agenda_cuidados SET data_fim=NULL')
        self.write("UPDATE paciente_instituicoes SET data_inicio='2026-11-01', data_fim='2026-11-30'")

    def test_open_complete_schedule_covered(self):
        self.open_plan()
        r=self.read()
        self.assertEqual(r['demanda_mensal_projetada'],45)
        self.assertEqual(r['qualidade_demanda'],'CONCLUSIVO')
        self.assertEqual(r['pendencias'],[])

    def test_open_future_competitor_does_not_block(self):
        self.open_plan()
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2027-01-01',NULL)")
        self.assertEqual(self.direct()['total_minutos_vigentes_projetados'],45)
        self.assertEqual(self.direct(4)['total_minutos_vigentes_projetados'],0)

    def test_open_partial_coverage_still_blocks(self):
        self.open_plan()
        self.write("UPDATE sessoes_assistenciais SET data_agendada='2026-12-01'")
        self.blocked('LEGADO_COBERTURA_INCOMPLETA')

    def test_open_incomplete_schedule_has_no_proven_end(self):
        self.open_plan()
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=2')
        self.blocked('LEGADO_TERMINO_NAO_COMPROVADO')

    def test_open_contradictory_numbering_has_no_proven_end(self):
        self.open_plan()
        self.write('UPDATE sessoes_assistenciais SET numero_sessao=2')
        self.blocked('LEGADO_TERMINO_NAO_COMPROVADO')

    def test_open_invalid_session_not_accepted_by_bound(self):
        self.open_plan()
        self.write('UPDATE sessoes_assistenciais SET duracao_minutos=99')
        self.blocked('DATA_OU_DURACAO_INCONSISTENTE')

    def test_open_finite_recurrence_covered(self):
        self.open_plan(estimated=True)
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=3')
        self.write("UPDATE paciente_instituicoes SET data_fim='2026-11-15'")
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2026-11-16',NULL)")
        r=self.direct()
        self.assertEqual(r['total_minutos_vigentes_projetados'],135)
        self.assertEqual(r['qualidade'],'ESTIMADO')

    def test_open_recurrence_partial_coverage(self):
        self.open_plan(estimated=True)
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=3')
        self.write("UPDATE paciente_instituicoes SET data_fim='2026-11-14'")
        self.blocked('LEGADO_COBERTURA_INCOMPLETA')

    def test_open_recurrence_invalid_quantity(self):
        self.open_plan(estimated=True)
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=NULL')
        self.blocked('LEGADO_TERMINO_NAO_COMPROVADO')

    def test_open_recurrence_invalid_pts_period(self):
        self.open_plan(estimated=True)
        self.write("UPDATE pts SET data_fim='2025-01-01'")
        self.blocked('LEGADO_TERMINO_NAO_COMPROVADO')

    def ambiguous_pair(self, occupation):
        self.legacy()
        self.write(f"INSERT INTO agenda_cuidados SELECT 2,pts_id,objetivo_id,atividade_id,{occupation},profissional_id,frequencia_semanal,quantidade_sessoes,duracao_minutos,data_inicio,data_fim,status FROM agenda_cuidados WHERE id=1")
        self.write("INSERT INTO sessoes_assistenciais SELECT 2,2,numero_sessao,data_agendada,hora_inicio,hora_fim,duracao_minutos,status,paciente_id,profissional_id,sessao_origem_id FROM sessoes_assistenciais WHERE id=1")
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2026-01-01',NULL)")

    def test_pending_two_agendas_same_occupation(self):
        self.ambiguous_pair(1)
        r=self.read()
        self.assertEqual(r['pendencias'][0]['quantidade'],2)
        self.assertEqual(r['ocupacoes'][0]['pendencias'][0]['quantidade'],2)

    def test_pending_two_occupations_consistent_and_sanitized(self):
        self.ambiguous_pair(2)
        r=self.read()
        self.assertEqual(r['pendencias'],[dict(origem='DEMANDA',codigo='LEGADO_VINCULO_AMBIGUO',quantidade=2)])
        self.assertEqual(sum(o['pendencias'][0]['quantidade'] for o in r['ocupacoes']),2)
        for secret in ('agenda_id','sessao_id','paciente_id','vinculo_id'):
            self.assertNotIn(secret,str(r))
        self.assertIsNone(r['demanda_mensal_projetada'])

    def test_pending_repeated_sessions_only_once_per_agenda(self):
        self.legacy()
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=2')
        self.write("INSERT INTO sessoes_assistenciais SELECT 2,1,2,'2026-11-02',hora_inicio,hora_fim,duracao_minutos,status,paciente_id,profissional_id,sessao_origem_id FROM sessoes_assistenciais WHERE id=1")
        self.write("INSERT INTO paciente_instituicoes VALUES (10,21,4,true,'2026-01-01',NULL)")
        self.assertEqual(self.read()['pendencias'][0]['quantidade'],1)

    def test_occupation_discovery_aggregates_without_sessions(self):
        from time import perf_counter
        self.legacy()
        # A bounded synthetic volume; no benchmark against shared databases.
        self.write("INSERT INTO agenda_cuidados SELECT n,1,1,1,1+(n%3),4,1,20,45,'2026-11-01','2026-11-30','PLANEJADO' FROM generate_series(2,200) n")
        self.write("INSERT INTO sessoes_assistenciais SELECT 1000+(a.id*20)+n,a.id,n,DATE '2026-11-01'+(n-1),null,null,45,'AGENDADA',21,4,null FROM agenda_cuidados a CROSS JOIN generate_series(1,20) n WHERE a.id>1")
        # Exclude the existing Session transaction-initialization hook from
        # the measurement of the occupation-discovery query itself.
        self.db.execute(text('SELECT 1'))
        statements=[]
        def capture(c,cur,sql,params,ctx,many): statements.append(sql)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            start=perf_counter()
            result=DemandaMensalService.occupation_candidates(self.db,3)
            elapsed=perf_counter()-start
        finally:event.remove(self.engine,'before_cursor_execute',capture)
        self.assertEqual(result,{1,2,3})
        self.assertEqual(len(statements),1)
        self.assertIn('SELECT DISTINCT',statements[0])
        self.assertNotIn('sessoes_assistenciais',statements[0])
        self.assertEqual(DemandaMensalService.occupation_candidates(self.db,4),set())
        print('C2_P2_OCCUPATIONS',dict(agendas=200,sessions=3981,queries=1,returned=3,seconds=round(elapsed,6)))

    def test_financial_reader_keeps_legacy_and_eligible_status_boundary(self):
        from app.services.financeiro.neuro_reader import read_neuro_batch
        self.legacy()
        self.write('CREATE TABLE pacientes(id integer primary key)')
        self.write('INSERT INTO pacientes VALUES(21)')
        request=SimpleNamespace(data_inicio=date(2026,11,1),data_fim=date(2026,11,30))
        for status, expected in [('CONFIRMADA',1),('REALIZADA',0),('CANCELADA',0)]:
            self.write("UPDATE sessoes_assistenciais SET status='"+status+"'")
            self.assertEqual(len(read_neuro_batch(self.db,(21,),request)[21].sessions),expected)
        self.write("UPDATE sessoes_assistenciais SET status='AGENDADA'")
        self.write('UPDATE pts SET contexto_assistencial_id=2')
        self.assertEqual(len(read_neuro_batch(self.db,(21,),request)[21].sessions),0)

    def test_financial_neuro_reader_unchanged_before_after_demand(self):
        from app.services.financeiro.neuro_reader import read_neuro_batch
        self.legacy()
        self.write('CREATE TABLE pacientes(id integer primary key)')
        self.write('INSERT INTO pacientes VALUES(21)')
        request=SimpleNamespace(data_inicio=date(2026,11,1),data_fim=date(2026,11,30))
        before=read_neuro_batch(self.db,(21,),request)
        self.direct()
        after=read_neuro_batch(self.db,(21,),request)
        self.assertEqual(before,after)
        self.assertEqual(len(after[21].sessions),1)


if __name__=='__main__':
    unittest.main()
