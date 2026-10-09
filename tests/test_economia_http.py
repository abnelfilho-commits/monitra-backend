"""AE1: real PostgreSQL, JWT and HTTP, with rollback and usage guards."""
import json
import os
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy import text, event
from app.database import get_db
from app.core.security import criar_access_token
from app.main import app as main_app
from app.routers import economia as api
from test_whatsapp_security import LocalClient
import test_financeiro_postgres as fixtures

PREFIX = '/admin/economia/servicos'


class RoutesTests(unittest.TestCase):
    def test_registered_admin_routes(self):
        self.assertEqual({(m, r.path[len(PREFIX):]) for r in main_app.routes
                          if r.path.startswith(PREFIX) for m in r.methods},
                         {('GET', '/'), ('POST', '/'), ('GET', '/{servico_id}'),
                          ('PUT', '/{servico_id}'), ('PATCH', '/{servico_id}/estado')})


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class EconomicHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.FinancialPostgresTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): fixtures.FinancialPostgresTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixtures.FinancialPostgresTests.setUp(self)
        self.app = FastAPI()
        self.app.include_router(api.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = LocalClient(self.app)
        self.users = {'ADMIN': self.actor}
        with self.engine.begin() as c:
            for role in ('ADMIN_CLINICA', 'PROFISSIONAL', 'SUPORTE', 'GESTOR', 'ADMINISTRADOR'):
                self.users[role] = c.execute(text("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES ('Synthetic',:e,'synthetic',:r,true) RETURNING id"), {'e': role+'@example.invalid', 'r':role}).scalar()
    def tearDown(self): fixtures.FinancialPostgresTests.tearDown(self)
    def request(self, method='GET', suffix='/', payload=None, role='ADMIN', token=None):
        if token is None and role is not None:
            token = criar_access_token({'sub':str(self.users[role]), 'tipo':'usuario'})
        headers = {'Content-Type':'application/json'}
        if token: headers['Authorization'] = 'Bearer '+token
        return self.client.request(method, PREFIX+suffix, json.dumps(payload).encode() if payload is not None else b'', headers)
    def payload(self, **changes):
        return dict(dict(codigo='NEW', descricao='Novo', ocupacao_id=self.occupation, duracao_minutos=45), **changes)
    def test_create_list_detail_and_reload(self):
        r = self.request('POST', payload=self.payload())
        self.assertEqual(r.status_code, 200, r.text)
        row = r.json(); self.db.expire_all()
        self.assertEqual(self.request(suffix='/'+str(row['id'])).json(), row)
        self.assertEqual(len(self.request().json()), 2)
        self.assertEqual(row['ocupacao_nome'], 'Synthetic'); self.assertFalse(row['em_uso'])
        self.assertTrue(row['ativo'])
    def test_unused_service_all_fields_and_lifecycle_idempotence(self):
        r = self.request('PUT', '/'+str(self.sid), self.payload(duracao_minutos=60))
        self.assertEqual(r.status_code,200,r.text)
        for active in (False, False, True, True):
            r = self.request('PATCH', f'/{self.sid}/estado', {'ativo':active})
            self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['ativo'],active)
            self.assertEqual(r.json()['duracao_minutos'],60)
    def test_price_and_mapping_each_protect_structure_allow_description_state(self):
        for source in ('precos_servico','mapeamentos_agenda_servico'):
            r=self.request('POST',payload=self.payload(codigo=source)).json(); identity=r['id']
            with self.engine.begin() as c:
                if source=='precos_servico':c.execute(text('INSERT INTO precos_servico(versao_id,servico_id,valor_base) VALUES (:v,:s,1)'),{'v':self.vid,'s':identity})
                else:c.execute(text('INSERT INTO mapeamentos_agenda_servico(agenda_cuidado_id,servico_id) VALUES (:a,:s)'),{'a':self.agenda,'s':identity})
            path='/'+str(identity)
            self.assertTrue(self.request(suffix=path).json()['em_uso'])
            blocked=self.request('PUT',path,self.payload(codigo=source,duracao_minutos=60))
            self.assertEqual(blocked.status_code,409,blocked.text)
            self.assertEqual(blocked.json()['detail']['code'],'SERVICE_IN_USE')
            allowed=self.request('PUT',path,self.payload(codigo=source,descricao='Atualizada'))
            self.assertEqual(allowed.status_code,200,allowed.text)
            self.assertEqual(self.request('PATCH',path+'/estado',{'ativo':False}).status_code,200)
            with self.engine.connect() as c:self.assertEqual(c.execute(text(f'SELECT count(*) FROM {source} WHERE servico_id=:s'),{'s':identity}).scalar(),1)
    def test_all_routes_deny_other_profiles_and_missing_invalid_token(self):
        for role in (*self.users.keys(),None):
            if role=='ADMIN':continue
            for method,path,body in [('GET','/',None),('GET',f'/{self.sid}',None),('POST','/',self.payload()),('PUT',f'/{self.sid}',self.payload()),('PATCH',f'/{self.sid}/estado',{'ativo':False})]:
                self.assertEqual(self.request(method,path,body,role=role).status_code,401 if role is None else 403)
        self.assertEqual(self.request(role=None,token='invalid').status_code,401)
    def test_validation_duplicate_and_unknown_occupation(self):
        self.assertEqual(self.request('POST',payload=self.payload(codigo='S')).status_code,409)
        self.assertEqual(self.request('POST',payload=self.payload(ocupacao_id=999999)).status_code,422)
        for changes in ({'codigo':' '},{'duracao_minutos':0},{'unidade':'HORA'},{'tipo_atendimento':'GRUPO'},{'ativo':'false'},{'ator_usuario_id':1}):
            self.assertEqual(self.request('POST',payload=self.payload(**changes)).status_code,422)
        self.assertEqual(len(self.request().json()),1)
    def test_not_found(self):
        for method,path,body in [('GET','/999999',None),('PUT','/999999',self.payload()),('PATCH','/999999/estado',{'ativo':False})]:
            self.assertEqual(self.request(method,path,body).status_code,404)
    def test_reads_no_commit_and_writes_single_commit(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.request();self.request(suffix=f'/{self.sid}');commit.assert_not_called()
            self.assertEqual(self.request('POST',payload=self.payload()).status_code,200)
            self.assertEqual(commit.call_count,1)
    def test_serialization_and_commit_failure_rollback_sanitized(self):
        for target in ('validation','commit'):
            context = patch.object(api.ServicoResponse,'model_validate',side_effect=ValueError('secret')) if target=='validation' else patch.object(self.db,'commit',side_effect=RuntimeError('secret'))
            with context:
                r=self.request('POST',payload=self.payload())
            self.assertEqual(r.status_code,500);self.assertNotIn('secret',r.text)
            with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT count(*) FROM servicos_economicos')).scalar(),1)
    def test_catalog_read_single_query(self):
        statements=[]
        def record(conn,cursor,statement,parameters,context,many):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',record)
        try:
            rows=api.service.list_services(self.db)
            self.assertEqual(len(rows),1);self.assertEqual(len(statements),1)
        finally:event.remove(self.engine,'before_cursor_execute',record)
