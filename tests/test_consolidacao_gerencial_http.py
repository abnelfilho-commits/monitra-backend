"""HTTP C2-M4 only, synthetic PostgreSQL fixture from C2-M3 (port 55743).

Uses real JWT decoding and ADMIN dependencies; no login or external environment.
Run unittest discover -s tests -p test_consolidacao_gerencial_http.py -v.
The measurement is a small local sample, not a production capacity benchmark.
"""
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Lock, Barrier
from unittest.mock import patch

import test_consolidacao_mensal as fixture
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core import deps
from app.database import get_db
from app.routers import consolidacao_gerencial as api
from app.services.demanda_mensal import DemandaMensalService

PATH = '/admin/consolidacao-gerencial/mensal'
SECRET = 'only-local-synthetic-c2m4-test-key'


class ManagementHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ConsolidacaoTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.engine = self.fixture.engine
        self.app = FastAPI()
        self.app.include_router(api.router)
        def database():
            with Session(self.engine) as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        self.secret = patch.object(deps, 'SECRET_KEY', SECRET)
        self.secret.start()
        self.addCleanup(self.secret.stop)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    def token(self, actor=1, expired=False, secret=SECRET):
        return jwt.encode({'sub': str(actor), 'tipo': 'usuario',
            'exp': datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 5)},
            secret, algorithm=deps.ALGORITHM)

    def get(self, actor=1, params=None, token=None):
        query = dict(instituicao_id=3, mes_referencia='2026-11')
        if params:
            query.update(params)
        return self.client.get(PATH, params=query,
            headers={'Authorization': 'Bearer ' + (token or self.token(actor))})

    def test_authentication_real_jwt(self):
        self.assertEqual(self.client.get(PATH).status_code,401)
        for token in ('invalid', self.token(expired=True), self.token(secret='wrong-key')):
            response = self.get(token=token)
            self.assertEqual(response.status_code,401)
            self.assertEqual(response.headers['www-authenticate'],'Bearer')

    def test_admin_inactive_and_gestor_denied(self):
        with patch.object(api.service,'calculate') as service:
            self.assertEqual(self.get(actor=2).status_code,403)
            self.assertEqual(self.get(actor=3).status_code,401)
            self.assertEqual(self.get(actor=999).status_code,401)
            service.assert_not_called()

    def test_institutions(self):
        self.assertEqual(self.get().status_code,200)
        self.assertEqual(self.get(params={'instituicao_id':5}).status_code,409)
        self.assertEqual(self.get(params={'instituicao_id':999}).status_code,404)

    def test_parameter_validation(self):
        for params in ({'mes_referencia':'2026-13'},{'mes_referencia':'0000-01'},
                       {'mes_referencia':'2026-1'},{'instituicao_id':0},
                       {'ocupacao_id':-1},{'instituicao_id':'sensitive-invalid'}):
            response = self.get(params=params)
            self.assertEqual(response.status_code,422)
            self.assertEqual(response.json(),{'detail':{'code':'INVALID_MONTHLY_PARAMETERS'}})
        self.assertEqual(self.client.get(PATH,headers={'Authorization':'Bearer '+self.token()}).status_code,422)

    def test_actor_cannot_be_supplied_by_client(self):
        with patch.object(api.service,'calculate',wraps=api.service.calculate) as service:
            self.assertEqual(self.get(params={'actor_id':2}).status_code,200)
            self.assertEqual(service.call_args.kwargs['actor_id'],1)

    def test_json_decimals_and_filter(self):
        self.fixture.demand(); self.fixture.capacity(occupation=2)
        response = self.get()
        self.assertEqual(response.status_code,200,response.text)
        result = response.json()
        self.assertEqual(result['saldo_mensal'],'-15.00')
        self.assertEqual(result['utilizacao_percentual'],'150.00')
        self.assertEqual(result['unidade'],'MINUTOS_MENSAIS')
        self.assertEqual([o['ocupacao_id'] for o in result['ocupacoes']],[1,2])
        filtered = self.get(params={'ocupacao_id':2}).json()
        self.assertEqual(filtered['demanda_mensal_projetada'],0)
        self.assertEqual([o['ocupacao_id'] for o in filtered['ocupacoes']],[2])
        self.assertEqual(result['motivos_nao_calculaveis']['saldo_mensal'],[])

    def test_openapi(self):
        response = self.client.get('/openapi.json')
        self.assertEqual(response.status_code,200)
        contract = response.json()
        operation = contract['paths'][PATH]['get']
        self.assertTrue(operation['security'])
        params = {p['name']:p for p in operation['parameters']}
        self.assertTrue(params['instituicao_id']['required'])
        self.assertTrue(params['mes_referencia']['required'])
        self.assertFalse(params['ocupacao_id']['required'])
        self.assertNotIn('actor_id',params)
        self.assertIn('MonthlyManagementResponse',contract['components']['schemas'])

    def test_estimated_and_zero(self):
        self.fixture.demand(estimated=True)
        r = self.get().json()
        self.assertEqual(r['qualidade'],'ESTIMADO')
        self.assertIsNone(r['utilizacao_percentual'])
        self.assertEqual(r['motivo_utilizacao_nula'],'CAPACIDADE_ZERO')
        self.assertEqual(r['motivos_nao_calculaveis']['utilizacao_percentual'],['CAPACIDADE_ZERO'])

    def test_multiple_causes_and_nulls(self):
        self.fixture.demand(); self.fixture.capacity(end='2026-11-10')
        self.fixture.write('UPDATE agenda_cuidados SET quantidade_sessoes=2')
        r = self.get().json()
        self.assertEqual(r['qualidade'],'INCOMPLETO')
        self.assertEqual(r['capacidade_mensal_conhecida'],'10.00')
        self.assertIsNone(r['demanda_mensal_projetada'])
        self.assertIsNone(r['capacidade_mensal_equivalente'])
        self.assertIsNone(r['saldo_mensal'])
        for field in ('saldo_mensal','utilizacao_percentual'):
            self.assertEqual(r['motivos_nao_calculaveis'][field],
                ['DEMANDA_NAO_CALCULAVEL','CAPACIDADE_NAO_CONCLUSIVA'])

    def test_inconsistent_and_privacy(self):
        self.fixture.capacity(minutes=-1)
        r = self.get().json()
        self.assertEqual(r['qualidade'],'INCONSISTENTE')
        self.assertEqual(set(r['pendencias'][0]),{'origem','codigo','quantidade'})
        for forbidden in ('profissional_id','paciente_id','vinculo_id','capacidade_id','sessao_id','agenda_id'):
            self.assertNotIn(forbidden,json.dumps(r))

    def test_zero_and_uncalculable_demand_both_preserved(self):
        self.fixture.demand()
        self.fixture.write('UPDATE agenda_cuidados SET quantidade_sessoes=2')
        r = self.get().json()
        self.assertEqual(r['motivos_nao_calculaveis']['utilizacao_percentual'],
                         ['DEMANDA_NAO_CALCULAVEL','CAPACIDADE_ZERO'])

    def test_schema_failures_sanitized(self):
        original = api.service.calculate
        for mode in ('extra','type','nested'):
            def invalid(*args,**kwargs):
                result = original(*args,**kwargs)
                if mode == 'extra': result['paciente_nome']='PRIVATE_TEST_SENTINEL'
                if mode == 'type': result['demanda_mensal_projetada']='PRIVATE_TEST_SENTINEL'
                if mode == 'nested': result['pendencias']=[{'origem':'DEMANDA','codigo':'OK','quantidade':1,'agenda_id':21}]
                return result
            with self.subTest(mode=mode), patch.object(api.service,'calculate',side_effect=invalid):
                response = self.get()
                self.assertEqual(response.status_code,500)
                self.assertEqual(response.json(),{'detail':{'code':'MONTHLY_CONSOLIDATION_FAILED'}})

    def test_calculation_failure_sanitized(self):
        with patch.object(api.service,'calculate',side_effect=ValueError('PRIVATE_TEST_SENTINEL SQL')):
            response = self.get()
            self.assertEqual(response.status_code,500)
            self.assertNotIn('PRIVATE_TEST_SENTINEL',response.text)

    def test_bank_failure_sanitized(self):
        error = OperationalError('SELECT PRIVATE_TEST_SENTINEL', {'secret':'PRIVATE_TEST_SENTINEL'}, Exception('PRIVATE_TEST_SENTINEL'))
        with patch.object(api.service,'calculate',side_effect=error):
            response = self.get()
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json(),{'detail':{'code':'MONTHLY_CONSOLIDATION_UNAVAILABLE'}})

    def test_dependency_failure_sanitized(self):
        def failed_database():
            raise OperationalError('PRIVATE_TEST_SENTINEL',{},Exception('PRIVATE_TEST_SENTINEL'))
        self.app.dependency_overrides[get_db] = failed_database
        response = self.get()
        self.assertEqual(response.status_code,503)
        self.assertNotIn('PRIVATE_TEST_SENTINEL',response.text)

    def test_snapshot_consistent_http(self):
        self.fixture.demand(); self.fixture.capacity()
        original = DemandaMensalService.calculate
        changed = False
        def concurrent(service,*args,**kwargs):
            nonlocal changed
            result = original(service,*args,**kwargs)
            if not changed:
                self.fixture.write('UPDATE capacidades_profissionais SET minutos_semanais=14')
                changed = True
            return result
        with patch.object(DemandaMensalService,'calculate',concurrent):
            r = self.get().json()
            self.assertEqual(r['capacidade_mensal_equivalente'],'30.00')
            self.assertEqual(r['ocupacoes'][0]['capacidade_mensal_equivalente'],'30.00')
        self.assertEqual(self.get().json()['capacidade_mensal_equivalente'],'60.00')

    def test_no_writes_and_caller_transaction_preserved(self):
        db = self.fixture.db
        db.execute(text('SELECT 1'))
        transaction = db.get_transaction()
        self.app.dependency_overrides[get_db] = lambda: db
        statements = []
        def capture(c,cur,sql,p,ctx,many): statements.append(sql)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            self.assertEqual(self.get().status_code,200)
            with patch.object(api.service,'calculate',side_effect=ValueError('PRIVATE_TEST_SENTINEL')):
                self.assertEqual(self.get().status_code,500)
        finally:
            event.remove(self.engine,'before_cursor_execute',capture)
        self.assertIs(db.get_transaction(),transaction)
        self.assertTrue(transaction.is_active)
        self.assertTrue(all(s.lstrip().startswith(('SELECT','WITH')) for s in statements))

    def test_isolation_two_populated_institutions(self):
        self.fixture.demand(); self.fixture.capacity()
        self.fixture.write("INSERT INTO profissional_instituicoes VALUES (10,4,4,2,'2026-01-01',null,true)")
        self.fixture.write("INSERT INTO capacidades_profissionais VALUES (13,10,14,'2026-01-01',null,true)")
        self.assertEqual(self.get().json()['capacidade_mensal_equivalente'],'30.00')
        other = self.get(params={'instituicao_id':4}).json()
        self.assertEqual(other['capacidade_mensal_equivalente'],'60.00')
        self.assertEqual(other['demanda_mensal_projetada'],0)
        self.assertEqual([o['ocupacao_id'] for o in other['ocupacoes']],[2])

    def test_operational_measurement(self):
        # Persisted schedules: 10 per occupation, 10 sessions each; no clinical text.
        self.fixture.write("INSERT INTO ocupacoes_profissionais SELECT x,'Synthetic',true FROM generate_series(3,20) x")
        self.fixture.write("INSERT INTO agenda_cuidados SELECT x,1,1,x,((x-1)/10)+1,4,1,10,45,'2026-11-01','2026-11-30','PLANEJADO' FROM generate_series(1,200) x")
        self.fixture.write("INSERT INTO sessoes_assistenciais SELECT (a.id-1)*10+d,a.id,d,DATE '2026-11-01'+d-1,null,null,45,'AGENDADA',21,4,null FROM agenda_cuidados a CROSS JOIN generate_series(1,10) d")
        lock = Lock()
        stats = {'sql':0,'active':0,'peak':0}
        def sql(*args):
            with lock: stats['sql'] += 1
        def checkout(*args):
            with lock:
                stats['active'] += 1
                stats['peak'] = max(stats['peak'],stats['active'])
        def checkin(*args):
            with lock: stats['active'] -= 1
        event.listen(self.engine,'before_cursor_execute',sql)
        event.listen(self.engine,'checkout',checkout)
        event.listen(self.engine,'checkin',checkin)
        measurements = []
        try:
            for occupations in (1,20):
                stats.update(sql=0,peak=0)
                start = time.perf_counter()
                response = self.get(params={'ocupacao_id':1} if occupations == 1 else {})
                elapsed = time.perf_counter()-start
                self.assertEqual(response.status_code,200,response.text)
                measurements.append(dict(occupations=occupations,plans=10*occupations,sessions=100*occupations,
                    seconds=round(elapsed,4),sql=stats['sql'],peak_connections=stats['peak']))
            stats.update(sql=0,peak=0)
            start = time.perf_counter()
            with ThreadPoolExecutor(max_workers=4) as pool:
                responses = list(pool.map(lambda _:self.get(),range(4)))
            self.assertTrue(all(r.status_code==200 for r in responses))
            measurements.append(dict(concurrent_requests=4,occupations=20,seconds=round(time.perf_counter()-start,4),
                                     sql=stats['sql'],peak_connections=stats['peak']))
            self.assertEqual(stats['active'],0)
        finally:
            event.remove(self.engine,'before_cursor_execute',sql)
            event.remove(self.engine,'checkout',checkout)
            event.remove(self.engine,'checkin',checkin)
        print('C2M4_SYNTHETIC_MEASUREMENT '+json.dumps(measurements))

    def limited_pool(self, size, timeout=0.25):
        engine = create_engine(fixture.URL, pool_size=size, max_overflow=0,
            pool_timeout=timeout, connect_args={'options':'-csearch_path='+self.fixture.schema})
        self.addCleanup(engine.dispose)
        def database():
            with Session(engine) as db:
                yield db
        self.app.dependency_overrides[get_db] = database
        return engine

    def test_documented_error_envelopes(self):
        document = self.client.get('/openapi.json').json()
        responses = document['paths'][PATH]['get']['responses']
        for code in ('401','403','404','409','422','500','503'):
            self.assertIn('application/json',responses[code]['content'])
        self.assertIn('WWW-Authenticate',responses['401']['headers'])
        self.assertIn('anyOf',responses['403']['content']['application/json']['schema'])
        self.assertEqual(responses['422']['content']['application/json']['schema']['$ref'],
                         '#/components/schemas/ManagementErrorResponse')

    def test_admin_revoked_after_authentication(self):
        original = api.service.calculate
        def revoke(*args,**kwargs):
            self.fixture.write('UPDATE usuarios SET ativo=false WHERE id=1')
            return original(*args,**kwargs)
        with patch.object(api.service,'calculate',side_effect=revoke), \
                patch.object(DemandaMensalService,'calculate') as demand:
            response = self.get()
            self.assertEqual(response.status_code,403)
            self.assertEqual(response.json(),{'detail':{'code':'ADMIN_REQUIRED'}})
            demand.assert_not_called()

    def test_two_institutions_with_demand_and_capacity(self):
        self.fixture.demand(); self.fixture.capacity()
        for sql in (
            "INSERT INTO paciente_instituicoes VALUES (10,22,4,true,'2026-01-01',null)",
            "INSERT INTO contextos_assistenciais VALUES (3,22,4,10,true,'2026-01-01',null)",
            "INSERT INTO pts VALUES (2,22,3,3,'2026-01-01',null,'ATIVO')",
            "INSERT INTO pts_objetivos VALUES (2,2,'ABERTO')",
            "INSERT INTO agenda_cuidados VALUES (2,2,2,2,2,4,1,1,60,'2026-11-01','2026-11-30','PLANEJADO')",
            "INSERT INTO sessoes_assistenciais VALUES (2,2,1,'2026-11-01',null,null,60,'AGENDADA',22,4,null)",
            "INSERT INTO profissional_instituicoes VALUES (10,4,4,2,'2026-01-01',null,true)",
            "INSERT INTO capacidades_profissionais VALUES (13,10,14,'2026-01-01',null,true)",
        ): self.fixture.write(sql)
        first, second = self.get().json(), self.get(params={'instituicao_id':4}).json()
        self.assertEqual((first['demanda_mensal_projetada'],first['capacidade_mensal_equivalente']),(45,'30.00'))
        self.assertEqual((second['demanda_mensal_projetada'],second['capacidade_mensal_equivalente']),(60,'60.00'))
        self.assertEqual([o['ocupacao_id'] for o in first['ocupacoes']],[1])
        self.assertEqual([o['ocupacao_id'] for o in second['ocupacoes']],[2])

    def test_real_read_timeout_releases_snapshot(self):
        engine = self.limited_pool(2)
        def timeout(service, reader, **kwargs):
            reader.execute(text("SET LOCAL statement_timeout = '10ms'"))
            reader.execute(text('SELECT pg_sleep(0.1) /* PRIVATE_TEST_SENTINEL */'))
        with patch.object(DemandaMensalService,'calculate',timeout):
            response = self.get()
        self.assertEqual(response.status_code,503)
        self.assertEqual(response.json(),{'detail':{'code':'MONTHLY_CONSOLIDATION_UNAVAILABLE'}})
        self.assertEqual(engine.pool.checkedout(),0)
        self.assertEqual(self.get().status_code,200)
        self.assertEqual(engine.pool.checkedout(),0)

    def test_limited_pool_concurrent_timeout_and_recovery(self):
        engine = self.limited_pool(2)
        barrier = Barrier(2,timeout=5)
        original = api.service.calculate
        def synchronized(*args,**kwargs):
            barrier.wait()  # Both authenticated requests hold their first connection.
            return original(*args,**kwargs)
        start = time.perf_counter()
        with patch.object(api.service,'calculate',side_effect=synchronized):
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _:self.get(),range(2)))
        self.assertIn(503,[r.status_code for r in responses])
        self.assertTrue(all(r.status_code in (200,503) for r in responses))
        for response in responses:
            if response.status_code==503:
                self.assertEqual(response.json(),{'detail':{'code':'MONTHLY_CONSOLIDATION_UNAVAILABLE'}})
        self.assertEqual(engine.pool.checkedout(),0)
        self.assertEqual(self.get().status_code,200)
        self.assertEqual(engine.pool.checkedout(),0)
        print('C2M4_POOL_RECOVERY '+json.dumps(dict(pool_size=2,max_overflow=0,pool_timeout=0.25,
            statuses=[r.status_code for r in responses],seconds=round(time.perf_counter()-start,4),checkedout=0)))

    def test_long_estimates_limited_pool_measurement(self):
        self.fixture.write("INSERT INTO ocupacoes_profissionais VALUES (3,'Synthetic',true),(4,'Synthetic',true)")
        self.fixture.write("INSERT INTO agenda_cuidados SELECT x,1,1,x,x,4,5000,5000,45,'2026-11-01','2026-11-30','PLANEJADO' FROM generate_series(1,4) x")
        engine = self.limited_pool(4,timeout=2)
        lock = Lock()
        stats = {'sql':0,'active':0,'peak':0}
        def sql(*args):
            with lock: stats['sql']+=1
        def checkout(*args):
            with lock:
                stats['active']+=1
                stats['peak']=max(stats['peak'],stats['active'])
        def checkin(*args):
            with lock: stats['active']-=1
        event.listen(engine,'before_cursor_execute',sql)
        event.listen(engine,'checkout',checkout)
        event.listen(engine,'checkin',checkin)
        def sample(_):
            start=time.perf_counter()
            response=self.get()
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['demanda_mensal_projetada'],900000)
            self.assertEqual(response.json()['qualidade'],'ESTIMADO')
            return round(time.perf_counter()-start,4)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                latencies=list(pool.map(sample,range(8)))
            self.assertEqual(engine.pool.checkedout(),0)
        finally:
            event.remove(engine,'before_cursor_execute',sql)
            event.remove(engine,'checkout',checkout)
            event.remove(engine,'checkin',checkin)
        ordered=sorted(latencies)
        print('C2M4_ESTIMATES_MEASUREMENT '+json.dumps(dict(pool_size=4,max_overflow=0,pool_timeout=2,
            concurrency=2,samples=8,occupations=4,estimated_occurrences=20000,latencies_seconds=latencies,
            median_seconds=round((ordered[3]+ordered[4])/2,4),sql=stats['sql'],peak_connections=stats['peak'],
            limitation='Small local sample; no tail percentile or production limit inferred')))


if __name__ == '__main__':
    unittest.main()
