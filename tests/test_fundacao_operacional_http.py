"""Administrative identity/context boundaries on disposable PostgreSQL 18."""
import json
import os
import unittest
from unittest.mock import patch
from alembic import command
from fastapi import FastAPI
from sqlalchemy import text
from app.database import get_db
from app.core.security import criar_access_token
from app.main import app as main_app
from app.routers import pessoas, contextos_assistenciais, saude_mental
from app.schemas.pessoa import PessoaUpdate
from test_whatsapp_security import LocalClient
from test_m0_baseline import config
import test_autorizacoes_institucionais_http as fixture


class OperationalContractTests(unittest.TestCase):
    def test_exact_routes_no_creation_or_grants(self):
        actual={(m,r.path) for r in main_app.routes for m in getattr(r,'methods',())
                if r.path.startswith(('/admin/pessoas','/admin/contextos-assistenciais'))}
        self.assertEqual(actual,{('GET','/admin/pessoas/'),('GET','/admin/pessoas/{pessoa_id}'),
            ('GET','/admin/pessoas/{pessoa_id}/acessos'),('GET','/admin/pessoas/{pessoa_id}/vinculos'),
            ('PATCH','/admin/pessoas/{pessoa_id}'),('POST','/admin/pessoas/{pessoa_id}/acesso'),('POST','/admin/contextos-assistenciais/'),
            ('GET','/admin/contextos-assistenciais/{contexto_id}'),('POST','/admin/contextos-assistenciais/{contexto_id}/linhas')})

    def test_patch_contract(self):
        self.assertEqual(PessoaUpdate().model_dump(exclude_unset=True),{})
        self.assertEqual(PessoaUpdate(nome_social=None).model_dump(exclude_unset=True),{'nome_social':None})
        for field,value in [('cpf',None),('id',1),('clinica_id',1),('ator_usuario_id',1),('nome_completo',None),('ativo',None)]:
            with self.subTest(field=field), self.assertRaises(ValueError):PessoaUpdate(**{field:value})


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'),'Disposable PostgreSQL 18 required')
class OperationalHttpTests(unittest.TestCase):
    def setUp(self):
        fixture.AuthorizationHttpPostgresTests.setUp(self)
        with self.engine.begin() as c:
            command.upgrade(config(c),'head')
            self.person=c.exec_driver_sql("INSERT INTO pessoas(nome_completo,cpf) VALUES ('Synthetic','52998224725') RETURNING id").scalar()
            c.execute(text('UPDATE pacientes SET pessoa_id=:p WHERE id=:id'),dict(p=self.person,id=self.patient))
            self.other=c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Other','OUTRO') RETURNING id").scalar()
            self.links=[]
            for institution in (self.institution,self.other):
                self.links.append(c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'ASSISTENCIAL','2026-01-01') RETURNING id"),dict(p=self.patient,i=institution)).scalar())
        self.app=FastAPI()
        for api in (pessoas,contextos_assistenciais,saude_mental):self.app.include_router(api.router)
        self.app.dependency_overrides[get_db]=lambda:self.db
        self.client=LocalClient(self.app)

    def tearDown(self):fixture.AuthorizationHttpPostgresTests.tearDown(self)

    def request(self,method,path,payload=None,params=None,role='ADMIN',token=None):
        if token is None and role is not None:token=criar_access_token({'sub':str(self.users[role]),'tipo':'usuario'})
        headers={'Content-Type':'application/json'}
        if token is not None:headers['Authorization']='Bearer '+token
        return self.client.request(method,path,json.dumps(payload).encode() if payload is not None else b'',headers,params)

    def create(self,**changes):
        response=self.request('POST','/admin/contextos-assistenciais/',dict(paciente_instituicao_id=self.links[0],data_inicio='2026-01-01',**changes))
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def count(self,table):return self.db.execute(text('SELECT count(*) FROM '+table)).scalar()

    def test_people_list_get_pagination_without_commit(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            rows=self.request('GET','/admin/pessoas/').json()
            self.assertEqual([p['id'] for p in rows],[self.person])
            self.assertEqual(self.request('GET',f'/admin/pessoas/{self.person}').json(),rows[0])
            self.assertEqual(self.request('GET','/admin/pessoas/',params={'offset':1,'limit':1}).json(),[])
            self.assertEqual(self.request('GET','/admin/pessoas/',params={'limit':101}).status_code,422)
            commit.assert_not_called()

    def test_people_partial_update_and_immutable_cpf(self):
        path=f'/admin/pessoas/{self.person}'
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            response=self.request('PATCH',path,{'nome_completo':' Updated ','nome_social':' Social ','telefone':' 123 '})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['nome_completo'],'Updated')
            self.assertEqual(response.json()['cpf'],'52998224725')
            commit.assert_called_once()
        self.assertEqual(self.request('PATCH',path,{'nome_social':None}).json()['nome_social'],None)
        for data in ({'cpf':'52998224725'},{'cpf':None},{'nome_completo':' '},{'data_nascimento':'2999-01-01'},{'email':'invalid'},{'clinica_id':1},{'ator_usuario_id':1}):
            self.assertEqual(self.request('PATCH',path,data).status_code,422,data)
        self.assertEqual(self.request('GET',path).json()['cpf'],'52998224725')

    def test_legacy_null_cpf_preserved(self):
        with self.engine.begin() as c: c.execute(text('UPDATE pessoas SET cpf=NULL WHERE id=:id'),dict(id=self.person))
        response=self.request('PATCH',f'/admin/pessoas/{self.person}',{'nome_completo':'Legacy'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIsNone(response.json()['cpf'])

    def test_person_missing_and_rollback(self):
        self.assertEqual(self.request('GET','/admin/pessoas/2147483647').status_code,404)
        self.assertEqual(self.request('PATCH','/admin/pessoas/2147483647',{'nome_completo':'X'}).status_code,404)
        with patch.object(pessoas.PessoaOut,'model_validate',side_effect=RuntimeError('private error')):
            response=self.request('PATCH',f'/admin/pessoas/{self.person}',{'nome_completo':'Not committed'})
        self.assertEqual(response.status_code,500)
        self.assertNotIn('private error',response.text)
        self.assertEqual(self.request('GET',f'/admin/pessoas/{self.person}').json()['nome_completo'],'Synthetic')

    def test_admin_only_all_routes(self):
        routes=[('GET','/admin/pessoas/',None),('GET',f'/admin/pessoas/{self.person}',None),('PATCH',f'/admin/pessoas/{self.person}',{}),
                ('POST','/admin/contextos-assistenciais/',{'paciente_instituicao_id':self.links[0],'data_inicio':'2026-01-01'}),
                ('GET','/admin/contextos-assistenciais/1',None),('POST','/admin/contextos-assistenciais/1/linhas',{'modulo_id':3})]
        for role in ('ADMIN_CLINICA','PROFISSIONAL','SUPORTE','UNKNOWN'):
            for method,path,payload in routes:
                self.assertEqual(self.request(method,path,payload,params={'instituicao_id':self.institution},role=role).status_code,403,(role,path))
        self.assertEqual(self.request('GET','/admin/pessoas/',role=None).status_code,401)
        self.assertEqual(self.request('GET','/admin/pessoas/',token='invalid').status_code,401)
        self.assertEqual(self.request('GET','/admin/pessoas/',role='INACTIVE').status_code,401)

    def test_context_identity_and_read_scope(self):
        row=self.create()
        self.assertEqual((row['paciente_id'],row['instituicao_id'],row['criado_por_usuario_id']),
                         (self.patient,self.institution,self.users['ADMIN']))
        path=f"/admin/contextos-assistenciais/{row['id']}"
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.assertEqual(self.request('GET',path,params={'instituicao_id':self.institution}).json(),row)
            commit.assert_not_called()
        self.assertEqual(self.request('GET',path,params={'instituicao_id':self.other}).status_code,404)
        self.assertEqual(self.request('GET',path).status_code,422)

    def test_context_invalid_link_and_payload(self):
        for payload,status in [({'data_inicio':'2026-01-01'},422),
            ({'paciente_instituicao_id':2147483647,'data_inicio':'2026-01-01'},404),
            ({'paciente_instituicao_id':self.links[0],'data_inicio':'2025-01-01'},409),
            ({'paciente_instituicao_id':self.links[0],'data_inicio':'2026-02-01','data_fim':'2026-01-01'},422),
            ({'paciente_instituicao_id':self.links[0],'data_inicio':'2026-01-01','instituicao_id':self.other},422)]:
            self.assertEqual(self.request('POST','/admin/contextos-assistenciais/',payload).status_code,status)
        self.assertEqual(self.count('contextos_assistenciais'),0)

    def test_line_no_implicit_authorization_or_activation(self):
        row=self.create()
        response=self.request('POST',f"/admin/contextos-assistenciais/{row['id']}/linhas",{'modulo_id':3},params={'instituicao_id':self.institution})
        self.assertEqual(response.status_code,201,response.text)
        self.assertFalse(response.json()['ativo'])
        self.assertEqual(response.json()['modulo_id'],3)
        for table in ('usuario_instituicao_acessos','concessoes_assistenciais','autoridades_delegacao','contexto_profissionais'):
            self.assertEqual(self.count(table),0)
        for role in ('ADMIN','ADMIN_CLINICA','PROFISSIONAL','SUPORTE'):
            self.assertEqual(self.request('GET','/saude-mental/pessoas',params={'instituicao_id':self.institution},role=role).json()['itens'],[])
            self.assertEqual(self.request('GET',f"/saude-mental/pessoas/{self.person}/contextos/{row['id']}",params={'instituicao_id':self.institution},role=role).status_code,404)
        self.assertEqual(self.count('pessoas'),1)

    def test_duplicate_context_and_line_preserve_existing_rules(self):
        row=self.create()
        self.assertEqual(self.request('POST','/admin/contextos-assistenciais/',{'paciente_instituicao_id':self.links[0],'data_inicio':'2026-01-01'}).status_code,409)
        path=f"/admin/contextos-assistenciais/{row['id']}/linhas"
        args={'instituicao_id':self.institution}
        self.assertEqual(self.request('POST',path,{'modulo_id':3},params=args).status_code,201)
        self.assertEqual(self.request('POST',path,{'modulo_id':3},params=args).status_code,409)
        self.assertEqual(self.count('contextos_assistenciais'),1)
        self.assertEqual(self.count('contexto_assistencial_linhas'),1)

    def test_line_wrong_institution_invalid_module_and_closed_context(self):
        row=self.create(data_fim='2026-12-31')
        path=f"/admin/contextos-assistenciais/{row['id']}/linhas"
        self.assertEqual(self.request('POST',path,{'modulo_id':3},params={'instituicao_id':self.other}).status_code,404)
        self.assertEqual(self.request('POST',path,{'modulo_id':3},params={'instituicao_id':self.institution}).status_code,409)
        with self.engine.begin() as c:c.exec_driver_sql('UPDATE contextos_assistenciais SET data_fim=NULL')
        self.db.expire_all()
        self.assertEqual(self.request('POST',path,{'modulo_id':2147483647},params={'instituicao_id':self.institution}).status_code,404)
        for payload in ({'modulo_id':3,'ativo':True},{'modulo_id':3,'contexto_assistencial_id':999},{'modulo_id':0}):
            self.assertEqual(self.request('POST',path,payload,params={'instituicao_id':self.institution}).status_code,422)
        self.assertEqual(self.count('contexto_assistencial_linhas'),0)

    def test_context_response_failure_rolls_back(self):
        with patch.object(contextos_assistenciais.ContextoOut,'model_validate',side_effect=RuntimeError('private')):
            response=self.request('POST','/admin/contextos-assistenciais/',{'paciente_instituicao_id':self.links[0],'data_inicio':'2026-01-01'})
        self.assertEqual(response.status_code,500)
        self.assertEqual(self.count('contextos_assistenciais'),0)

    def test_same_person_separate_institutions(self):
        first=self.create()
        second=self.request('POST','/admin/contextos-assistenciais/',{'paciente_instituicao_id':self.links[1],'data_inicio':'2026-01-01'})
        self.assertEqual(second.status_code,201,second.text)
        self.assertEqual(second.json()['instituicao_id'],self.other)
        self.assertNotEqual(first['id'],second.json()['id'])
