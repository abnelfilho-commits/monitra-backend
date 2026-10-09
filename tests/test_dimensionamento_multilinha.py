"""Transversal planned demand against disposable PostgreSQL and actual views."""
import os
import unittest
from unittest.mock import patch
from sqlalchemy import text
import test_planejamento_mental as foundation
from app.core.security import criar_access_token
from app.routers.dimensionamento import router


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class DimensionamentoTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.PlanningTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.PlanningTests.tearDownClass.__func__)
    tearDown = foundation.PlanningTests.tearDown
    command_grant = foundation.PlanningTests.command_grant
    path = foundation.PlanningTests.path
    request = foundation.PlanningTests.request
    create = foundation.PlanningTests.create

    def setUp(self):
        foundation.PlanningTests.setUp(self)
        self.db.execute(text("DELETE FROM agenda_cuidados"))
        self.db.commit()
        self.app.include_router(router)
        self.headers = {'Authorization': 'Bearer ' + criar_access_token({'sub': str(self.actor), 'tipo': 'usuario'})}
        self.db.execute(text("UPDATE modulos_clinicos SET slug='neurodesenvolvimento' WHERE id=1"))
        self.db.execute(text("INSERT INTO modulos_clinicos(id,nome,slug,ativo) VALUES (2,'Cardio','cardiometabolico',true) ON CONFLICT(id) DO UPDATE SET slug=EXCLUDED.slug"))
        self.db.execute(text("UPDATE ocupacoes_profissionais SET nome='Psicólogo' WHERE id=:o"), dict(o=self.occupation))
        self.db.execute(text("UPDATE atividades_terapeuticas SET nome='Psicoterapia individual' WHERE id=:a"), dict(a=self.activity))
        self.db.commit()
        response = self.request('POST', self.suffix, dict(self.payload, frequencia_semanal=1, duracao_minutos=45))
        self.assertEqual(response.status_code, 201, response.text)
        self.agenda = response.json()['id']

    def read(self, linha='todas', **params):
        response = self.client.request('GET', '/dimensionamento/ocupacoes', headers=self.headers, params=dict(linha=linha, **params))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def legacy(self, module, duration):
        plan = self.db.scalar(text("INSERT INTO pts(paciente_id,modulo_id,status) SELECT paciente_id,:m,'ENCERRADO' FROM pts WHERE id=:p RETURNING id"), dict(m=module, p=self.plan))
        objective = self.db.scalar(text("INSERT INTO pts_objetivos(pts_id,descricao) VALUES (:p,'Synthetic legacy') RETURNING id"), dict(p=plan))
        self.db.execute(text("""INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio,status)
            VALUES (:p,:ob,:a,:o,1,:d,'2020-01-01','PLANEJADO')"""), dict(p=plan, ob=objective, a=self.activity, o=self.occupation, d=duration))
        self.db.commit()

    def test_concrete_planning_without_schedule_sessions_or_clinical_data(self):
        result = self.read('saude_mental')
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], dict(ocupacao_id=self.occupation, ocupacao_nome='Psicólogo', total_planejamentos=1,
            minutos_semanais=45, horas_semanais=0.75, horas_mensais=3.25, horas_anuais=39, fte=0.02))
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM sessoes_assistenciais')), 0)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM registros_longitudinais')), 0)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM vw_dimensionamento_ocupacao')), 0)

    def test_legacy_neuro_cardio_equivalence_and_todas_consolidates(self):
        self.legacy(1, 300); self.legacy(2, 120)
        for module, slug, hours in [(1, 'neurodesenvolvimento', 5), (2, 'cardiometabolico', 2)]:
            old = self.client.get('/dimensionamento/ocupacoes', params=dict(modulo_id=module))
            self.assertEqual(old.status_code, 200, old.text)
            expected = [{k: v for k, v in row.items() if k != 'modulo_id'} for row in old.json()]
            self.assertEqual(self.read(slug), expected)
            self.assertEqual(expected[0]['horas_semanais'], hours)
        self.assertEqual(self.read('saude_mental')[0]['horas_semanais'], .75)
        total = self.read()
        self.assertEqual(len(total), 1)
        self.assertEqual((total[0]['total_planejamentos'], total[0]['horas_semanais'], total[0]['horas_mensais'], total[0]['horas_anuais'], total[0]['fte']), (3, 7.75, 33.56, 403, .19))
        self.assertEqual(len(self.client.get('/dimensionamento/ocupacoes').json()), 2)

    def test_multiline_activity_never_multiplies_and_multiple_plannings_sum(self):
        self.db.execute(text('INSERT INTO atividade_modulos(atividade_id,modulo_id) VALUES (:a,1),(:a,2),(:a,3)'), dict(a=self.activity))
        self.db.commit()
        self.assertEqual(self.read()[0]['total_planejamentos'], 1)
        response = self.request('POST', self.suffix, dict(self.payload, frequencia_semanal=2, duracao_minutos=45))
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual((self.read()[0]['total_planejamentos'], self.read()[0]['horas_semanais']), (2, 2.25))
        self.legacy(1, 300)
        self.assertEqual((self.read()[0]['total_planejamentos'], self.read()[0]['horas_semanais']), (3, 7.25))

    def test_other_occupation_has_independent_group(self):
        occupation = self.db.scalar(text("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Terapeuta sintético') RETURNING id"))
        self.db.execute(text("""INSERT INTO agenda_cuidados(pts_id,objetivo_id,atividade_id,ocupacao_id,frequencia_semanal,duracao_minutos,data_inicio)
            VALUES (:p,:ob,:a,:o,2,60,CURRENT_DATE)"""), dict(p=self.plan, ob=self.objective, a=self.activity, o=occupation))
        self.db.commit()
        rows = self.read('saude_mental')
        self.assertEqual([r['ocupacao_id'] for r in rows], [occupation, self.occupation])
        self.assertEqual([r['horas_semanais'] for r in rows], [2, .75])
        self.assertEqual([r['total_planejamentos'] for r in rows], [1, 1])

    def test_contextual_eligibility_and_no_inference_from_activity(self):
        mutations = [
            ("UPDATE agenda_cuidados SET status='CANCELADO' WHERE id=:id", self.agenda),
            ("UPDATE pts SET status='ENCERRADO' WHERE id=:id", self.plan),
            ('UPDATE contextos_assistenciais SET ativo=false WHERE id=:id', self.open),
            ('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:id', self.open),
            ('UPDATE paciente_instituicoes SET ativo=false WHERE id=(SELECT paciente_instituicao_id FROM contextos_assistenciais WHERE id=:id)', self.open),
            ('UPDATE instituicoes SET ativo=false WHERE id=:id', self.institutions[0]),
            ('UPDATE modulos_clinicos SET ativo=false WHERE id=:id', 3),
            ('UPDATE atividades_terapeuticas SET modulo_id=1 WHERE id=:id', self.activity),
        ]
        for sql, identity in mutations:
            with self.subTest(sql=sql):
                self.db.execute(text(sql), dict(id=identity))
                self.assertEqual(self.read('saude_mental'), [])
                self.db.rollback()
        self.db.execute(text('INSERT INTO atividade_modulos(atividade_id,modulo_id) VALUES (:a,1)'), dict(a=self.activity))
        self.assertEqual(self.read('saude_mental'), [])
        self.db.rollback()
        self.db.execute(text('UPDATE pts SET contexto_assistencial_id=NULL WHERE id=:p'), dict(p=self.plan))
        self.assertEqual(self.read('saude_mental'), [])
        self.assertEqual(self.read(), [])

    def test_recurring_quantity_not_realized_sessions_or_period_proration(self):
        before = self.read()
        self.db.execute(text("UPDATE agenda_cuidados SET quantidade_sessoes=1,data_inicio='2030-01-01',data_fim='2030-01-02' WHERE id=:a"), dict(a=self.agenda))
        self.assertEqual(self.read(), before)

    def test_read_only_and_capacity_not_integrated(self):
        self.legacy(1, 300)
        before = list(self.db.execute(text('SELECT * FROM vw_demanda_capacidade')).mappings())
        self.assertTrue(before)
        self.assertTrue(all(row['capacidade_horas_ano'] == 0 for row in before))
        with self.db.no_autoflush, patch.object(self.db, 'commit', side_effect=AssertionError('GET commit')), patch.object(self.db, 'flush', side_effect=AssertionError('GET flush')):
            rows = self.read()
        self.assertTrue(all(set(row) == {'ocupacao_id','ocupacao_nome','total_planejamentos','minutos_semanais','horas_semanais','horas_mensais','horas_anuais','fte'} for row in rows))
        self.assertEqual(list(self.db.execute(text('SELECT * FROM vw_demanda_capacidade')).mappings()), before)

    def test_active_account_required_and_invalid_filters_rejected(self):
        path = '/dimensionamento/ocupacoes'
        for headers in ({}, {'Authorization': 'Bearer invalid'}):
            self.assertEqual(self.client.request('GET', path, params=dict(linha='todas'), headers=headers).status_code, 401)
        for params in (dict(linha='unknown'), dict(linha='saude_mental', modulo_id=1)):
            self.assertEqual(self.client.request('GET', path, params=params, headers=self.headers).status_code, 422)
        self.db.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'), dict(id=self.actor))
        self.db.expire_all()
        self.assertEqual(self.client.request('GET', path, params=dict(linha='todas'), headers=self.headers).status_code, 401)
