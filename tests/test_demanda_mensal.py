"""C2-M1 synthetic data only; no environment URL or remote database is used.

Run: python -m unittest discover -s tests -p test_demanda_mensal.py -v
"""
import unittest
from copy import deepcopy
from datetime import date, timedelta
from unittest.mock import patch

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

from app.services.demanda_mensal import DemandaMensalService, STATES


def plan(**changes):
    row = dict(agenda_id=1, pts_id=1, objetivo_id=1, atividade_id=1, ocupacao_id=1,
               profissional_id=4, frequencia_semanal=1, quantidade_sessoes=2,
               duracao_minutos=45, agenda_inicio=date(2026, 11, 1), agenda_fim=date(2026, 11, 30),
               paciente_id=21, modulo_id=3, contexto_id=2, pts_inicio=date(2026, 1, 1), pts_fim=None,
               objetivo_pts_id=1, contexto_paciente_id=21, instituicao_id=3, vinculo_id=9,
               contexto_ativo=True, contexto_inicio=date(2026, 1, 1), contexto_fim=None,
               vinculo_paciente_id=21, vinculo_instituicao_id=3, vinculo_ativo=True,
               vinculo_inicio=date(2026, 1, 1), vinculo_fim=None, sessao_id=None,
               numero_sessao=None, data_agendada=None, hora_inicio=None, hora_fim=None,
               sessao_duracao=None, sessao_estado=None, sessao_paciente_id=None,
               sessao_profissional_id=None, sessao_origem_id=None)
    row.update(changes)
    return row


def schedule(**changes):
    a = plan(**changes)
    return [dict(a, sessao_id=n, numero_sessao=n, data_agendada=a['agenda_inicio'] + timedelta(days=n-1),
                 sessao_duracao=a['duracao_minutos'], sessao_estado='AGENDADA',
                 sessao_paciente_id=a['paciente_id'], sessao_profissional_id=a['profissional_id'])
            for n in range(1, a['quantidade_sessoes'] + 1)]


class MonthlyDemandTests(unittest.TestCase):
    def calculate(self, rows, month='2026-11', occupation=None):
        s = DemandaMensalService()
        start, end = s._period(3, month, occupation)
        return s._calculate(rows, 3, occupation, start, end)

    def blocked(self, rows, code, quality='INCONSISTENTE'):
        result = self.calculate(rows)
        self.assertEqual(result['qualidade'], quality)
        self.assertIsNone(result['total_minutos_vigentes_projetados'])
        self.assertFalse(result['conclusivo'])
        self.assertIn(code, [p['codigo'] for p in result['pendencias']])
        return result

    def test_february_28_days(self):
        r = self.calculate([plan(agenda_inicio=date(2026, 2, 1), agenda_fim=date(2026, 2, 28))], '2026-02')
        self.assertEqual(r['data_fim'], '2026-02-28')
        self.assertEqual(r['minutos_vigentes_estimados'], 90)

    def test_month_30_days(self):
        self.assertEqual(self.calculate([])['data_fim'], '2026-11-30')

    def test_month_31_days(self):
        self.assertEqual(self.calculate([], '2026-12')['data_fim'], '2026-12-31')

    def test_leap_year(self):
        self.assertEqual(self.calculate([], '2028-02')['data_fim'], '2028-02-29')

    def test_month_boundaries(self):
        rows = schedule(quantidade_sessoes=4, agenda_inicio=date(2026, 10, 31), agenda_fim=date(2026, 12, 1))
        for r, day in zip(rows, (date(2026,10,31), date(2026,11,1), date(2026,11,30), date(2026,12,1))):
            r['data_agendada'] = day
        self.assertEqual(self.calculate(rows)['total_minutos_vigentes_projetados'], 90)

    def test_complete_schedule(self):
        r = self.calculate(schedule())
        self.assertEqual(r['qualidade'], 'CONCLUSIVO')
        self.assertEqual(r['minutos_vigentes_persistidos'], 90)
        self.assertEqual(r['quantidade_ocorrencias_estimadas'], 0)

    def test_partial_never_estimated(self):
        r = self.blocked(schedule()[:1], 'CRONOGRAMA_INCOMPLETO_OU_CONTRADITORIO', 'INCOMPLETO')
        self.assertEqual(r['minutos_vigentes_estimados'], 0)

    def test_numbering_contradiction(self):
        rows = schedule(); rows[1]['numero_sessao'] = 1
        self.blocked(rows, 'CRONOGRAMA_INCOMPLETO_OU_CONTRADITORIO')

    def test_manual_quantity_estimate_not_redistributed(self):
        r = self.calculate([plan(quantidade_sessoes=1)])
        self.assertEqual(r['qualidade'], 'ESTIMADO')
        self.assertEqual(r['quantidade_ocorrencias_estimadas'], 1)
        self.assertEqual(r['total_minutos_vigentes_projetados'], 45)
        self.assertFalse(r['conclusivo'])
        self.assertTrue(all(x == dict(quantidade=0, minutos=0) for x in r['por_status'].values()))

    def test_all_seven_states_separate(self):
        rows = schedule(quantidade_sessoes=7)
        for row, state in zip(rows, STATES): row['sessao_estado'] = state
        r = self.calculate(rows)
        self.assertEqual(r['minutos_vigentes_persistidos'], 5 * 45)
        self.assertEqual(r['por_status'], {s: dict(quantidade=1, minutos=45) for s in STATES})

    def test_two_distinct_occurrences_same_day(self):
        rows = schedule(); rows[1]['data_agendada'] = rows[0]['data_agendada']
        self.assertEqual(self.calculate(rows)['total_minutos_vigentes_projetados'], 90)

    def test_distinct_plans_same_day_different_explicit_times(self):
        first, second = schedule(), schedule(agenda_id=2)
        for r in first: r.update(hora_inicio='09:00', hora_fim='09:45')
        for r in second: r.update(hora_inicio='10:00', hora_fim='10:45')
        self.assertEqual(self.calculate(first + second)['total_minutos_vigentes_projetados'], 180)

    def test_missing_date_blocks(self):
        rows = schedule(); rows[0]['data_agendada'] = None
        self.blocked(rows, 'DATA_OU_DURACAO_INCONSISTENTE')

    def test_invalid_period_blocks(self):
        self.blocked(schedule(vinculo_fim=date(2025,1,1)), 'VIGENCIA_INVALIDA')

    def test_missing_period_blocks(self):
        self.blocked(schedule(pts_inicio=None), 'VIGENCIA_INCOMPLETA', 'INCOMPLETO')

    def test_foreign_link_blocks_instead_of_attributing(self):
        self.blocked(schedule(vinculo_instituicao_id=4), 'ANCESTRALIDADE_INCONSISTENTE')

    def test_integrity_is_checked_outside_month_fragment(self):
        rows = schedule(agenda_inicio=date(2026,10,31))
        rows[0]['sessao_duracao'] = 10
        self.blocked(rows, 'DATA_OU_DURACAO_INCONSISTENTE')

    def test_empty_scope_is_distinct_from_missing_data(self):
        r = self.calculate([])
        self.assertEqual(r['qualidade'], 'CONCLUSIVO')
        self.assertEqual(r['total_minutos_vigentes_projetados'], 0)
        self.assertEqual(r['pendencias'], [])

    def test_joint_period_partial_month_inclusive(self):
        rows = schedule(agenda_inicio=date(2026, 11, 15), contexto_inicio=date(2026,11,15),
                        vinculo_fim=date(2026,11,16), pts_fim=date(2026,11,16))
        self.assertEqual(self.calculate(rows)['total_minutos_vigentes_projetados'], 90)

    def test_occurrence_outside_joint_period(self):
        self.blocked(schedule(pts_inicio=date(2026,11,2)), 'OCORRENCIA_FORA_DA_VIGENCIA')

    def test_estimate_outside_period_not_clipped(self):
        self.blocked([plan(agenda_fim=date(2026,11,2))], 'OCORRENCIA_FORA_DA_VIGENCIA')

    def test_unknown_institution_not_inferred_or_disclosed(self):
        with self.assertLogs('app.services.demanda_mensal', level='WARNING') as logs:
            r = self.calculate([plan(contexto_id=None, instituicao_id=None)])
        self.assertEqual(r, self.calculate([]))
        self.assertIn('quantidade_planejamentos=1', logs.output[0])
        self.assertNotIn('paciente', logs.output[0])

    def test_estimated_zero_is_not_conclusive(self):
        r = self.calculate([plan(quantidade_sessoes=1, agenda_fim=date(2026,12,31))], '2026-12')
        self.assertEqual(r['total_minutos_vigentes_projetados'], 0)
        self.assertEqual(r['quantidade_ocorrencias_estimadas'], 0)
        self.assertEqual(r['qualidade'], 'ESTIMADO')
        self.assertFalse(r['conclusivo'])

    def test_estimate_date_overflow(self):
        r = self.calculate([plan(agenda_inicio=date.max, agenda_fim=None)], '9999-12')
        self.assertEqual(r['qualidade'], 'INCONSISTENTE')
        self.assertIsNone(r['total_minutos_vigentes_projetados'])
        self.assertEqual(r['pendencias'][0]['codigo'], 'ESTIMATIVA_LIMITE_DE_DATAS')

    def test_result_independent_of_elapsed_time(self):
        import time
        import app.services.demanda_mensal as demand
        source = [plan()]
        expected = self.calculate(source)
        original_date = demand._date
        def slow_date(value):
            time.sleep(0.03)
            return original_date(value)
        with patch('app.services.demanda_mensal._date', side_effect=slow_date):
            self.assertEqual(self.calculate(source), expected)
        with patch('time.monotonic', side_effect=AssertionError('Clock must not be read')):
            self.assertEqual(self.calculate(source), expected)
        self.assertNotIn('monotonic', vars(demand))

    def test_large_valid_quantity_is_not_capped(self):
        r = self.calculate([plan(quantidade_sessoes=100_001, frequencia_semanal=100_001)])
        self.assertEqual(r['quantidade_ocorrencias_estimadas'], 100_001)
        self.assertEqual(r['total_minutos_vigentes_projetados'], 100_001 * 45)

    def test_extreme_quantity_date_limit_discards_partial_counts(self):
        r = self.calculate([plan(agenda_inicio=date.max, agenda_fim=None,
                                quantidade_sessoes=2_000_000_000)], '9999-12')
        self.assertEqual(r['pendencias'][0]['codigo'], 'ESTIMATIVA_LIMITE_DE_DATAS')
        self.assertIsNone(r['total_minutos_vigentes_projetados'])
        self.assertEqual(r['quantidade_ocorrencias_estimadas'], 0)

    def test_numeric_underflow_is_a_traceable_pending_issue(self):
        self.blocked([plan(frequencia_semanal=10 ** 1000)],
                     'ESTIMATIVA_PRECISAO_NUMERICA_INSUFICIENTE')

    def test_stream_preserves_standard_engine_dates_and_counts(self):
        from app.services.scheduling_engine import SchedulingEngine
        from app.services.scheduling_models import PlanejamentoAssistencial
        for frequency in (1, 3, 7, 14):
            with self.subTest(frequency=frequency):
                beginning = date(2026,10,20)
                source = plan(agenda_inicio=beginning, agenda_fim=date(2026,12,31),
                              quantidade_sessoes=10, frequencia_semanal=frequency)
                proposal = SchedulingEngine.generate_sessions(PlanejamentoAssistencial(beginning,10,frequency,45))
                expected = sum(date(2026,11,1) <= s.data_agendada <= date(2026,11,30) for s in proposal)
                r = self.calculate([source])
                self.assertEqual(r['quantidade_ocorrencias_estimadas'], expected)
                self.assertEqual(r['minutos_vigentes_estimados'], expected * 45)

    def test_daily_distribution_matches_engine_in_long_sequences(self):
        from collections import Counter
        from app.services.scheduling_engine import SchedulingEngine
        from app.services.scheduling_models import PlanejamentoAssistencial
        for frequency, quantity in ((3, 5000), (7, 5000), (14, 5000), (100_001, 100_001)):
            with self.subTest(frequency=frequency, quantity=quantity):
                beginning = date(2020, 1, 1)
                a = plan(agenda_inicio=beginning, agenda_fim=None,
                         quantidade_sessoes=quantity, frequencia_semanal=frequency)
                expected = Counter(s.data_agendada for s in SchedulingEngine.generate_sessions(
                    PlanejamentoAssistencial(beginning, quantity, frequency, 45)))
                # Compare every generated day, month by month; use the same
                # complete validation on each invocation.
                months = sorted({(d.year, d.month) for d in expected})
                actual = Counter()
                for year, month in months:
                    start, end = DemandaMensalService._period(3, f'{year:04d}-{month:02d}', None)
                    counts, error = DemandaMensalService._estimate(a, [(beginning, None)], start, end)
                    self.assertIsNone(error)
                    self.assertLessEqual(len(counts), 31)
                    actual.update(counts)
                self.assertEqual(actual, expected)

    def test_last_representable_date_succeeds(self):
        a = plan(agenda_inicio=date.max - timedelta(days=7), agenda_fim=None)
        counts, error = DemandaMensalService._estimate(a, [(a['agenda_inicio'], None)],
                                                       date(9999,12,1), date.max)
        self.assertIsNone(error)
        self.assertEqual(counts, {date.max - timedelta(days=7): 1, date.max: 1})

    def test_semantic_duplicates_block_both(self):
        rows = schedule() + schedule(agenda_id=2, objetivo_id=2)
        r = self.blocked(rows, 'POSSIVEL_DUPLICIDADE_SEMANTICA')
        self.assertEqual(r['minutos_vigentes_persistidos'], 0)

    def test_institution_filter(self):
        rows = schedule() + schedule(agenda_id=2, instituicao_id=4, vinculo_instituicao_id=4)
        self.assertEqual(self.calculate(rows)['total_minutos_vigentes_projetados'], 90)

    def test_occupation_filter(self):
        rows = schedule() + schedule(agenda_id=2, ocupacao_id=2)
        self.assertEqual(self.calculate(rows, occupation=2)['total_minutos_vigentes_projetados'], 90)

    def test_missing_quantity_not_zero(self):
        self.blocked([plan(quantidade_sessoes=None)], 'PLANEJAMENTO_QUANTITATIVO_INVALIDO', 'INCOMPLETO')

    def test_unknown_state(self):
        rows = schedule(); rows[1]['sessao_estado'] = 'OUTRO'
        self.blocked(rows, 'ESTADO_DESCONHECIDO')

    def test_inconsistent_duration(self):
        rows = schedule(); rows[1]['sessao_duracao'] = 50
        self.blocked(rows, 'DATA_OU_DURACAO_INCONSISTENTE')

    def test_invalid_times(self):
        rows = schedule(); rows[1].update(hora_inicio='09:00', hora_fim='09:50')
        self.blocked(rows, 'HORARIO_INCONSISTENTE')

    def test_dates_contradict_numbering(self):
        rows = schedule()
        rows[0]['data_agendada'], rows[1]['data_agendada'] = rows[1]['data_agendada'], rows[0]['data_agendada']
        self.blocked(rows, 'SEQUENCIA_TEMPORAL_INCONSISTENTE')

    def test_join_multiplication(self):
        rows = schedule(); rows.append(deepcopy(rows[0]))
        self.blocked(rows, 'OCORRENCIA_MULTIPLICADA')

    def test_ancestry(self):
        self.blocked(schedule(objetivo_pts_id=99), 'ANCESTRALIDADE_INCONSISTENTE')

    def test_session_ancestry(self):
        rows = schedule(); rows[0]['sessao_paciente_id'] = 99
        self.blocked(rows, 'SESSAO_ANCESTRALIDADE_INCONSISTENTE')

    def test_replacement_no_double_count(self):
        rows = schedule(); rows[0]['sessao_estado'] = 'REAGENDADA'; rows[1]['sessao_origem_id'] = 1
        self.assertEqual(self.calculate(rows)['total_minutos_vigentes_projetados'], 45)

    def test_replacement_unproven(self):
        rows = schedule(); rows[1]['sessao_origem_id'] = 99
        self.blocked(rows, 'SUBSTITUICAO_NAO_COMPROVADA')

    def test_replacement_branches(self):
        rows = schedule(quantidade_sessoes=3); rows[0]['sessao_estado'] = 'REAGENDADA'
        rows[1]['sessao_origem_id'] = rows[2]['sessao_origem_id'] = 1
        self.blocked(rows, 'SUBSTITUICAO_AMBIGUA')

    def test_unaffected_subtotal_preserved_but_total_blocked(self):
        rows = schedule() + [plan(agenda_id=2, quantidade_sessoes=None)]
        r = self.blocked(rows, 'PLANEJAMENTO_QUANTITATIVO_INVALIDO', 'INCOMPLETO')
        self.assertEqual(r['minutos_vigentes_persistidos'], 90)
        self.assertTrue(r['subtotais_parciais'])

    def test_inactive_scope_excluded(self):
        self.assertEqual(self.calculate(schedule(contexto_ativo=False))['total_minutos_vigentes_projetados'], 0)

    def test_invalid_input(self):
        for institution, month, occupation in ((True,'2026-11',None),(3,'2026-1',None),
                                              (3,'2026-13',None),(3,'2026-11',0)):
            with self.subTest(month=month, institution=institution, occupation=occupation):
                with self.assertRaises(ValueError):
                    DemandaMensalService._period(institution,month,occupation)


class ReadAdapterTests(unittest.TestCase):
    """Execute the actual selection on disposable in-memory SQLite, no mocks."""
    def test_read_only_query_filters_and_minimization(self):
        engine = create_engine('sqlite:///:memory:')
        definitions = {
            'instituicoes': 'id int, ativo boolean',
            'agenda_cuidados': 'id int, pts_id int, objetivo_id int, atividade_id int, ocupacao_id int, profissional_id int, frequencia_semanal int, quantidade_sessoes int, duracao_minutos int, data_inicio date, data_fim date, status text',
            'pts': 'id int, paciente_id int, modulo_id int, contexto_assistencial_id int, data_inicio date, data_fim date, status text',
            'pts_objetivos': 'id int, pts_id int, status text',
            'contextos_assistenciais': 'id int, paciente_id int, instituicao_id int, paciente_instituicao_id int, ativo boolean, data_inicio date, data_fim date',
            'paciente_instituicoes': 'id int, paciente_id int, instituicao_id int, ativo boolean, data_inicio date, data_fim date',
            'sessoes_assistenciais': 'id int, agenda_cuidado_id int, numero_sessao int, data_agendada date, hora_inicio time, hora_fim time, duracao_minutos int, status text, paciente_id int, profissional_id int, sessao_origem_id int',
        }
        try:
            with engine.begin() as conn:
                for table, columns in definitions.items():
                    conn.execute(text(f'CREATE TABLE {table} ({columns})'))
                conn.execute(text('INSERT INTO instituicoes VALUES (3,1), (4,1), (5,0)'))
                for i in range(1, 6):
                    institution = 4 if i == 2 else 3
                    pstate = 'ENCERRADO' if i == 3 else 'ATIVO'
                    ostate = 'FECHADO' if i == 4 else 'ABERTO'
                    astate = 'CANCELADO' if i == 5 else 'PLANEJADO'
                    conn.execute(text(f"INSERT INTO paciente_instituicoes VALUES ({i},21,{institution},1,'2026-01-01',NULL)"))
                    conn.execute(text(f"INSERT INTO contextos_assistenciais VALUES ({i},21,{institution},{i},1,'2026-01-01',NULL)"))
                    conn.execute(text(f"INSERT INTO pts VALUES ({i},21,3,{i},'2026-01-01',NULL,'{pstate}')"))
                    conn.execute(text(f"INSERT INTO pts_objetivos VALUES ({i},{i},'{ostate}')"))
                    conn.execute(text(f"INSERT INTO agenda_cuidados VALUES ({i},{i},{i},1,1,4,1,1,45,'2026-11-01','2026-11-30','{astate}')"))
                conn.execute(text("INSERT INTO pts VALUES (6,99,3,NULL,'2026-01-01',NULL,'ATIVO')"))
                conn.execute(text("INSERT INTO pts_objetivos VALUES (6,6,'ABERTO')"))
                conn.execute(text("INSERT INTO agenda_cuidados VALUES (6,6,6,1,1,4,1,1,45,'2026-11-01','2026-11-30','PLANEJADO')"))
            statements = []
            event.listen(engine, 'before_cursor_execute', lambda c, cur, stmt, args, ctx, many: statements.append(stmt))
            with Session(engine) as db:
                r = DemandaMensalService().calculate(db, instituicao_id=3, mes_referencia='2026-11')
            self.assertEqual(r['total_minutos_vigentes_projetados'], 45)
            self.assertEqual(r['qualidade'], 'ESTIMADO')
            self.assertEqual(len(statements), 2)
            self.assertTrue(all(stmt.lstrip().startswith('SELECT') for stmt in statements))
            self.assertNotIn('registros_longitudinais', statements[1])
            with Session(engine) as db:
                other = DemandaMensalService().calculate(db, instituicao_id=4, mes_referencia='2026-11')
            self.assertEqual(other['total_minutos_vigentes_projetados'], 45)
            self.assertEqual(other['qualidade'], 'ESTIMADO')
            self.assertEqual(other['pendencias'], [])
            for institution in (5, 999):
                with self.subTest(institution=institution), Session(engine) as db:
                    with self.assertRaises(ValueError):
                        DemandaMensalService().calculate(db, instituicao_id=institution, mes_referencia='2026-11')
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
