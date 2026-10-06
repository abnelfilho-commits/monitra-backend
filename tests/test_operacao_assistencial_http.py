"""Explicit ADMIN -> A -> D -> B scenario; real JWT and disposable PG18."""
import os
import unittest
from unittest.mock import patch
from sqlalchemy import text
from app.routers import operacao_assistencial as api
from app.main import app as main_app
import test_fundacao_operacional_http as fixture


class RoutesTests(unittest.TestCase):
    def test_registered(self):
        paths={r.path for r in main_app.routes}
        self.assertIn('/operacao-assistencial/contextos/{contexto_id}/grants',paths)
        self.assertIn('/operacao-assistencial/contextos/{contexto_id}/saude-mental/ativar',paths)


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Disposable PG18 required')
class OperationalAuthorizationTests(unittest.TestCase):
    request = fixture.OperationalHttpTests.request
    tearDown = fixture.OperationalHttpTests.tearDown
    count = fixture.OperationalHttpTests.count

    def setUp(self):
        fixture.OperationalHttpTests.setUp(self)
        self.app.include_router(api.router)
        self.root={};self.professional_links={}
        with self.engine.begin() as c:
            for role in ('SUPORTE','ADMIN_CLINICA','PROFISSIONAL','UNKNOWN'):
                p=c.execute(text('INSERT INTO pessoas(nome_completo) VALUES (:n) RETURNING id'),dict(n=role)).scalar()
                c.execute(text('UPDATE usuarios SET pessoa_id=:p WHERE id=:u'),dict(p=p,u=self.users[role]))
                self.root[role]=c.execute(text("INSERT INTO usuario_instituicao_acessos(usuario_id,instituicao_id,perfil_institucional,ativo) VALUES (:u,:i,'SUPORTE',true) RETURNING id"),dict(u=self.users[role],i=self.institution)).scalar()
                if role in ('PROFISSIONAL','UNKNOWN'):
                    pr=c.execute(text('INSERT INTO profissionais(nome,pessoa_id,ativo) VALUES (:n,:p,true) RETURNING id'),dict(n=role,p=p)).scalar()
                    self.professional_links[role]=c.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2020-01-01') RETURNING id"),dict(p=pr,i=self.institution,o=self.occupation)).scalar()
        # Match the explicitly prepared institutional membership period.
        context=self.request('POST','/admin/contextos-assistenciais/',dict(paciente_instituicao_id=self.links[0],data_inicio='2026-01-01'))
        self.assertEqual(context.status_code,201,context.text)
        self.context=context.json()['id'];self.path=f'/operacao-assistencial/contextos/{self.context}'
        line=self.request('POST',f'/admin/contextos-assistenciais/{self.context}/linhas',{'modulo_id':3},params={'instituicao_id':self.institution})
        self.assertEqual(line.status_code,201,line.text);self.assertFalse(line.json()['ativo'])

    def op(self, suffix='', payload=None, role='ADMIN', method='POST', institution=None):
        return self.request(method,self.path+suffix,payload,params={'instituicao_id':institution or self.institution},role=role)

    def nominate(self):
        r=self.op('/autoridades/bootstrap',dict(usuario_instituicao_acesso_id=self.root['SUPORTE'],capacidades=['CONTEXTO_ADMINISTRAR','ASSISTENCIAL_LER','ASSISTENCIAL_REGISTRAR'],motivo='Explicit nomination'))
        self.assertEqual(r.status_code,200,r.text);return r

    def grant(self, role, cap):
        r=self.op('/grants',dict(usuario_instituicao_acesso_id=self.root[role],capacidade=cap,motivo='Explicit grant'),role='SUPORTE')
        self.assertEqual(r.status_code,200,r.text);return r.json()

    def participation(self):
        return self.op('/participacoes',dict(profissional_instituicao_id=self.professional_links['PROFISSIONAL'],data_inicio='2026-01-01',motivo='Explicit participation'),role='ADMIN_CLINICA')

    def people(self, role):
        r=self.request('GET','/saude-mental/pessoas',params={'instituicao_id':self.institution},role=role)
        self.assertEqual(r.status_code,200,r.text);return r.json()['itens']

    def test_complete_explicit_scenario_and_revoke(self):
        self.assertEqual(self.people('PROFISSIONAL'),[])
        self.assertEqual(self.op('/saude-mental/ativar').status_code,200)
        self.assertEqual(self.count('concessoes_assistenciais'),0)
        self.nominate()
        self.assertEqual(self.count('concessoes_assistenciais'),0)
        self.assertEqual(self.op('/participacoes',dict(profissional_instituicao_id=self.professional_links['PROFISSIONAL'],data_inicio='2026-01-01',motivo='Denied A'),role='SUPORTE').status_code,403)
        self.grant('ADMIN_CLINICA','CONTEXTO_ADMINISTRAR')
        self.assertEqual(self.participation().status_code,200)
        self.assertEqual(self.people('PROFISSIONAL'),[])
        read=self.grant('PROFISSIONAL','ASSISTENCIAL_LER')
        self.grant('PROFISSIONAL','ASSISTENCIAL_REGISTRAR')
        self.assertEqual([r['contexto_assistencial_id'] for r in self.people('PROFISSIONAL')],[self.context])
        self.assertEqual(self.people('UNKNOWN'),[])
        self.assertEqual(self.people('ADMIN'),[])
        self.assertEqual(self.people('SUPORTE'),[])
        self.assertEqual(self.people('ADMIN_CLINICA'),[])
        r=self.request('GET',f'/saude-mental/pessoas/{self.person}/contextos/{self.context}',params={'instituicao_id':self.institution},role='PROFISSIONAL')
        self.assertEqual(r.status_code,200,r.text)
        revoked=self.op(f"/grants/{read['id']}/revogar",{'motivo':'Explicit revoke'},role='SUPORTE')
        self.assertEqual(revoked.status_code,200,revoked.text)
        self.assertEqual(self.people('PROFISSIONAL'),[])
        self.assertEqual(self.request('GET',f'/saude-mental/pessoas/{self.person}/contextos/{self.context}',params={'instituicao_id':self.institution},role='PROFISSIONAL').status_code,404)

    def test_state_permissions_do_not_infer_roles(self):
        admin=self.op(method='GET').json()
        self.assertTrue(admin['acoes']['bootstrap'])
        self.assertEqual(admin['acoes']['conceder_capacidades'],[])
        self.assertFalse(admin['acoes']['administrar_participacao'])
        self.assertEqual(self.op(method='GET',role='UNKNOWN').status_code,403)
        self.nominate()
        a=self.op(method='GET',role='SUPORTE').json()['acoes']
        self.assertEqual(len(a['conceder_capacidades']),3)
        self.assertFalse(a['administrar_participacao'])
        self.grant('ADMIN_CLINICA','CONTEXTO_ADMINISTRAR')
        d=self.op(method='GET',role='ADMIN_CLINICA').json()['acoes']
        self.assertTrue(d['administrar_participacao']);self.assertEqual(d['conceder_capacidades'],[])
        r=self.request('GET','/operacao-assistencial/contextos',params={'instituicao_id':self.institution},role='UNKNOWN')
        self.assertEqual(r.json(),[])

    def test_admin_no_grant_revoke_self_and_recovery_rules(self):
        self.nominate()
        read=self.grant('PROFISSIONAL','ASSISTENCIAL_LER')
        body=dict(usuario_instituicao_acesso_id=self.root['PROFISSIONAL'],capacidade='ASSISTENCIAL_LER',motivo='Denied')
        self.assertEqual(self.op('/grants',body).status_code,403)
        self.assertEqual(self.op(f"/grants/{read['id']}/revogar",{'motivo':'Denied'}).status_code,403)
        body['usuario_instituicao_acesso_id']=self.root['SUPORTE']
        self.assertEqual(self.op('/grants',body,role='SUPORTE').json()['detail']['code'],'SELF_GRANT_DENIED')
        recovery=dict(usuario_instituicao_acesso_id=self.root['ADMIN_CLINICA'],capacidades=['ASSISTENCIAL_LER'],motivo='Recovery')
        self.assertEqual(self.op('/autoridades/recovery',recovery).json()['detail']['code'],'ELIGIBLE_AUTHORITY_EXISTS')
        self.assertEqual(self.op('/autoridades/bootstrap',recovery).json()['detail']['code'],'BOOTSTRAP_ALREADY_PERFORMED')

    def test_line_idempotence_isolation_and_closed_context(self):
        self.assertEqual(self.op('/saude-mental/ativar',role='SUPORTE').status_code,403)
        self.assertEqual(self.op('/saude-mental/ativar',institution=self.other).status_code,403)
        for _ in range(2):self.assertTrue(self.op('/saude-mental/ativar').json()['ativo'])
        self.assertFalse(self.op('/saude-mental/desativar').json()['ativo'])
        self.assertEqual(self.count('concessoes_assistenciais'),0)
        self.assertEqual(self.count('contexto_profissionais'),0)
        self.db.rollback()
        with self.engine.begin() as c:c.execute(text("UPDATE contextos_assistenciais SET data_fim='2026-12-31' WHERE id=:id"),dict(id=self.context))
        self.assertEqual(self.op('/saude-mental/ativar').json()['detail']['code'],'CONTEXT_NOT_OPEN')

    def test_rollback_before_commit_and_get_no_commit(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.assertEqual(self.op(method='GET').status_code,200);commit.assert_not_called()
        with patch.object(api.ContextoLinhaOut,'model_validate',side_effect=RuntimeError('private secret')):
            r=self.op('/saude-mental/ativar')
        self.assertEqual(r.status_code,500);self.assertNotIn('private secret',r.text)
        self.assertFalse(self.op(method='GET').json()['linha']['ativo'])

    def test_transport_and_eligibility(self):
        self.assertEqual(self.op(method='GET',role=None).status_code,401)
        self.assertEqual(self.request('GET',self.path).status_code,422)
        self.assertEqual(self.op('/grants',dict(usuario_instituicao_acesso_id=1,capacidade='ADMIN',motivo='x')).status_code,422)
        self.assertEqual(self.op('/grants',dict(usuario_instituicao_acesso_id=1,capacidade='ASSISTENCIAL_LER',motivo='x',ator_usuario_id=1)).status_code,422)
        self.nominate();self.grant('ADMIN_CLINICA','CONTEXTO_ADMINISTRAR')
        self.db.rollback()
        with self.engine.begin() as c:c.execute(text('UPDATE profissional_instituicoes SET ativo=false WHERE id=:id'),dict(id=self.professional_links['PROFISSIONAL']))
        self.assertEqual(self.participation().json()['detail']['code'],'PROFESSIONAL_LINK_INELIGIBLE')
        state=self.op(method='GET',role='SUPORTE').json()
        self.assertNotIn(self.professional_links['PROFISSIONAL'],[p['id'] for p in state['profissionais']])
