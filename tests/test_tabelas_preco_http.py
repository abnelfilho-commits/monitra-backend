"""AE2 vertical HTTP contracts on disposable PostgreSQL, with real JWT auth."""
import json
import os
import unittest
from datetime import timedelta
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy import text, event
from app.main import app as main_app
from app.database import get_db
from app.core.security import criar_access_token
from app.routers import tabelas_preco as api
from app.models.financeiro import ServicoEconomico
from test_whatsapp_security import LocalClient
import test_financeiro_postgres as fixtures


class RoutesTests(unittest.TestCase):
    def test_all_twelve_routes_registered(self):
        paths = {(m, r.path) for r in main_app.routes for m in getattr(r, 'methods', [])}
        for r in api.router.routes:
            for method in r.methods:
                self.assertIn((method, r.path), paths)
        self.assertEqual(len(api.router.routes), 12)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class TableHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): fixtures.FinancialPostgresTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): fixtures.FinancialPostgresTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixtures.FinancialPostgresTests.setUp(self)
        self.app = FastAPI(); self.app.include_router(api.router)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = LocalClient(self.app)
        self.users = {'ADMIN': self.actor}
        with self.engine.begin() as c:
            for role in ('ADMIN_CLINICA', 'PROFISSIONAL', 'SUPORTE', 'GESTOR'):
                self.users[role] = c.execute(text("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES ('Synthetic',:e,'synthetic',:r,true) RETURNING id"),dict(e=role+'@example.invalid',r=role)).scalar()
    def tearDown(self): fixtures.FinancialPostgresTests.tearDown(self)
    def req(self, method, path, body=None, role='ADMIN', token=None):
        if token is None and role:
            token = criar_access_token({'sub': str(self.users[role]), 'tipo': 'usuario'})
        headers = {'Content-Type': 'application/json'}
        if token: headers['Authorization'] = 'Bearer '+token
        return self.client.request(method, '/admin/economia'+path,
            json.dumps(body).encode() if body is not None else b'', headers)
    def ok(self, method, path, body=None):
        r = self.req(method, path, body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()
    def version(self, number=2, days=1, table=None):
        return self.ok('POST', f'/tabelas/{table or self.tid}/versoes',
            dict(numero=number, vigente_desde=str(self.today+timedelta(days=days))))
    def price(self, version=None, service=None, value='150.00', external=None):
        return self.ok('POST', f'/versoes/{version or self.vid}/precos',
            dict(servico_id=service or self.sid, valor_base=value, codigo_externo=external))
    def test_acceptance_150_create_reload_edit_publish_immutable(self):
        table=self.ok('POST','/tabelas/',dict(proprietario_instituicao_id=self.other,codigo='NEW',nome='Tabela Empresa'))
        self.assertEqual(table['proprietario_nome'],'B')
        self.assertEqual(self.ok('GET',f"/tabelas/{table['id']}"),table)
        self.assertEqual(len(self.ok('GET','/tabelas/')),2)
        v=self.version(1,0,table['id']); vid=v['id']
        self.assertEqual(self.ok('GET',f'/versoes/{vid}/precos')['precos'],[])
        self.assertEqual(len(self.ok('GET',f"/tabelas/{table['id']}/versoes")),1)
        p=self.price(vid); path=f"/precos/{p['id']}"
        for value in ('151.25','150.00'):
            self.ok('PUT',path,dict(valor_base=value))
        self.db.expire_all()
        self.assertEqual(self.ok('GET',f'/versoes/{vid}/precos')['precos'][0]['valor_base'],'150.00')
        self.ok('PUT',f'/versoes/{vid}',dict(numero=3,vigente_desde=str(self.today)))
        published=self.ok('POST',f'/versoes/{vid}/publicar')
        self.assertEqual(published['publicado_por_usuario_id'],self.actor)
        self.assertIsNotNone(published['publicado_em'])
        self.db.expire_all()
        self.assertEqual(self.ok('GET',f'/versoes/{vid}')['estado'],'PUBLISHED')
        for method,url,body in [('PUT',f'/versoes/{vid}',dict(numero=4,vigente_desde=str(self.today))),
            ('POST',f'/versoes/{vid}/precos',dict(servico_id=self.sid,valor_base='1')),
            ('PUT',path,dict(valor_base='1')),('DELETE',path,None),('POST',f'/versoes/{vid}/publicar',None)]:
            self.assertEqual(self.req(method,url,body).status_code,409)
        self.assertEqual(self.ok('GET',f'/versoes/{vid}/precos')['precos'][0]['valor_base'],'150.00')
    def test_zero_delete_absence_and_empty_publication_allowed(self):
        p=self.price(value='0.00')
        self.assertEqual(p['valor_base'],'0.00')
        r=self.req('DELETE',f"/precos/{p['id']}");self.assertEqual(r.status_code,204)
        self.assertEqual(self.ok('GET',f'/versoes/{self.vid}/precos')['quantidade_precos'],0)
        self.assertEqual(self.ok('POST',f'/versoes/{self.vid}/publicar')['estado'],'PUBLISHED')
    def test_retroactive_publication_utc(self):
        self.ok('PUT',f'/versoes/{self.vid}',dict(numero=1,vigente_desde=str(self.today-timedelta(days=1))))
        self.db.execute(text("SET TIME ZONE 'Pacific/Kiritimati'"))
        r=self.req('POST',f'/versoes/{self.vid}/publicar')
        self.assertEqual(r.status_code,422);self.assertEqual(r.json()['detail']['code'],'RETROACTIVE_PUBLICATION')
        self.assertEqual(self.ok('GET',f'/versoes/{self.vid}')['estado'],'DRAFT')
    def test_uniqueness_and_foreign_keys(self):
        body=dict(proprietario_instituicao_id=self.owner,codigo='T',nome='Duplicada')
        self.assertEqual(self.req('POST','/tabelas/',body).status_code,409)
        body['proprietario_instituicao_id']=self.other;self.ok('POST','/tabelas/',body)
        body['proprietario_instituicao_id']=999999
        self.assertEqual(self.req('POST','/tabelas/',body).status_code,422)
        self.assertEqual(self.req('POST',f'/tabelas/{self.tid}/versoes',dict(numero=1,vigente_desde=str(self.today))).status_code,409)
        self.price(external='EXT')
        self.assertEqual(self.req('POST',f'/versoes/{self.vid}/precos',dict(servico_id=self.sid,valor_base='1')).status_code,409)
        second=self.service.create(self.db,ServicoEconomico,dict(codigo='OTHER',descricao='Outro',ocupacao_id=self.occupation,duracao_minutos=45));self.db.commit();sid=second.id
        r=self.req('POST',f'/versoes/{self.vid}/precos',dict(servico_id=sid,valor_base='1',codigo_externo='EXT'))
        self.assertEqual(r.status_code,409);self.assertEqual(r.json()['detail']['code'],'EXTERNAL_CODE_EXISTS')
        self.ok('POST',f'/versoes/{self.vid}/publicar')
        v=self.version(2,0)
        self.assertEqual(self.req('POST',f"/versoes/{v['id']}/publicar").status_code,409)
    def test_previous_means_vigencia_not_number_and_inactive_visible(self):
        self.price();self.ok('POST',f'/versoes/{self.vid}/publicar')
        earlier=self.version(20,1); self.ok('POST',f"/versoes/{earlier['id']}/publicar")
        target=self.version(2,2)
        future=self.version(30,4);self.price(future['id']);self.ok('POST',f"/versoes/{future['id']}/publicar")
        draft=self.version(40,1)
        grid=self.ok('GET',f"/versoes/{target['id']}/precos")
        self.assertEqual(grid['versao_anterior_id'],earlier['id']);self.assertEqual(grid['servicos_anteriores_sem_preco'],0)
        grid=self.ok('GET',f"/versoes/{draft['id']}/precos")
        self.assertEqual(grid['versao_anterior_id'],self.vid);self.assertEqual(grid['servicos_anteriores_sem_preco'],1)
        with self.engine.begin() as c:c.execute(text('UPDATE servicos_economicos SET ativo=false WHERE id=:s'),dict(s=self.sid))
        grid=self.ok('GET',f'/versoes/{self.vid}/precos')
        self.assertEqual(grid['servicos_inativos'],1);self.assertFalse(grid['precos'][0]['servico_ativo'])
    def test_all_routes_admin_only(self):
        routes=[('GET','/tabelas/',None),('POST','/tabelas/',dict(proprietario_instituicao_id=self.owner,codigo='X',nome='X')),
            ('GET',f'/tabelas/{self.tid}',None),('GET',f'/tabelas/{self.tid}/versoes',None),
            ('POST',f'/tabelas/{self.tid}/versoes',dict(numero=2,vigente_desde=str(self.today))),
            ('GET',f'/versoes/{self.vid}',None),('PUT',f'/versoes/{self.vid}',dict(numero=2,vigente_desde=str(self.today))),
            ('POST',f'/versoes/{self.vid}/publicar',None),('GET',f'/versoes/{self.vid}/precos',None),
            ('POST',f'/versoes/{self.vid}/precos',dict(servico_id=self.sid,valor_base='1')),
            ('PUT','/precos/1',dict(valor_base='1')),('DELETE','/precos/1',None)]
        for role in ('ADMIN_CLINICA','PROFISSIONAL','SUPORTE','GESTOR',None):
            for method,path,body in routes:
                self.assertEqual(self.req(method,path,body,role=role).status_code,401 if role is None else 403)
        self.assertEqual(self.req('GET','/tabelas/',role=None,token='invalid').status_code,401)
    def test_reads_no_commit_write_once_rollback_before_response(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            for path in ('/tabelas/',f'/tabelas/{self.tid}',f'/tabelas/{self.tid}/versoes',f'/versoes/{self.vid}',f'/versoes/{self.vid}/precos'):
                self.ok('GET',path)
            commit.assert_not_called();self.price();self.assertEqual(commit.call_count,1)
        for target in ('validation','commit'):
            context=patch.object(api.VersaoResponse,'model_validate',side_effect=ValueError('secret')) if target=='validation' else patch.object(self.db,'commit',side_effect=RuntimeError('secret'))
            with context:r=self.req('POST',f'/tabelas/{self.tid}/versoes',dict(numero=2,vigente_desde=str(self.today)))
            self.assertEqual(r.status_code,500);self.assertNotIn('secret',r.text)
            self.assertEqual(len(self.ok('GET',f'/tabelas/{self.tid}/versoes')),1)
    def test_validation_and_not_found(self):
        for value in ('', '-1', '1.001', 'NaN', 'Infinity', '1000000000000'):
            self.assertEqual(self.req('POST',f'/versoes/{self.vid}/precos',dict(servico_id=self.sid,valor_base=value)).status_code,422)
        self.assertEqual(self.req('PUT',f'/versoes/{self.vid}',dict(numero=0,vigente_desde=str(self.today))).status_code,422)
        self.assertEqual(self.req('POST','/tabelas/',dict(proprietario_instituicao_id=self.owner,codigo=' ',nome='X')).status_code,422)
        for path in ('/tabelas/999999','/tabelas/999999/versoes','/versoes/999999','/versoes/999999/precos'):
            self.assertEqual(self.req('GET',path).status_code,404)
        self.assertEqual(self.req('PUT','/precos/999999',dict(valor_base='1')).status_code,404)
        self.assertEqual(self.req('DELETE','/precos/999999').status_code,404)
        self.assertEqual(self.req('PUT',f'/versoes/{self.vid}',dict(numero=1,vigente_desde=str(self.today),publicado_por_usuario_id=1)).status_code,422)
    def test_publisher_cannot_be_supplied_by_client(self):
        r=self.req('POST',f'/versoes/{self.vid}/publicar',dict(publicado_por_usuario_id=self.users['SUPORTE']))
        self.assertEqual(r.status_code,422)
        self.assertEqual(self.ok('GET',f'/versoes/{self.vid}')['estado'],'DRAFT')

    def test_grid_queries_bounded_no_n_plus_one(self):
        self.price();self.ok('POST',f'/versoes/{self.vid}/publicar');v=self.version()
        statements=[]
        def record(conn,cursor,statement,parameters,context,many):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',record)
        try:
            self.service.list_prices(self.db,v['id'])
            self.assertEqual(len(statements),4)
        finally:event.remove(self.engine,'before_cursor_execute',record)
