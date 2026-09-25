"""G2.B.2 HTTP boundary against explicitly disposable PostgreSQL 18."""
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
from app.routers import vinculos_institucionais as api
from app.services.institucional import InstitucionalErro
from app.main import integrity_error_handler, app as main_app
from sqlalchemy.exc import IntegrityError
from test_m0_baseline import config
from test_whatsapp_security import LocalClient

URL = os.getenv('G2B1_TEST_POSTGRES_URL')
PREFIX = '/admin/vinculos-institucionais'
RESOURCES = ('pacientes', 'profissionais', 'paciente-profissionais')


class InstitutionalHttpStructureTests(unittest.TestCase):
    def test_exact_fifteen_registered_routes_and_fixed_models(self):
        routes = [r for r in main_app.routes if r.path.startswith(PREFIX)]
        self.assertEqual(len(routes), 15)
        for resource in RESOURCES:
            expected = {('POST', PREFIX+'/'+resource), ('GET', PREFIX+'/'+resource),
                        ('GET', PREFIX+'/'+resource+'/{identity}'),
                        ('POST', PREFIX+'/'+resource+'/{identity}/close'),
                        ('POST', PREFIX+'/'+resource+'/{identity}/invalidate')}
            self.assertTrue(expected <= {(m, r.path) for r in routes for m in r.methods})


@unittest.skipUnless(URL, 'Requires explicitly disposable PostgreSQL 18')
class InstitutionalHttpPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.database != 'm0_baseline':
            raise RuntimeError('Disposable local database only')
        cls.admin = create_engine(url, isolation_level='AUTOCOMMIT')
        cls.name = 'g2b2_' + uuid4().hex
        with cls.admin.connect() as c:
            if int(c.execute(text('SHOW server_version_num')).scalar()) // 10000 != 18:
                raise RuntimeError('PostgreSQL 18 required')
            c.execute(text('CREATE DATABASE '+cls.name))
        cls.engine = create_engine(url.set(database=cls.name))
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'g2b1_institucional_v1')

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:
            c.execute(text('DROP DATABASE '+cls.name))
        cls.admin.dispose()

    def setUp(self):
        self.users = {}
        with self.engine.begin() as c:
            for role in ('ADMIN', 'ADMIN_CLINICA', 'PROFISSIONAL', 'SUPORTE', 'UNKNOWN', 'INACTIVE'):
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
            c.execute(text('TRUNCATE institucional_operacoes,paciente_profissionais,paciente_instituicoes,profissional_instituicoes,instituicoes,pacientes,profissionais,usuarios,ocupacoes_profissionais CASCADE'))

    def request(self, method, suffix, payload=None, params=None, role='ADMIN', token=None):
        if token is None and role is not None:
            token = criar_access_token({'sub':str(self.users[role]), 'tipo':'usuario'})
        headers = {'Content-Type':'application/json'}
        if token is not None: headers['Authorization'] = 'Bearer '+token
        return self.client.request(method, PREFIX+suffix, json.dumps(payload).encode() if payload is not None else b'', headers, params)

    def payload(self, resource):
        base = dict(data_inicio='2026-01-01', motivo='Explicit synthetic operation')
        if resource=='pacientes': base.update(paciente_id=self.patient,instituicao_id=self.institution,tipo_vinculo='ASSISTENCIAL')
        elif resource=='profissionais': base.update(profissional_id=self.professional,instituicao_id=self.institution,ocupacao_id=self.occupation)
        else: base.update(paciente_id=self.patient,paciente_instituicao_id=self.pi,profissional_instituicao_id=self.pri)
        return base

    def create(self, resource):
        response = self.request('POST','/'+resource,self.payload(resource))
        self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def parents(self):
        self.pi = self.create('pacientes')['id']; self.pri = self.create('profissionais')['id']

    def count(self, table):
        with self.engine.connect() as c: return c.execute(text('SELECT count(*) FROM '+table)).scalar()

    def test_global_admin_all_operations_commit_and_provenance(self):
        self.parents(); child = self.create('paciente-profissionais')
        ids = dict(zip(RESOURCES, (self.pi,self.pri,child['id'])))
        for resource in RESOURCES:
            identity = ids[resource]
            response = self.request('GET',f'/{resource}/{identity}')
            self.assertEqual(response.status_code,200,response.text)
            self.assertNotIn('pessoa', response.json()); self.assertNotIn('usuario',response.json())
            self.assertNotIn('estado',response.json()); self.assertNotIn('senha_hash',response.json())
            response = self.request('GET','/'+resource,params={'instituicao_id':self.institution})
            self.assertEqual([r['id'] for r in response.json()],[identity])
        for resource in reversed(RESOURCES):
            response = self.request('POST',f'/{resource}/{ids[resource]}/close',dict(data_fim='2026-02-01',motivo='Explicit close'))
            self.assertEqual(response.status_code,200,response.text); self.assertTrue(response.json()['ativo'])
        for resource in reversed(RESOURCES):
            response = self.request('POST',f'/{resource}/{ids[resource]}/invalidate',{'motivo':'Explicit invalidation'})
            self.assertEqual(response.status_code,200,response.text); self.assertFalse(response.json()['ativo'])
        self.assertEqual(self.count('institucional_operacoes'),9)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT DISTINCT ator_usuario_id FROM institucional_operacoes')).scalars().all(),[self.users['ADMIN']])

    def test_all_routes_reject_other_profiles_and_missing_auth(self):
        for resource in RESOURCES:
            calls=[('POST','/'+resource,{}),('GET','/'+resource,None),('GET',f'/{resource}/1',None),
                   ('POST',f'/{resource}/1/close',{}),('POST',f'/{resource}/1/invalidate',{})]
            for role in ('ADMIN_CLINICA','PROFISSIONAL','SUPORTE','UNKNOWN',None):
                for method,path,payload in calls:
                    with self.subTest(role=role,path=path,method=method):
                        r=self.request(method,path,payload,role=role)
                        self.assertEqual(r.status_code,401 if role is None else 403,r.text)
        self.assertEqual(self.count('institucional_operacoes'),0)

    def test_invalid_inactive_missing_user_and_responsavel_tokens(self):
        tokens=['invalid', criar_access_token({'sub':'999999','tipo':'usuario'}),
                criar_access_token({'sub':str(self.users['ADMIN']),'tipo':'responsavel'})]
        for token in tokens:
            self.assertEqual(self.request('GET','/pacientes/1',token=token).status_code,401)
        self.assertEqual(self.request('GET','/pacientes/1',role='INACTIVE').status_code,401)

    def test_idempotent_create_close_invalidate(self):
        self.parents(); self.create('paciente-profissionais')
        for resource in RESOURCES:
            first=self.create(resource); second=self.create(resource)
            self.assertEqual(first,second)
        self.assertEqual(self.count('institucional_operacoes'),3)
        for resource in reversed(RESOURCES):
            identity=self.create(resource)['id']
            for action,payload in [('close',{'data_fim':'2026-02-01','motivo':'Close'}),('invalidate',{'motivo':'Invalidation'})]:
                a=self.request('POST',f'/{resource}/{identity}/{action}',payload)
                b=self.request('POST',f'/{resource}/{identity}/{action}',payload)
                self.assertEqual(a.status_code,200,a.text); self.assertEqual(a.json(),b.json())
        self.assertEqual(self.count('institucional_operacoes'),9)

    def test_validation_structured_and_no_free_model_or_actor(self):
        for resource in ('pacientes','profissionais'):
            payload=self.payload(resource)
            for extra in ({'model':'Usuario'},{'actor_id':self.users['ADMIN']},{'clinica_id':1},{'ativo':False},{'motivo':' '},{'motivo':None}):
                r=self.request('POST','/'+resource,{**payload,**extra})
                self.assertEqual(r.status_code,422);self.assertEqual(r.json()['detail'],{'code':'INVALID_PAYLOAD'})
            payload.pop('motivo'); self.assertEqual(self.request('POST','/'+resource,payload).status_code,422)
        for resource in RESOURCES:
            self.assertEqual(self.request('GET','/'+resource).status_code,422)
            self.assertEqual(self.request('POST',f'/{resource}/1/close',{'motivo':'x','data_fim':'invalid'}).status_code,422)
            self.assertEqual(self.request('POST',f'/{resource}/1/invalidate',{}).status_code,422)

    def test_domain_error_translation_and_rollback(self):
        cases={'ADMIN_REQUIRED':403,'LINK_NOT_FOUND':404,
               'PERIOD_CONFLICT':409,'CLOSE_CONFLICT':409,'LINK_INVALIDATED':409,
               'DEPENDENT_LINK_CONFLICT':409,'LEGACY_CONTEXT_UNRESOLVED':409,
               'PATIENT_MISMATCH':409,'INSTITUTION_MISMATCH':409,'PARENT_PERIOD_OR_STATE_CONFLICT':409,
               'INVALID_CLOSE':422,'INVALID_PERIOD':422,'REASON_REQUIRED':422,
               'EXPLICIT_INSTITUTION_REQUIRED':422,'CLEAN_SESSION_REQUIRED':500,
               'READ_COMMITTED_REQUIRED':500,'INVALID_TARGET':500,'UNKNOWN':500}
        for code,status in cases.items():
            with self.subTest(code=code), patch.object(api.service,'create',side_effect=InstitucionalErro(code)), patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
                r=self.request('POST','/pacientes',self.payload('pacientes'))
                self.assertEqual(r.status_code,status)
                self.assertEqual(r.json()['detail'],{'code':code if status!=500 else 'INSTITUTIONAL_OPERATION_FAILED'})
                commit.assert_not_called();rollback.assert_called_once()

    def test_legacy_null_and_d2_409_without_changes(self):
        self.parents()
        with self.engine.begin() as c:
            identity=c.execute(text("INSERT INTO paciente_profissionais(paciente_id,profissional_instituicao_id,data_inicio) VALUES (:p,:pr,'2026-01-01') RETURNING id"),dict(p=self.patient,pr=self.pri)).scalar()
        r=self.request('GET',f'/paciente-profissionais/{identity}')
        self.assertEqual(r.status_code,200);self.assertIsNone(r.json()['paciente_instituicao_id'])
        for action,payload in [('close',dict(data_fim='2026-02-01',motivo='Close')),('invalidate',dict(motivo='Invalidate'))]:
            r=self.request('POST',f'/pacientes/{self.pi}/{action}',payload)
            self.assertEqual(r.status_code,409);self.assertEqual(r.json()['detail']['code'],'LEGACY_CONTEXT_UNRESOLVED')
        self.assertEqual(self.count('institucional_operacoes'),2)
        with self.engine.connect() as c:
            self.assertIsNone(c.execute(text('SELECT paciente_instituicao_id FROM paciente_profissionais')).scalar())
            self.assertEqual(c.execute(text('SELECT ativo,data_fim FROM paciente_instituicoes')).one(),(True,None))

    def test_failure_after_domain_flush_rolls_back_link_and_audit(self):
        original=api.service._audit
        def fail(*a,**kw): original(*a,**kw);raise RuntimeError('must not leak internal detail')
        with patch.object(api.service,'_audit',side_effect=fail):
            r=self.request('POST','/pacientes',self.payload('pacientes'))
        self.assertEqual(r.status_code,500);self.assertNotIn('must not leak',r.text)
        self.assertEqual(self.count('paciente_instituicoes'),0);self.assertEqual(self.count('institucional_operacoes'),0)

    def test_integrity_error_preserves_global_handler_and_rolls_back(self):
        payload=self.payload('pacientes');payload['paciente_id']=-999
        r=self.request('POST','/pacientes',payload)
        self.assertEqual(r.status_code,400,r.text)
        self.assertEqual(self.count('paciente_instituicoes'),0);self.assertEqual(self.count('institucional_operacoes'),0)

    def test_no_accounts_permissions_or_context_inference(self):
        tables=('usuarios','pacientes','profissionais','pessoas','responsaveis','vinculos','paciente_modulos','profissional_modulos','responsavel_paciente')
        def snapshot():
            with self.engine.connect() as c:return {t:c.execute(text('SELECT to_jsonb(t) FROM '+t+' t ORDER BY id')).scalars().all() for t in tables}
        before=snapshot();self.parents();self.create('paciente-profissionais');self.assertEqual(snapshot(),before)
        for resource in RESOURCES:
            self.assertEqual(self.request('GET','/'+resource,params={'instituicao_id':-999}).json(),[])
        p=self.payload('pacientes');p.pop('instituicao_id')
        self.assertEqual(self.request('POST','/pacientes',p).status_code,422)

    def test_real_conflicts_and_not_found(self):
        self.parents(); child=self.create('paciente-profissionais')
        r=self.request('POST',f'/pacientes/{self.pi}/invalidate',{'motivo':'x'})
        self.assertEqual(r.json()['detail']['code'],'DEPENDENT_LINK_CONFLICT')
        r=self.request('POST',f'/paciente-profissionais/{child["id"]}/close',{'data_fim':'2025-01-01','motivo':'x'})
        self.assertEqual(r.status_code,422);self.assertEqual(r.json()['detail']['code'],'INVALID_PERIOD')
        for resource in RESOURCES:
            self.assertEqual(self.request('GET',f'/{resource}/999999').status_code,404)
