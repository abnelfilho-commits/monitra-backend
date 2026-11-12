"""C2-M3 integration: ONLY disposable local PostgreSQL, synthetic data.

Start postgres:18 as integra-c2m3-synthetic, database c2m3_synthetic,
password c2m3_local_only, port 127.0.0.1:55743. Never uses configured DB URL.
Each test owns and drops a separate schema. No production migrations.
"""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import create_engine, text, event
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:///:memory:'}):
    from app.services.institucional import InstitucionalErro
from app.services.consolidacao_mensal import ConsolidacaoMensalService, _snapshot
from app.services.demanda_mensal import DemandaMensalService

URL = 'postgresql+psycopg2://postgres:c2m3_local_only@127.0.0.1:55743/c2m3_synthetic'


class ConsolidacaoTests(unittest.TestCase):
    def setUp(self):
        self.root = create_engine(URL)
        self.schema = 'c2m3_' + uuid4().hex
        with self.root.begin() as c:
            c.execute(text('CREATE SCHEMA ' + self.schema))
        self.engine = create_engine(URL, connect_args={'options': '-csearch_path=' + self.schema})
        self.addCleanup(self.cleanup)
        definitions = {
            'usuarios': 'id int primary key, pessoa_id int, nome text, email text, senha_hash text, perfil text, clinica_id int, profissional_id int, ativo boolean',
            'instituicoes': 'id int primary key, ativo boolean',
            'profissionais': 'id int primary key, ativo boolean',
            'ocupacoes_profissionais': 'id int primary key, nome text, ativo boolean',
            'profissional_instituicoes': 'id int primary key, instituicao_id int, profissional_id int, ocupacao_id int, data_inicio date, data_fim date, ativo boolean',
            'capacidades_profissionais': 'id int primary key, profissional_instituicao_id int, minutos_semanais int, data_inicio date, data_fim date, ativo boolean',
            'pts': 'id int primary key, paciente_id int, modulo_id int, contexto_assistencial_id int, data_inicio date, data_fim date, status text',
            'pts_objetivos': 'id int primary key, pts_id int, status text',
            'contextos_assistenciais': 'id int primary key, paciente_id int, instituicao_id int, paciente_instituicao_id int, ativo boolean, data_inicio date, data_fim date',
            'paciente_instituicoes': 'id int primary key, paciente_id int, instituicao_id int, ativo boolean, data_inicio date, data_fim date',
            'agenda_cuidados': 'id int primary key, pts_id int, objetivo_id int, atividade_id int, ocupacao_id int, profissional_id int, frequencia_semanal int, quantidade_sessoes int, duracao_minutos int, data_inicio date, data_fim date, status text',
            'sessoes_assistenciais': 'id int primary key, agenda_cuidado_id int, numero_sessao int, data_agendada date, hora_inicio time, hora_fim time, duracao_minutos int, status text, paciente_id int, profissional_id int, sessao_origem_id int',
        }
        with self.engine.begin() as c:
            for name, columns in definitions.items():
                c.execute(text(f'CREATE TABLE {name} ({columns})'))
            for sql in (
                "INSERT INTO usuarios(id,ativo,perfil) VALUES (1,true,'ADMIN'),(2,true,'GESTOR'),(3,false,'ADMIN')",
                'INSERT INTO instituicoes VALUES (3,true),(4,true),(5,false)',
                'INSERT INTO profissionais VALUES (4,true)',
                "INSERT INTO ocupacoes_profissionais VALUES (1,'Synthetic',true),(2,'Synthetic',true)",
                "INSERT INTO paciente_instituicoes VALUES (9,21,3,true,'2026-01-01',null)",
                "INSERT INTO contextos_assistenciais VALUES (2,21,3,9,true,'2026-01-01',null)",
                "INSERT INTO pts VALUES (1,21,3,2,'2026-01-01',null,'ATIVO')",
                "INSERT INTO pts_objetivos VALUES (1,1,'ABERTO')",
            ):
                c.execute(text(sql))
        self.db = Session(self.engine)
        self.addCleanup(self.db.close)

    def cleanup(self):
        self.engine.dispose()
        with self.root.begin() as c:
            c.execute(text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        self.root.dispose()

    def write(self, sql):
        with self.engine.begin() as c:
            c.execute(text(sql))

    def demand(self, occupation=1, estimated=False):
        self.write(f"INSERT INTO agenda_cuidados VALUES (1,1,1,1,{occupation},4,1,1,45,'2026-11-01','2026-11-30','PLANEJADO')")
        if not estimated:
            self.write("INSERT INTO sessoes_assistenciais VALUES (1,1,1,'2026-11-01',null,null,45,'AGENDADA',21,4,null)")

    def capacity(self, occupation=1, end='2026-11-30', minutes=7):
        self.write(f"INSERT INTO profissional_instituicoes VALUES (9,3,4,{occupation},'2026-01-01',null,true)")
        self.write(f"INSERT INTO capacidades_profissionais VALUES (12,9,{minutes},'2026-11-01','{end}',true)")

    def read(self, **changes):
        return ConsolidacaoMensalService().calculate(self.db, **dict(
            dict(instituicao_id=3, mes_referencia='2026-11', actor_id=1), **changes))

    def test_authorized_both_engines(self):
        self.demand(); self.capacity()
        r = self.read()
        self.assertEqual((r['demanda_mensal_projetada'], r['capacidade_mensal_equivalente'], r['saldo_mensal'], r['utilizacao_percentual']), (45,'30.00','-15.00','150.00'))
        self.assertEqual(r['qualidade'], 'CONCLUSIVO')
        self.assertEqual(len(r['ocupacoes']), 1)

    def test_unauthorized_before_assistential_query(self):
        with patch.object(DemandaMensalService, 'calculate') as demand:
            for actor in (2,3,999):
                with self.subTest(actor=actor), self.assertRaises(InstitucionalErro):
                    self.read(actor_id=actor)
            demand.assert_not_called()

    def test_inactive_and_absent_institution(self):
        with patch.object(DemandaMensalService, 'calculate') as demand:
            for institution in (5,999):
                with self.subTest(institution=institution), self.assertRaises(InstitucionalErro):
                    self.read(instituicao_id=institution)
            demand.assert_not_called()

    def test_demand_only_occupation(self):
        self.demand()
        r = self.read()['ocupacoes'][0]
        self.assertEqual(r['ocupacao_id'], 1)
        self.assertEqual(r['demanda_mensal_projetada'],45)
        self.assertEqual(r['capacidade_mensal_equivalente'],'0.00')
        self.assertEqual(r['motivo_utilizacao_nula'],'CAPACIDADE_ZERO')
        self.assertIsNone(r['utilizacao_percentual'])

    def test_capacity_only_occupation(self):
        self.capacity(occupation=2)
        r = self.read()['ocupacoes'][0]
        self.assertEqual(r['ocupacao_id'],2)
        self.assertEqual(r['demanda_mensal_projetada'],0)
        self.assertEqual(r['utilizacao_percentual'],'0.00')

    def test_union_and_filter(self):
        self.demand(); self.capacity(occupation=2)
        self.assertEqual([o['ocupacao_id'] for o in self.read()['ocupacoes']],[1,2])
        r = self.read(ocupacao_id=2)
        self.assertEqual([o['ocupacao_id'] for o in r['ocupacoes']],[2])
        self.assertEqual(r['demanda_mensal_projetada'],0)

    def test_estimated_is_not_conclusive(self):
        self.demand(estimated=True); self.capacity()
        r = self.read()
        self.assertEqual(r['qualidade'],'ESTIMADO')
        self.assertFalse(r['conclusivo'])
        self.assertEqual(r['utilizacao_percentual'],'150.00')

    def test_incomplete_capacity_null_derivatives(self):
        self.capacity(end='2026-11-10'); self.demand()
        r = self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'10.00')
        self.assertTrue(r['capacidade_subtotal_parcial'])
        self.assertEqual(r['qualidade'],'INCOMPLETO')
        for key in ('capacidade_mensal_equivalente','saldo_mensal','utilizacao_percentual'):
            self.assertIsNone(r[key])

    def test_inconsistent_priority(self):
        self.capacity(minutes=-1); self.demand(estimated=True)
        self.assertEqual(self.read()['qualidade'],'INCONSISTENTE')

    def test_null_demand_not_zero(self):
        self.demand(); self.capacity()
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=2')
        r = self.read()
        self.assertIsNone(r['demanda_mensal_projetada'])
        self.assertIsNone(r['saldo_mensal'])
        self.assertEqual(r['motivo_utilizacao_nula'],'DEMANDA_NAO_CALCULAVEL')

    def test_empty_zero_denominator(self):
        r = self.read()
        self.assertEqual(r['saldo_mensal'],'0.00')
        self.assertEqual(r['motivo_utilizacao_nula'],'CAPACIDADE_ZERO')
        self.assertIsNone(r['utilizacao_percentual'])

    def test_pending_sanitization(self):
        self.demand(); self.capacity(minutes=-1)
        self.write('UPDATE agenda_cuidados SET quantidade_sessoes=2')
        r = self.read()
        forbidden = {'agenda_id','sessao_id','vinculo_id','profissional_id','paciente_id','capacidade_id','detalhes_vinculos'}
        def check(value):
            if isinstance(value,dict):
                self.assertFalse(forbidden & value.keys())
                for child in value.values(): check(child)
            elif isinstance(value,list):
                for child in value: check(child)
        check(r)
        for p in r['pendencias']:
            self.assertEqual(set(p), {'origem','codigo','quantidade'})

    def test_institution_isolation(self):
        self.demand(); self.capacity()
        r = self.read(instituicao_id=4)
        self.assertEqual(r['demanda_mensal_projetada'],0)
        self.assertEqual(r['capacidade_mensal_equivalente'],'0.00')
        self.assertEqual(r['ocupacoes'],[])

    def test_snapshot_during_concurrent_commit(self):
        self.demand(); self.capacity()
        original = DemandaMensalService.calculate
        changed = False
        def concurrent(service, *args, **kwargs):
            nonlocal changed
            result = original(service, *args, **kwargs)
            if not changed:
                self.write('UPDATE capacidades_profissionais SET minutos_semanais=14')
                changed = True
            return result
        with patch.object(DemandaMensalService,'calculate',concurrent):
            self.assertEqual(self.read()['capacidade_mensal_equivalente'],'30.00')
        self.assertEqual(self.read()['capacidade_mensal_equivalente'],'60.00')

    def test_snapshot_read_only_enforced(self):
        with self.assertRaises(DBAPIError):
            with _snapshot(self.db) as reader:
                self.assertEqual(reader.execute(text('SHOW transaction_isolation')).scalar(),'repeatable read')
                self.assertEqual(reader.execute(text('SHOW transaction_read_only')).scalar(),'on')
                reader.execute(text('INSERT INTO instituicoes VALUES (99,true)'))
        self.assertEqual(self.db.execute(text('SHOW transaction_isolation')).scalar(),'read committed')
        self.assertEqual(self.db.execute(text('SHOW transaction_read_only')).scalar(),'off')

    def test_no_write_or_shared_session_flush(self):
        from app.models.usuario import Usuario
        self.db.add(Usuario(id=99,nome='Synthetic',email='s',senha_hash='s',perfil='ADMIN',ativo=True))
        transaction = self.db.get_transaction()
        statements = []
        def capture(conn,cursor,statement,params,context,many): statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            self.read()
        finally:
            event.remove(self.engine,'before_cursor_execute',capture)
        self.assertTrue(all(s.lstrip().startswith(('SELECT','WITH')) for s in statements))
        self.assertEqual(len(self.db.new),1)
        self.assertIs(self.db.get_transaction(),transaction)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM usuarios WHERE id=99')).scalar(),0)

    def test_exact_numerator_used_for_utilization(self):
        self.capacity(minutes=1,end='2026-11-01'); self.demand()
        self.write("UPDATE profissional_instituicoes SET data_fim='2026-11-01'")
        r = self.read()
        self.assertEqual(r['capacidade_mensal_equivalente'],'0.14')
        self.assertEqual(r['saldo_mensal'],'-44.86')
        self.assertEqual(r['utilizacao_percentual'],'31500.00')

    def test_incomplete_over_estimated(self):
        self.capacity(end='2026-11-10'); self.demand(estimated=True)
        r = self.read()
        self.assertEqual(r['qualidade_demanda'], 'ESTIMADO')
        self.assertEqual(r['qualidade'], 'INCOMPLETO')
        self.assertIsNone(r['saldo_mensal'])

    def test_multiple_conclusive_occupations_independent_rounding(self):
        self.demand(); self.capacity(minutes=1,end='2026-11-01')
        self.write("UPDATE profissional_instituicoes SET data_fim='2026-11-01'")
        self.write("INSERT INTO profissional_instituicoes VALUES (10,3,4,2,'2026-11-01','2026-11-01',true)")
        self.write("INSERT INTO capacidades_profissionais VALUES (13,10,1,'2026-11-01','2026-11-01',true)")
        self.write("INSERT INTO agenda_cuidados VALUES (2,1,1,1,2,4,1,1,45,'2026-11-01','2026-11-30','PLANEJADO')")
        self.write("INSERT INTO sessoes_assistenciais VALUES (2,2,1,'2026-11-01',null,null,45,'AGENDADA',21,4,null)")
        r = self.read()
        self.assertEqual(r['qualidade'], 'CONCLUSIVO')
        self.assertEqual([o['ocupacao_id'] for o in r['ocupacoes']], [1,2])
        self.assertEqual(r['demanda_mensal_projetada'], 90)
        self.assertEqual(sum(o['demanda_mensal_projetada'] for o in r['ocupacoes']), 90)
        # Exact numerator 2 / 7 is rounded once, not 0.14 + 0.14.
        self.assertEqual(r['capacidade_mensal_equivalente'], '0.29')
        self.assertEqual(r['saldo_mensal'], '-89.71')
        self.assertEqual(r['utilizacao_percentual'], '31500.00')
        for group in r['ocupacoes']:
            self.assertEqual(group['qualidade'], 'CONCLUSIVO')
            self.assertEqual(group['demanda_mensal_projetada'], 45)
            self.assertEqual(group['capacidade_mensal_equivalente'], '0.14')
            self.assertEqual(group['saldo_mensal'], '-44.86')
            self.assertEqual(group['utilizacao_percentual'], '31500.00')
            self.assertEqual(group['pendencias'], [])

    def test_outside_month_plan_has_no_fictitious_contribution(self):
        self.demand(occupation=2)
        self.write("UPDATE agenda_cuidados SET data_inicio='2026-12-01', data_fim='2026-12-31'")
        self.write("UPDATE sessoes_assistenciais SET data_agendada='2026-12-01'")
        r = self.read()
        # Discovery retains the occupation; the engine excludes its December plan.
        self.assertEqual([o['ocupacao_id'] for o in r['ocupacoes']], [2])
        for result in (r, r['ocupacoes'][0]):
            self.assertEqual(result['qualidade'], 'CONCLUSIVO')
            self.assertEqual(result['demanda_mensal_projetada'], 0)
            self.assertEqual(result['demanda_persistida_conhecida'], 0)
            self.assertEqual(result['demanda_estimada_conhecida'], 0)
            self.assertEqual(result['capacidade_mensal_equivalente'], '0.00')
            self.assertEqual(result['saldo_mensal'], '0.00')
            self.assertIsNone(result['utilizacao_percentual'])
            self.assertEqual(result['motivo_utilizacao_nula'], 'CAPACIDADE_ZERO')
            self.assertEqual(result['pendencias'], [])

    def test_unsupported_snapshot_fails_closed(self):
        engine = create_engine('sqlite:///:memory:')
        try:
            with Session(engine) as db:
                with self.assertRaisesRegex(ValueError, 'MONTHLY_SNAPSHOT_REQUIRES_POSTGRESQL'):
                    ConsolidacaoMensalService().calculate(db, instituicao_id=3,
                        mes_referencia='2026-11', actor_id=1)
        finally:
            engine.dispose()


if __name__ == '__main__':
    unittest.main()
