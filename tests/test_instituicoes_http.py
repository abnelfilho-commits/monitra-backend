"""D7.1-C: real JWT/HTTP and disposable PostgreSQL institution administration."""
import json
import os
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy import text
from app.database import get_db
from app.core.security import criar_access_token
from app.main import app as main_app
from app.routers import instituicoes as api
from app.schemas.institucional import InstituicaoUpdate
from test_whatsapp_security import LocalClient
import test_autorizacoes_institucionais_http as access_tests

PREFIX = '/admin/instituicoes'


class InstitutionHttpContractTests(unittest.TestCase):
    def test_six_routes_registered_no_delete(self):
        found = {(m, r.path[len(PREFIX):]) for r in main_app.routes if r.path.startswith(PREFIX) for m in r.methods}
        self.assertEqual(found, {('GET','/'),('POST','/'),('GET','/{instituicao_id}'),
            ('PATCH','/{instituicao_id}'),('POST','/{instituicao_id}/ativar'),('POST','/{instituicao_id}/inativar')})

    def test_patch_absent_vs_explicit_null_and_extra_fields(self):
        self.assertEqual(InstituicaoUpdate().model_dump(exclude_unset=True), {})
        self.assertEqual(InstituicaoUpdate(cnpj=None).model_dump(exclude_unset=True), {'cnpj':None})
        for values in ({'razao_social':None},{'tipo_instituicao':None},{'ativo':False},{'clinica_id':1},{'ator_usuario_id':1}):
            with self.assertRaises(ValueError):InstituicaoUpdate(**values)


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Requires explicitly disposable PostgreSQL 18')
class InstitutionHttpPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):access_tests.AuthorizationHttpPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):access_tests.AuthorizationHttpPostgresTests.tearDownClass.__func__(cls)

    def setUp(self):
        access_tests.AuthorizationHttpPostgresTests.setUp(self)
        self.app = FastAPI()
        self.app.include_router(api.router)
        self.app.dependency_overrides[get_db] = lambda:self.db
        self.client = LocalClient(self.app)

    def tearDown(self):access_tests.AuthorizationHttpPostgresTests.tearDown(self)

    def request(self, method, suffix='/', payload=None, params=None, role='ADMIN', token=None):
        if token is None and role is not None:
            token=criar_access_token({'sub':str(self.users[role]),'tipo':'usuario'})
        headers={'Content-Type':'application/json'}
        if token is not None:headers['Authorization']='Bearer '+token
        return self.client.request(method,PREFIX+suffix,json.dumps(payload).encode() if payload is not None else b'',headers,params)

    def create(self, **changes):
        result=self.request('POST',payload=dict(dict(razao_social=' Nova ',tipo_instituicao='OPERADORA_SAUDE'),**changes))
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def test_create_valid_cnpj_and_exact_response(self):
        result=self.create(cnpj='11.222.333/0001-81',nome_fantasia='Fantasia')
        self.assertEqual(result['cnpj'],'11222333000181')
        self.assertEqual(result['razao_social'],'Nova')
        self.assertTrue(result['ativo'])
        self.assertEqual(set(result),{'id','razao_social','nome_fantasia','cnpj','tipo_instituicao','instituicao_pai_id','ativo','criado_em','atualizado_em'})
        self.assertEqual(self.request('GET','/'+str(result['id'])).json(),result)

    def test_list_all_active_inactive_and_filters(self):
        other=self.create(ativo=False)
        rows=self.request('GET').json()
        self.assertEqual({r['id'] for r in rows},{self.institution,other['id']})
        for value, expected in (('true',{self.institution}),('false',{other['id']})):
            self.assertEqual({r['id'] for r in self.request('GET',params={'ativo':value}).json()},expected)
        self.assertEqual([r['id'] for r in self.request('GET',params={'tipo_instituicao':'OPERADORA_SAUDE'}).json()],[other['id']])
        self.assertEqual(self.request('GET',params={'tipo_instituicao':'INVALID'}).status_code,422)

    def test_missing_id_all_operations(self):
        for method,suffix,body in [('GET','/999999',None),('PATCH','/999999',{'nome_fantasia':'X'}),('POST','/999999/ativar',None),('POST','/999999/inativar',None)]:
            r=self.request(method,suffix,body)
            self.assertEqual(r.status_code,404,r.text)
            self.assertEqual(r.json()['detail']['code'],'INSTITUTION_NOT_FOUND')

    def test_reject_invalid_cnpj_type_and_blank_name(self):
        for values in ({'cnpj':'11222333000182'},{'cnpj':'00000000000000'},{'tipo_instituicao':'INVALID'},{'razao_social':'  '}):
            body=dict(dict(razao_social='Synthetic',tipo_instituicao='OUTRO'),**values)
            r=self.request('POST',payload=body)
            self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(len(self.request('GET').json()),1)

    def test_duplicate_cnpj_create_and_patch_rollback(self):
        first=self.create(cnpj='11.222.333/0001-81')
        second=self.create()
        for method,suffix,body in [('POST','/',dict(razao_social='No insert',tipo_instituicao='OUTRO',cnpj=first['cnpj'])),
                                  ('PATCH','/'+str(second['id']),dict(razao_social='No update',cnpj=first['cnpj']))]:
            r=self.request(method,suffix,body)
            self.assertEqual(r.status_code,409,r.text)
            self.assertEqual(r.json()['detail']['code'],'CNPJ_ALREADY_EXISTS')
        self.assertEqual(len(self.request('GET').json()),3)
        self.assertEqual(self.request('GET','/'+str(second['id'])).json()['razao_social'],'Nova')

    def test_create_with_parent_and_missing_parent(self):
        row=self.create(instituicao_pai_id=self.institution)
        self.assertEqual(row['instituicao_pai_id'],self.institution)
        r=self.request('POST',payload=dict(razao_social='Invalid',tipo_instituicao='OUTRO',instituicao_pai_id=999999))
        self.assertEqual(r.status_code,422,r.text)
        self.assertEqual(r.json()['detail']['code'],'PARENT_INSTITUTION_NOT_FOUND')
        self.assertEqual(len(self.request('GET').json()),2)

    def test_self_parent_and_deep_cycle_rejected_atomically(self):
        child=self.create(instituicao_pai_id=self.institution)
        grandchild=self.create(instituicao_pai_id=child['id'])
        for parent in (self.institution,grandchild['id']):
            r=self.request('PATCH','/'+str(self.institution),dict(instituicao_pai_id=parent,razao_social='No overwrite'))
            self.assertEqual(r.status_code,409,r.text)
            self.assertEqual(r.json()['detail']['code'],'INSTITUTION_HIERARCHY_CYCLE')
        row=self.request('GET','/'+str(self.institution)).json()
        self.assertEqual(row['razao_social'],'Synthetic');self.assertIsNone(row['instituicao_pai_id'])

    def test_patch_partial_valid_parent_change_and_clear_nullable(self):
        a=self.create(cnpj='11.222.333/0001-81',nome_fantasia='A',instituicao_pai_id=self.institution)
        b=self.create()
        path='/'+str(a['id'])
        r=self.request('PATCH',path,{'nome_fantasia':'B'}).json()
        self.assertEqual(r['cnpj'],a['cnpj']);self.assertEqual(r['razao_social'],a['razao_social'])
        self.assertEqual(self.request('PATCH',path,{'instituicao_pai_id':b['id']}).json()['instituicao_pai_id'],b['id'])
        r=self.request('PATCH',path,{'nome_fantasia':None,'cnpj':None,'instituicao_pai_id':None}).json()
        for key in ('nome_fantasia','cnpj','instituicao_pai_id'):self.assertIsNone(r[key])

    def test_patch_invalid_fields_and_parent_preserve_row(self):
        path='/'+str(self.institution)
        before=self.request('GET',path).json()
        for body in ({'ativo':False},{'razao_social':None},{'razao_social':' '},{'tipo_instituicao':None},
                     {'tipo_instituicao':'INVALID'},{'cnpj':'123'},{'instituicao_pai_id':999999}):
            self.assertEqual(self.request('PATCH',path,body).status_code,422)
        self.assertEqual(self.request('GET',path).json(),before)

    def test_activate_inactivate_preserve_history_idempotently(self):
        path='/'+str(self.institution)
        for action,state in (('inativar',False),('inativar',False),('ativar',True),('ativar',True)):
            r=self.request('POST',path+'/'+action)
            self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['ativo'],state);self.assertEqual(r.json()['id'],self.institution)
        self.assertEqual(self.request('DELETE',path).status_code,405)

    def test_all_endpoints_admin_only_real_jwt(self):
        operations=[('GET','/',None),('GET','/'+str(self.institution),None),('POST','/',{'razao_social':'X','tipo_instituicao':'OUTRO'}),
                    ('PATCH','/'+str(self.institution),{'nome_fantasia':'X'}),('POST',f'/{self.institution}/ativar',None),('POST',f'/{self.institution}/inativar',None)]
        for method,path,body in operations:
            for role in ('ADMIN_CLINICA','PROFISSIONAL','SUPORTE','UNKNOWN','ADMINISTRADOR'):
                self.assertEqual(self.request(method,path,body,role=role).status_code,403)
            for role,token in ((None,None),(None,'invalid'),('INACTIVE',None)):
                self.assertEqual(self.request(method,path,body,role=role,token=token).status_code,401)

    def test_get_never_commits_and_write_commits_once(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.assertEqual(self.request('GET').status_code,200)
            self.assertEqual(self.request('GET','/'+str(self.institution)).status_code,200)
            commit.assert_not_called()
            self.create();self.assertEqual(commit.call_count,1)

    def test_response_validation_before_commit_rolls_back(self):
        with patch.object(api.InstituicaoResponse,'model_validate',side_effect=ValueError('private internal detail')):
            with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
                r=self.request('POST',payload={'razao_social':'No commit','tipo_instituicao':'OUTRO'})
                self.assertEqual(r.status_code,500);commit.assert_not_called()
                self.assertNotIn('private',r.text)
        self.assertEqual(len(self.request('GET').json()),1)

    def test_commit_failure_rolls_back(self):
        with patch.object(self.db,'commit',side_effect=RuntimeError('private database')):
            r=self.request('PATCH','/'+str(self.institution),{'nome_fantasia':'No commit'})
            self.assertEqual(r.status_code,500);self.assertNotIn('private',r.text)
        self.assertIsNone(self.request('GET','/'+str(self.institution)).json()['nome_fantasia'])

    def test_creation_rejects_legacy_actor_and_unknown_fields(self):
        for extra in ({'clinica_id':1},{'ator_usuario_id':self.users['ADMIN']},{'id':1}):
            self.assertEqual(self.request('POST',payload=dict(razao_social='X',tipo_instituicao='OUTRO',**extra)).status_code,422)

    def test_inactivation_does_not_cascade_to_links_access_or_children(self):
        child=self.create(instituicao_pai_id=self.institution)
        with self.engine.begin() as c:
            c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'BENEFICIARIO',CURRENT_DATE)"),dict(p=self.patient,i=self.institution))
            c.execute(text("INSERT INTO usuario_instituicao_acessos(usuario_id,instituicao_id,perfil_institucional,ativo) VALUES (:u,:i,'SUPORTE',true)"),dict(u=self.users['SUPORTE'],i=self.institution))
        self.assertEqual(self.request('POST',f'/{self.institution}/inativar').status_code,200)
        self.assertTrue(self.request('GET','/'+str(child['id'])).json()['ativo'])
        with self.engine.connect() as c:
            for table in ('paciente_instituicoes','usuario_instituicao_acessos'):
                self.assertTrue(c.execute(text(f'SELECT ativo FROM {table} WHERE instituicao_id=:i'),dict(i=self.institution)).scalar())
