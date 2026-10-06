"""IAM-N1: native account provisioning against disposable PG18."""
import os
import unittest
from unittest.mock import patch
from sqlalchemy import text
from app.core.security import verificar_senha, criar_access_token
from app.routers import pessoas, operacao_assistencial
from app.models.usuario import Usuario
import test_fundacao_operacional_http as fixture


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Disposable PG18 required')
class NativeAccessTests(unittest.TestCase):
    request = fixture.OperationalHttpTests.request
    tearDown = fixture.OperationalHttpTests.tearDown
    count = fixture.OperationalHttpTests.count

    def setUp(self):
        fixture.OperationalHttpTests.setUp(self)
        self.app.include_router(operacao_assistencial.router)
        self.path = f'/admin/pessoas/{self.person}/acesso'
        self.data = dict(email='native@example.com', senha_inicial='Local-test-credential',
                         instituicao_id=self.institution, perfil_institucional='SUPORTE', ativo=True)

    def enable(self, **changes):
        return self.request('POST', self.path, {**self.data, **changes})

    def test_native_account_and_w1b_no_implicit_entitlements(self):
        tables=('profissionais','profissional_instituicoes','autoridades_delegacao','concessoes_assistenciais','contexto_profissionais')
        before={t:self.count(t) for t in tables}
        self.db.rollback()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            r=self.enable()
            self.assertEqual(r.status_code,200,r.text)
            commit.assert_called_once()
        body=r.json();u=self.db.get(Usuario,body['usuario_id'])
        self.assertEqual(u.pessoa_id,self.person)
        self.assertIsNone(u.clinica_id);self.assertIsNone(u.profissional_id)
        self.assertTrue(verificar_senha(self.data['senha_inicial'],u.senha_hash))
        self.assertNotIn('senha',r.text);self.assertNotIn(u.senha_hash,r.text)
        self.assertEqual(body['autorizacao']['perfil_institucional'],'SUPORTE')
        self.assertEqual(body['autorizacao']['instituicao_id'],self.institution)
        self.assertEqual(before,{t:self.count(t) for t in tables})
        c=self.request('POST','/admin/contextos-assistenciais/',dict(paciente_instituicao_id=self.links[0],data_inicio='2026-01-01')).json()
        path=f"/operacao-assistencial/contextos/{c['id']}"
        state=self.request('GET',path,params={'instituicao_id':self.institution}).json()
        self.assertIn({'id':body['autorizacao']['id'],'nome':'Synthetic'},state['contas'])
        self.assertEqual(state['acoes']['conceder_capacidades'],[])
        self.assertEqual(self.request('GET','/saude-mental/pessoas',params={'instituicao_id':self.institution}).json()['itens'],[])
        # Own-account exclusion remains true even for an independently elevated
        # synthetic ADMIN (provisioning never performs this elevation).
        self.db.rollback()
        with self.engine.begin() as conn:conn.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:id"),{'id':u.id})
        token=criar_access_token({'sub':str(u.id)})
        self.db.expire_all()
        own=self.request('GET',path,params={'instituicao_id':self.institution},token=token).json()
        self.assertNotIn(body['autorizacao']['id'],[x['id'] for x in own['contas']])

    def test_repeat_keeps_password_and_conflicts_do_not_overwrite(self):
        r=self.enable().json();u=self.db.get(Usuario,r['usuario_id']);old=u.senha_hash
        again=self.enable(senha_inicial='Different-local-password')
        self.assertEqual(again.status_code,200,again.text);self.assertEqual(again.json(),r)
        self.db.refresh(u);self.assertEqual(u.senha_hash,old)
        self.assertEqual(self.enable(email='other@example.com').status_code,409)
        self.assertEqual(self.enable(perfil_institucional='GESTOR').status_code,409)
        self.assertEqual(self.enable(ativo=False).status_code,409)
        self.assertEqual(self.count('usuario_instituicao_acessos'),1)
        self.assertEqual(self.db.query(Usuario).filter_by(pessoa_id=self.person).count(),1)

    def test_email_owned_by_other_or_unassociated_account_conflicts(self):
        self.assertEqual(self.enable(email='ADMIN@example.invalid').status_code,422) # invalid TLD rejected at boundary
        self.db.rollback()
        with self.engine.begin() as c:c.execute(text("UPDATE usuarios SET email='taken@example.com' WHERE id=:id"),{'id':self.users['SUPORTE']})
        self.assertEqual(self.enable(email='TAKEN@example.com').status_code,409)
        self.assertEqual(self.db.query(Usuario).filter_by(pessoa_id=self.person).count(),0)
        from app.models.pessoa import Pessoa
        other = Pessoa(nome_completo='Other synthetic person', ativo=True)
        self.db.add(other)
        self.db.flush()
        self.db.get(Usuario, self.users['SUPORTE']).pessoa_id = other.id
        self.db.commit()
        self.assertEqual(self.enable(email='taken@example.com').status_code,409)
        self.assertEqual(self.db.query(Usuario).filter_by(pessoa_id=self.person).count(),0)

    def test_inactive_person_and_institution(self):
        for table,identity in [('pessoas',self.person),('instituicoes',self.institution)]:
            self.db.rollback()
            with self.engine.begin() as c:c.execute(text(f'UPDATE {table} SET ativo=false WHERE id=:id'),{'id':identity})
            self.assertEqual(self.enable().status_code,409)
            with self.engine.begin() as c:c.execute(text(f'UPDATE {table} SET ativo=true WHERE id=:id'),{'id':identity})
        self.assertEqual(self.db.query(Usuario).filter_by(pessoa_id=self.person).count(),0)

    def test_admin_only_and_sanitized_payload(self):
        for role in ('PROFISSIONAL','SUPORTE','ADMIN_CLINICA','UNKNOWN'):
            self.assertEqual(self.request('POST',self.path,self.data,role=role).status_code,403)
        self.assertEqual(self.request('POST',self.path,self.data,role=None).status_code,401)
        for patch_data in ({'perfil_institucional':'ADMIN'},{'senha_inicial':' '},{'senha_inicial':'é'*37},{'clinica_id':1},{'ator_usuario_id':1}):
            r=self.enable(**patch_data);self.assertEqual(r.status_code,422,r.text)
            self.assertNotIn('Local-test-credential',r.text)

    def test_rollback_after_account_creation(self):
        with patch.object(pessoas.AcessoPessoaOut,'model_validate',side_effect=RuntimeError('sensitive')):
            r=self.enable()
        self.assertEqual(r.status_code,500);self.assertNotIn('sensitive',r.text)
        self.assertEqual(self.db.query(Usuario).filter_by(pessoa_id=self.person).count(),0)
        self.assertEqual(self.count('usuario_instituicao_acessos'),0)

    def test_inactive_access_default_and_explicit_second_institution(self):
        data={k:v for k,v in self.data.items() if k!='ativo'}
        r=self.request('POST',self.path,data)
        self.assertEqual(r.status_code,200,r.text);self.assertFalse(r.json()['autorizacao']['ativo'])
        second=self.enable(instituicao_id=self.other)
        self.assertEqual(second.status_code,200,second.text)
        self.assertEqual(second.json()['usuario_id'],r.json()['usuario_id'])
        self.assertEqual(self.count('usuario_instituicao_acessos'),2)

    def test_real_concurrent_reuse(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from sqlalchemy.orm import Session
        from app.schemas.acesso_pessoa import AcessoPessoaCreate
        from app.services.acesso_pessoa import AcessoPessoaService
        barrier=Barrier(2)
        def provision():
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                result=AcessoPessoaService().enable(db,self.person,AcessoPessoaCreate(**self.data),actor_id=self.users['ADMIN'])
                ids=(result['usuario_id'],result['autorizacao'].id)
                db.commit()
                return ids
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=[pool.submit(provision) for _ in range(2)]
            results=[j.result(timeout=30) for j in jobs]
        self.assertEqual(results[0],results[1])
        self.assertEqual(self.db.query(Usuario).filter_by(pessoa_id=self.person).count(),1)

    def test_login_and_legacy_clinical_denial(self):
        from app.routers import auth
        from app.core.deps import get_usuario_atual
        from app.services.care_lines.access import authorized_line
        from fastapi import HTTPException
        from fastapi.security import OAuth2PasswordRequestForm
        r=self.enable().json()
        tokens=auth.login(OAuth2PasswordRequestForm(username=self.data['email'],password=self.data['senha_inicial']),self.db)
        user=get_usuario_atual(tokens['access_token'],self.db)
        self.assertEqual(user.id,r['usuario_id'])
        from app.models.modular import ModuloClinico
        if self.db.get(ModuloClinico,1) is None:
            self.db.add(ModuloClinico(id=1,nome='Neuro',slug='neurodesenvolvimento',ativo=True))
            self.db.flush()
        with self.assertRaises(HTTPException) as denied:
            authorized_line(self.db,user,'NEURO')
        self.assertEqual(denied.exception.status_code,403)
