"""G2.C.2 HTTP regression using disposable PostgreSQL 18 and real JWT dependencies."""
import os
import json
import unittest
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from alembic import command
from app.database import get_db
from app.core.security import criar_access_token
from app.routers import autorizacoes_institucionais as api
from app.main import integrity_error_handler, app as main_app
from sqlalchemy.exc import IntegrityError
from test_m0_baseline import config
from test_whatsapp_security import LocalClient

URL = os.getenv('G2C1_TEST_POSTGRES_URL')
PREFIX = '/admin/autorizacoes-institucionais'

class AuthorizationHttpStructureTests(unittest.TestCase):
    def test_six_registered_routes(self):
        routes = [r for r in main_app.routes if r.path.startswith(PREFIX)]
        self.assertEqual({(m,r.path[len(PREFIX):]) for r in routes for m in r.methods},
            {('POST','/'),('GET','/'),('GET','/{instituicao_id}/{usuario_id}'),
             ('PATCH','/{instituicao_id}/{usuario_id}/perfil'),
             ('POST','/{instituicao_id}/{usuario_id}/ativar'),('POST','/{instituicao_id}/{usuario_id}/desativar')})

@unittest.skipUnless(URL, 'Requires explicitly disposable PostgreSQL 18')
class AuthorizationHttpPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.database != 'm0_baseline':
            raise RuntimeError('Disposable local database only')
        cls.admin = create_engine(url, isolation_level='AUTOCOMMIT')
        cls.name = 'g2c2_' + uuid4().hex
        with cls.admin.connect() as c:
            if int(c.execute(text('SHOW server_version_num')).scalar()) // 10000 != 18:
                raise RuntimeError('PostgreSQL 18 required')
            c.execute(text('CREATE DATABASE '+cls.name))
        cls.engine = create_engine(url.set(database=cls.name))
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'g2c1_autorizacao_v1')

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:
            c.execute(text('DROP DATABASE '+cls.name))
        cls.admin.dispose()

    def setUp(self):
        self.users = {}
        with self.engine.begin() as c:
            for role in ('ADMIN', 'ADMIN_CLINICA', 'PROFISSIONAL', 'SUPORTE', 'UNKNOWN', 'ADMINISTRADOR', 'INACTIVE'):
                self.users[role] = c.execute(text('INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES (:n,:e,:h,:p,:a) RETURNING id'),
                    dict(n='Synthetic', e=role+'@example.invalid', h='existing-synthetic',
                         p='ADMIN' if role=='INACTIVE' else role, a=role!='INACTIVE')).scalar()
            self.patient = c.execute(text("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id")).scalar()
            self.professional = c.execute(text("INSERT INTO profissionais(nome) VALUES ('Synthetic') RETURNING id")).scalar()
            self.occupation = c.execute(text("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Synthetic') RETURNING id")).scalar()
            self.institution = c.execute(text("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Synthetic','OUTRO') RETURNING id")).scalar()
        self.db = Session(self.engine)
        self.app = FastAPI()
        self.app.include_router(api.router)
        self.app.add_exception_handler(IntegrityError, integrity_error_handler)
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = LocalClient(self.app)

    def tearDown(self):
        self.db.rollback(); self.db.close()
        with self.engine.begin() as c:
            c.execute(text('TRUNCATE usuario_instituicao_acessos,institucional_operacoes,paciente_profissionais,paciente_instituicoes,profissional_instituicoes,instituicoes,pacientes,profissionais,usuarios,ocupacoes_profissionais CASCADE'))

    def request(self, method, suffix, payload=None, params=None, role='ADMIN', token=None):
        if token is None and role is not None:
            token = criar_access_token({'sub':str(self.users[role]), 'tipo':'usuario'})
        headers = {'Content-Type':'application/json'}
        if token is not None: headers['Authorization'] = 'Bearer '+token
        return self.client.request(method, PREFIX+suffix, json.dumps(payload).encode() if payload is not None else b'', headers, params)

    def payload(self, **changes):
        return dict(dict(usuario_id=self.users['PROFISSIONAL'], instituicao_id=self.institution,
                         perfil_institucional='PROFISSIONAL'), **changes)

    def path(self, suffix=''):
        return f'/{self.institution}/{self.users["PROFISSIONAL"]}'+suffix

    def create(self, **changes):
        response = self.request('POST','/',self.payload(**changes))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def test_lifecycle_default_idempotence_and_explicit_profile(self):
        first=self.create()
        self.assertFalse(first['ativo'])
        self.assertEqual(set(first),{'id','usuario_id','instituicao_id','perfil_institucional','ativo'})
        self.assertEqual(self.create(),first)
        self.assertEqual(self.request('GET',self.path()).json(),first)
        self.assertEqual(self.request('GET','/',params={'instituicao_id':self.institution}).json(),[first])
        self.assertEqual(self.request('POST','/',self.payload(perfil_institucional='GESTOR')).status_code,409)
        for profile in ('GESTOR','SUPORTE','PROFISSIONAL'):
            response=self.request('PATCH',self.path('/perfil'),{'perfil_institucional':profile})
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['perfil_institucional'],profile)
            self.assertFalse(response.json()['ativo'])
        for action,state in (('ativar',True),('ativar',True),('desativar',False),('desativar',False)):
            response=self.request('POST',self.path('/'+action))
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['ativo'],state)
            self.assertEqual(response.json()['id'],first['id'])

    def test_all_operations_require_authenticated_global_admin(self):
        operations=[('POST','/',self.payload(),None),('GET','/',None,{'instituicao_id':self.institution}),
                    ('GET',self.path(),None,None),('PATCH',self.path('/perfil'),{'perfil_institucional':'GESTOR'},None),
                    ('POST',self.path('/ativar'),None,None),('POST',self.path('/desativar'),None,None)]
        for method,path,body,params in operations:
            for role in ('ADMIN_CLINICA','PROFISSIONAL','SUPORTE','UNKNOWN','ADMINISTRADOR'):
                self.assertEqual(self.request(method,path,body,params,role=role).status_code,403)
            for role,token in ((None,None),(None,'invalid'),('INACTIVE',None)):
                self.assertEqual(self.request(method,path,body,params,role=role,token=token).status_code,401)
        token=criar_access_token({'sub':str(self.users['ADMIN']),'tipo':'responsavel'})
        self.assertEqual(self.request('GET','/',params={'instituicao_id':self.institution},token=token).status_code,401)

    def test_payload_and_explicit_institution_validation(self):
        self.assertEqual(self.request('GET','/').status_code,422)
        self.assertEqual(self.request('GET','/',params={'instituicao_id':0}).status_code,422)
        for fields in ({'ator_usuario_id':self.users['ADMIN']},{'pessoa_id':1},{'clinica_id':1},
                       {'perfil_institucional':'ADMIN'},{'ativo':'true'},{'data_inicio':'2026-01-01'}):
            response=self.request('POST','/',self.payload(**fields))
            self.assertEqual(response.status_code,422,response.text)
            self.assertEqual(response.json()['detail'],{'code':'INVALID_PAYLOAD'})
        self.create()
        response=self.request('PATCH',self.path('/perfil'),{'perfil_institucional':'GESTOR','ator_usuario_id':1})
        self.assertEqual(response.status_code,422)

    def test_institution_isolation_and_no_implicit_side_effects(self):
        tables=('usuarios','pessoas','pacientes','profissionais','responsaveis','responsavel_paciente',
                'paciente_instituicoes','profissional_instituicoes','paciente_profissionais','vinculos',
                'paciente_modulos','profissional_modulos')
        def snapshot():
            with self.engine.connect() as c:
                return {t:c.execute(text('SELECT row_to_json(t)::text FROM '+t+' t ORDER BY 1')).scalars().all() for t in tables}
        before=snapshot()
        with self.engine.begin() as c:
            other=c.execute(text("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Other','OUTRO') RETURNING id")).scalar()
        first=self.create(ativo=True)
        self.assertEqual(self.request('GET',f'/{other}/{self.users["PROFISSIONAL"]}').status_code,404)
        self.assertEqual(self.request('GET','/',params={'instituicao_id':other}).json(),[])
        second=self.create(instituicao_id=other,perfil_institucional='SUPORTE')
        self.request('POST',self.path('/desativar'))
        self.assertEqual(self.request('GET',f'/{other}/{self.users["PROFISSIONAL"]}').json(),second)
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(snapshot(),before)

    def test_inactive_targets_remain_queryable_and_revocable(self):
        self.create(ativo=True)
        with self.engine.begin() as c:
            c.execute(text('UPDATE usuarios SET ativo=false WHERE id=:i'),{'i':self.users['PROFISSIONAL']})
            c.execute(text('UPDATE instituicoes SET ativo=false WHERE id=:i'),{'i':self.institution})
        self.assertEqual(self.request('GET',self.path()).status_code,200)
        self.assertEqual(len(self.request('GET','/',params={'instituicao_id':self.institution}).json()),1)
        self.assertEqual(self.request('POST',self.path('/ativar')).status_code,409)
        self.assertEqual(self.request('PATCH',self.path('/perfil'),{'perfil_institucional':'GESTOR'}).status_code,409)
        self.assertEqual(self.request('POST',self.path('/desativar')).status_code,200)
        self.assertFalse(self.request('GET',self.path()).json()['ativo'])

    def test_missing_targets_and_access(self):
        for method,path,body in [('GET',self.path(),None),('POST',self.path('/ativar'),None),
                                 ('POST',self.path('/desativar'),None),('PATCH',self.path('/perfil'),{'perfil_institucional':'GESTOR'})]:
            self.assertEqual(self.request(method,path,body).status_code,404)
        for fields in ({'usuario_id':2147483647},{'instituicao_id':2147483647}):
            self.assertEqual(self.request('POST','/',self.payload(**fields)).status_code,404)
        self.assertEqual(self.request('GET','/',params={'instituicao_id':2147483647}).status_code,404)

    def test_response_validation_and_commit_failures_rollback(self):
        for target in ('response','commit'):
            context=(patch.object(api.AcessoResponse,'model_validate',side_effect=ValueError('secret')) if target=='response'
                     else patch.object(self.db,'commit',side_effect=RuntimeError('secret')))
            with context:
                response=self.request('POST','/',self.payload(ativo=True))
            self.assertEqual(response.status_code,500)
            self.assertEqual(response.json()['detail'],{'code':'AUTHORIZATION_OPERATION_FAILED'})
            with self.engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT count(*) FROM usuario_instituicao_acessos')).scalar(),0)

    def test_read_service_rejects_non_admin_directly(self):
        from app.services.autorizacao_institucional import AutorizacaoInstitucionalErro
        for role in ('PROFISSIONAL','ADMIN_CLINICA','SUPORTE'):
            with self.assertRaises(AutorizacaoInstitucionalErro):
                api.service.get(self.db,self.users['PROFISSIONAL'],self.institution,actor_id=self.users[role])
            with self.assertRaises(AutorizacaoInstitucionalErro):
                api.service.list(self.db,instituicao_id=self.institution,actor_id=self.users[role])
