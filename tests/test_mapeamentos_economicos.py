"""AE4 focused HTTP tests on the existing disposable PostgreSQL 18."""
import json
import os
import unittest
from urllib.parse import urlsplit, parse_qsl
from unittest.mock import patch
from alembic import command
from fastapi import FastAPI
from sqlalchemy import text
from app.core.security import criar_access_token
from app.database import get_db
from app.main import app as main_app
from app.routers import mapeamentos_economicos as api
from test_whatsapp_security import LocalClient
import test_financeiro_postgres as fixtures
from test_m0_baseline import config


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class MappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.FinancialPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        fixtures.FinancialPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        fixtures.FinancialPostgresTests.setUp(self)
        # Current HTTP service reads current contextual PTS columns.
        with self.engine.begin() as c:
            command.upgrade(config(c), 'w3_atendimento_mental_v1')
            self.second = c.execute(text("INSERT INTO servicos_economicos(codigo,descricao,ocupacao_id,duracao_minutos) VALUES ('S2','Second',:o,45) RETURNING id"), {'o': self.occupation}).scalar()
            self.nonadmin = c.exec_driver_sql("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES ('Other','other@example.invalid','test','SUPORTE',true) RETURNING id").scalar()
        app = FastAPI()
        app.include_router(api.router)
        app.dependency_overrides[get_db] = lambda: self.db
        self.client = LocalClient(app)

    def tearDown(self):
        fixtures.FinancialPostgresTests.tearDown(self)

    def req(self, method='GET', path='/', body=None, actor=None):
        token = criar_access_token({'sub': str(actor or self.actor), 'tipo': 'usuario'})
        url = urlsplit(path)
        return self.client.request(method, '/admin/economia/mapeamentos'+url.path,
            json.dumps(body).encode() if body is not None else b'',
            {'Content-Type': 'application/json', 'Authorization': 'Bearer '+token},
            params=dict(parse_qsl(url.query)))

    def create(self, service=None):
        return self.req('POST', body={'agenda_cuidado_id': self.agenda, 'servico_id': service or self.sid})

    def test_admin_and_registered_routes(self):
        paths = {(method, r.path) for r in main_app.routes for method in getattr(r, 'methods', [])}
        for r in api.router.routes:
            for method in r.methods:
                self.assertIn((method, r.path), paths)
        for method, path, body in [('GET','/',None), ('POST','/',{'agenda_cuidado_id': self.agenda,'servico_id': self.sid}), ('PUT','/1',{'servico_id': self.sid})]:
            self.assertEqual(self.req(method,path,body,self.nonadmin).status_code,403)
        self.assertEqual(self.req().status_code,200)

    def test_listing_filters_and_no_commit(self):
        with patch.object(self.db, 'commit', wraps=self.db.commit) as commit:
            response = self.req()
            self.assertEqual(response.status_code,200,response.text)
            commit.assert_not_called()
        row=response.json()[0]
        self.assertIsNone(row['mapeamento_id'])
        self.assertIsNone(row['contexto_assistencial_id'])
        self.assertEqual(row['paciente_id'],self.patient)
        self.assertEqual(len(self.req(path='/?situacao=NAO_MAPEADOS').json()),1)
        self.assertEqual(self.req(path='/?situacao=MAPEADOS').json(),[])
        self.assertEqual(self.req(path='/?busca=absent').json(),[])
        self.assertEqual(len(self.req(path='/?busca=Synthetic').json()),1)
        self.assertEqual(self.req(path='/?modulo_id=99999').json(),[])
        self.assertEqual(self.req(path='/?situacao=INVALID').status_code,422)

    def test_create_idempotence_conflict_and_explicit_change(self):
        first=self.create()
        self.assertEqual(first.status_code,200,first.text)
        row=first.json()
        self.assertEqual(self.create().json()['mapeamento_id'],row['mapeamento_id'])
        conflict=self.create(self.second)
        self.assertEqual(conflict.status_code,409,conflict.text)
        self.assertEqual(conflict.json()['detail']['code'],'MAPPING_CONFLICT')
        self.assertEqual(self.req().json()[0]['servico_id'],self.sid)
        changed=self.req('PUT','/'+str(row['mapeamento_id']),{'servico_id':self.second})
        self.assertEqual(changed.status_code,200,changed.text)
        self.assertEqual(changed.json()['servico_id'],self.second)
        self.assertEqual(len(self.req(path='/?situacao=MAPEADOS').json()),1)
        self.assertEqual(self.req(path='/?situacao=NAO_MAPEADOS').json(),[])

    def test_inactive_selection_rejected_but_history_visible(self):
        first=self.create().json()
        self.db.rollback()
        with self.engine.begin() as c:
            c.execute(text('UPDATE servicos_economicos SET ativo=false WHERE id=:id'),{'id':self.sid})
        row=self.req().json()[0]
        self.assertEqual(row['mapeamento_id'],first['mapeamento_id'])
        self.assertIs(row['servico_ativo'],False)
        self.assertEqual(self.create().status_code,422)
        self.assertEqual(self.req('PUT','/'+str(first['mapeamento_id']),{'servico_id':self.sid}).status_code,422)
        self.assertEqual(self.req('PUT','/'+str(first['mapeamento_id']),{'servico_id':self.second}).status_code,200)

    def test_missing_references(self):
        for payload in [{'agenda_cuidado_id':999999,'servico_id':self.sid}, {'agenda_cuidado_id':self.agenda,'servico_id':999999}]:
            self.assertEqual(self.req('POST',body=payload).status_code,404)
        self.assertEqual(self.req('PUT','/999999',{'servico_id':self.sid}).status_code,404)
        self.assertIsNone(self.req().json()[0]['mapeamento_id'])

    def test_invalid_response_rolls_back_before_commit(self):
        with patch.object(api.service,'list_mapping_agendas',return_value=[{}]):
            self.assertEqual(self.create().status_code,500)
        self.assertIsNone(self.req().json()[0]['mapeamento_id'])
