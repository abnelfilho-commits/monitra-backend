"""C2-M2 only. Synthetic SQLite in memory; never reads a configured DB URL."""
import os
import unittest
from unittest.mock import patch
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session

with patch.dict(os.environ, {'DATABASE_URL': 'sqlite:///:memory:'}):
    from app.services.institucional import InstitucionalErro
from app.services.capacidade_mensal import CapacidadeMensalService


class MonthlyCapacityTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        tables = {
            'usuarios': 'id INTEGER PRIMARY KEY, pessoa_id int, nome text, email text, senha_hash text, perfil text, clinica_id int, profissional_id int, ativo boolean',
            'instituicoes': 'id INTEGER PRIMARY KEY, ativo boolean',
            'profissionais': 'id INTEGER PRIMARY KEY, ativo boolean',
            'ocupacoes_profissionais': 'id INTEGER PRIMARY KEY, nome text, ativo boolean',
            'profissional_instituicoes': 'id INTEGER PRIMARY KEY, instituicao_id int, profissional_id int, ocupacao_id int, data_inicio date, data_fim date, ativo boolean',
            'capacidades_profissionais': 'id INTEGER PRIMARY KEY, profissional_instituicao_id int, minutos_semanais int, data_inicio date, data_fim date, ativo boolean',
        }
        with self.engine.begin() as db:
            for table, columns in tables.items():
                db.execute(text(f'CREATE TABLE {table} ({columns})'))
            db.execute(text("INSERT INTO usuarios(id,nome,email,senha_hash,perfil,ativo) VALUES (1,'Synthetic','a','x','ADMIN',1),(2,'Synthetic','b','x','GESTOR',1),(3,'Synthetic','c','x','ADMIN',0)"))
            db.execute(text('INSERT INTO instituicoes VALUES (3,1),(4,1),(5,0)'))
            db.execute(text('INSERT INTO profissionais VALUES (4,1),(5,1),(6,0)'))
            db.execute(text("INSERT INTO ocupacoes_profissionais VALUES (1,'Synthetic A',1),(2,'Synthetic B',0)"))
        self.db = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)

    def link(self, identity=9, institution=3, professional=4, occupation=1,
             start='2026-01-01', end=None, active=True):
        self.db.execute(text('INSERT INTO profissional_instituicoes VALUES (:id,:i,:p,:o,:s,:e,:a)'),
                        dict(id=identity,i=institution,p=professional,o=occupation,s=start,e=end,a=active))
        self.db.commit()

    def capacity(self, identity=12, link=9, minutes=1200, start='2026-01-01', end=None, active=True):
        self.db.execute(text('INSERT INTO capacidades_profissionais VALUES (:id,:v,:m,:s,:e,:a)'),
                        dict(id=identity,v=link,m=minutes,s=start,e=end,a=active))
        self.db.commit()

    def read(self, **changes):
        return CapacidadeMensalService().calculate(self.db, **dict(
            dict(instituicao_id=3, mes_referencia='2026-11', actor_id=1), **changes))

    def test_28_days(self):
        self.link(); self.capacity(minutes=7)
        self.assertEqual(self.read(mes_referencia='2026-02')['capacidade_mensal_total'], '28.00')

    def test_29_days(self):
        self.link(); self.capacity(minutes=7)
        self.assertEqual(self.read(mes_referencia='2028-02')['capacidade_mensal_total'], '29.00')

    def test_30_days(self):
        self.link(); self.capacity(minutes=7)
        self.assertEqual(self.read()['capacidade_mensal_total'], '30.00')

    def test_31_days(self):
        self.link(); self.capacity(minutes=7)
        self.assertEqual(self.read(mes_referencia='2026-12')['capacidade_mensal_total'], '31.00')

    def test_full_month_decimal(self):
        self.link(); self.capacity()
        r=self.read()
        self.assertEqual(r['numerador'],36000)
        self.assertEqual(r['capacidade_mensal_total'],'5142.86')

    def test_partial_link_and_declaration_intersection(self):
        self.link(start='2026-11-10',end='2026-11-20')
        self.capacity(start='2026-11-01',end='2026-12-01',minutes=7)
        r=self.read()
        self.assertEqual(r['capacidade_mensal_total'],'11.00')
        self.assertEqual(r['detalhes_vinculos'][0]['dias_elegiveis'],11)

    def test_successive_declarations(self):
        self.link(); self.capacity(minutes=7,end='2026-11-15')
        self.capacity(identity=13,minutes=14,start='2026-11-16')
        r=self.read()
        self.assertEqual(r['capacidade_mensal_total'],'45.00')
        self.assertEqual(r['vinculos'],1)
        self.assertEqual(r['profissionais_distintos'],1)

    def test_middle_gap_preserves_known(self):
        self.link(); self.capacity(minutes=7,end='2026-11-10')
        self.capacity(identity=13,minutes=7,start='2026-11-20')
        r=self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'21.00')
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertEqual(r['qualidade'],'INCOMPLETO')
        self.assertEqual(r['detalhes_vinculos'][0]['dias_sem_declaracao'],9)
        self.assertEqual(r['pendencias'][0]['data_inicio'],'2026-11-11')

    def test_missing_capacity_not_zero_declared(self):
        self.link(); r=self.read()
        self.assertEqual(r['vinculos_sem_capacidade'],1)
        self.assertEqual(r['detalhes_vinculos'][0]['dias_sem_declaracao'],30)
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertFalse(r['conclusivo'])

    def test_overlap_even_one_day(self):
        self.link(); self.capacity(end='2026-11-15')
        self.capacity(identity=13,start='2026-11-15')
        r=self.read()
        self.assertEqual(r['qualidade'],'INCONSISTENTE')
        # Only the ambiguous 15th is excluded; the other 29 days remain known.
        self.assertEqual(r['capacidade_mensal_conhecida'],'4971.43')
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertEqual(r['pendencias'][0]['codigo'],'DECLARACOES_SOBREPOSTAS')

    def test_single_day_inclusive(self):
        self.link(start='2026-11-30',end='2026-11-30')
        self.capacity(minutes=7,start='2026-11-30',end='2026-11-30')
        self.assertEqual(self.read()['capacidade_mensal_total'],'1.00')

    def test_cross_month_periods(self):
        self.link(start='2026-10-31',end='2026-12-01')
        self.capacity(minutes=7,start='2026-10-31',end='2026-12-01')
        self.assertEqual(self.read()['capacidade_mensal_total'],'30.00')

    def test_multiple_occupations_and_same_professional(self):
        self.link(); self.capacity(minutes=7)
        self.link(identity=10,occupation=2); self.capacity(identity=13,link=10,minutes=14)
        r=self.read()
        self.assertEqual((r['vinculos'],r['profissionais_distintos']),(2,1))
        self.assertEqual(r['capacidade_mensal_total'],'90.00')
        self.assertFalse(r['ocupacoes'][1]['ocupacao_ativa'])
        filtered=self.read(ocupacao_id=2)
        self.assertEqual(filtered['capacidade_mensal_total'],'60.00')
        self.assertEqual(filtered['vinculos'],1)

    def test_empty_institution(self):
        r=self.read()
        self.assertEqual(r['qualidade'],'CONCLUSIVO')
        self.assertEqual(r['capacidade_mensal_total'],'0.00')
        self.assertEqual(r['ocupacoes'],[])

    def test_no_intermediate_rounding(self):
        self.link(end='2026-11-01'); self.capacity(minutes=1)
        self.link(identity=10,professional=5,end='2026-11-01')
        self.capacity(identity=13,link=10,minutes=1)
        r=self.read()
        self.assertEqual(r['numerador'],2)
        self.assertEqual(r['capacidade_mensal_total'],'0.29')

    def test_zero_invalid(self):
        self.link(); self.capacity(minutes=0)
        self.assertEqual(self.read()['qualidade'],'INCONSISTENTE')

    def test_reversed_capacity_period(self):
        self.link(); self.capacity(start='2026-11-20',end='2026-11-10')
        self.assertEqual(self.read()['qualidade'],'INCONSISTENTE')

    def test_reversed_link_period(self):
        self.link(start='2026-11-20',end='2026-11-10')
        self.assertEqual(self.read()['qualidade'],'INCONSISTENTE')

    def test_invalidated_capacity_is_absent(self):
        self.link(); self.capacity(active=False)
        self.assertEqual(self.read()['qualidade'],'INCOMPLETO')

    def test_current_inactive_parents_excluded(self):
        self.link(active=False); self.capacity()
        self.link(identity=10,professional=6); self.capacity(identity=13,link=10)
        self.assertEqual(self.read()['vinculos'],0)

    def test_institution_isolation(self):
        self.link(); self.capacity(minutes=7)
        self.link(identity=10,institution=4); self.capacity(identity=13,link=10,minutes=70)
        self.assertEqual(self.read()['capacidade_mensal_total'],'30.00')
        self.assertEqual(self.read(instituicao_id=4)['capacidade_mensal_total'],'300.00')

    def test_admin_denials(self):
        for actor in (2,3,999):
            with self.subTest(actor=actor), self.assertRaises(InstitucionalErro) as caught:
                self.read(actor_id=actor)
            self.assertEqual(caught.exception.code,'ADMIN_REQUIRED')

    def test_invalid_institutions(self):
        for institution, code in ((5,'CAPACITY_INSTITUTION_INACTIVE'),(999,'CAPACITY_INSTITUTION_NOT_FOUND')):
            with self.subTest(institution=institution), self.assertRaises(InstitucionalErro) as caught:
                self.read(instituicao_id=institution)
            self.assertEqual(caught.exception.code,code)

    def test_read_only_even_pending_orm_write(self):
        from app.models.usuario import Usuario
        self.db.add(Usuario(id=99,nome='Pending',email='pending',senha_hash='x',perfil='ADMIN',ativo=True))
        statements=[]
        event.listen(self.engine,'before_cursor_execute',lambda conn,cursor,stmt,args,ctx,many: statements.append(stmt))
        self.read()
        self.assertEqual(len(statements),2)
        self.assertTrue(all(s.lstrip().startswith(('SELECT','WITH')) for s in statements))
        self.assertEqual(len(self.db.new),1)
        self.db.rollback()

    def test_inconsistent_link_does_not_erase_sound_subtotal(self):
        self.link(); self.capacity(minutes=7)
        self.link(identity=10,professional=5); self.capacity(identity=13,link=10,minutes=-1)
        r=self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'30.00')
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertEqual(r['vinculos_inconsistentes'],1)

    def test_input_validation(self):
        for changes in ({'instituicao_id':True},{'ocupacao_id':0},{'mes_referencia':'2026-1'}, {'mes_referencia':'2026-13'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.read(**changes)

    def test_leading_and_trailing_gaps(self):
        self.link(); self.capacity(start='2026-11-10',end='2026-11-20',minutes=7)
        r=self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'11.00')
        self.assertEqual(r['detalhes_vinculos'][0]['dias_sem_declaracao'],19)
        self.assertEqual(len(r['pendencias']),2)
        self.assertEqual(r['vinculos_com_capacidade'],1)
        self.assertEqual(r['vinculos_com_lacunas'],1)

    def test_outside_month_links_and_declarations(self):
        self.link(); self.capacity(start='2026-12-01')
        self.link(identity=10,start='2026-12-01')
        self.capacity(identity=13,link=10,start='2026-12-01')
        r=self.read()
        self.assertEqual(r['vinculos'],1)
        self.assertEqual(r['vinculos_sem_capacidade'],1)
        self.assertEqual(r['qualidade'],'INCOMPLETO')

    def test_missing_occupation_is_not_silently_dropped(self):
        self.link(occupation=999); self.capacity()
        r=self.read()
        self.assertEqual(r['qualidade'],'INCONSISTENTE')
        self.assertEqual(r['pendencias'][0]['codigo'],'IDENTIDADE_INCONSISTENTE')

    def test_last_date_no_successor_overflow(self):
        self.link(start='9999-12-31'); self.capacity(start='9999-12-31',minutes=7)
        r=self.read(mes_referencia='9999-12')
        self.assertEqual(r['capacidade_mensal_total'],'1.00')

    def test_valid_and_invalid_separate_periods_same_link(self):
        self.link(); self.capacity(minutes=7,end='2026-11-10')
        self.capacity(identity=13,minutes=-1,start='2026-11-20')
        r=self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'10.00')
        self.assertEqual(r['qualidade'],'INCONSISTENTE')
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertTrue(any(p['codigo']=='DIAS_SEM_DECLARACAO' and p['dias']==9 for p in r['pendencias']))

    def test_local_overlap_preserves_both_unambiguous_tails(self):
        self.link(); self.capacity(minutes=7,end='2026-11-20')
        self.capacity(identity=13,minutes=14,start='2026-11-10')
        r=self.read()
        self.assertEqual(r['numerador'],9*7+10*14)
        self.assertEqual(r['capacidade_mensal_conhecida'],'29.00')
        self.assertIsNone(r['capacidade_mensal_total'])

    def test_invalid_value_outside_eligible_window_is_irrelevant(self):
        self.link(start='2026-11-10',end='2026-11-20')
        self.capacity(minutes=7,start='2026-11-10',end='2026-11-20')
        self.capacity(identity=13,minutes=-1,start='2026-11-01',end='2026-11-05')
        r=self.read()
        self.assertEqual(r['capacidade_mensal_total'],'11.00')
        self.assertEqual(r['pendencias'],[])

    def test_unlocatable_invalid_dates_block_whole_link(self):
        self.link(); self.capacity(minutes=7)
        self.capacity(identity=13,start=None)
        r=self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'0.00')
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertEqual(r['pendencias'][0]['relevancia_temporal'],'INDETERMINADA')

    def test_inconsistent_occupation_preserves_other_occupation(self):
        self.link(); self.capacity(minutes=1,end='2026-11-01')
        self.capacity(identity=13,minutes=-1,start='2026-11-02')
        self.link(identity=10,occupation=2,start='2026-11-01',end='2026-11-01')
        self.capacity(identity=14,link=10,minutes=1)
        r=self.read()
        self.assertEqual(r['numerador'],2)
        self.assertEqual(r['capacidade_mensal_conhecida'],'0.29')
        self.assertIsNone(r['capacidade_mensal_total'])
        self.assertEqual(r['ocupacoes'][1]['qualidade'],'CONCLUSIVO')
        self.assertEqual(r['ocupacoes'][1]['capacidade_mensal_total'],'0.14')

    def test_invalid_interval_masks_valid_declaration_only_locally(self):
        self.link(); self.capacity(minutes=7)
        self.capacity(identity=13,minutes=0,start='2026-11-10',end='2026-11-20')
        r=self.read()
        self.assertEqual(r['capacidade_mensal_conhecida'],'19.00')
        self.assertEqual(r['qualidade'],'INCONSISTENTE')


if __name__ == '__main__':
    unittest.main()
