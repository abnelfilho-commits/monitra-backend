"""IAM-N1.1 administrative reads on a disposable current-schema PostgreSQL."""
import os
import unittest
from unittest.mock import patch
from sqlalchemy import event, text
import test_fundacao_operacional_http as fixture


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class PersonReadTests(unittest.TestCase):
    setUp = fixture.OperationalHttpTests.setUp
    tearDown = fixture.OperationalHttpTests.tearDown
    request = fixture.OperationalHttpTests.request
    count = fixture.OperationalHttpTests.count

    def read(self, suffix, person=None, **kwargs):
        return self.request('GET', f'/admin/pessoas/{person or self.person}/{suffix}', **kwargs)

    def enable(self, **changes):
        response = self.request('POST', f'/admin/pessoas/{self.person}/acesso', dict(
            email='native@example.com', senha_inicial='Synthetic-password',
            instituicao_id=self.institution, perfil_institucional='SUPORTE', ativo=True, **changes))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_no_account_and_no_links_are_explicit(self):
        from app.models.pessoa import Pessoa
        p = Pessoa(nome_completo='No roles', ativo=True)
        self.db.add(p); self.db.commit()
        self.assertEqual(self.read('acessos', p.id).json(), dict(pessoa_id=p.id, usuario=None, autorizacoes=[]))
        self.assertEqual(self.read('vinculos', p.id).json(), dict(pessoa_id=p.id, paciente_id=None,
            profissional_id=None, profissional_ativo=None, pacientes=[], profissionais=[]))

    def test_canonical_professional_state_without_links_survives_fresh_read(self):
        from uuid import uuid4
        from app.routers import identidades
        self.app.include_router(identidades.router)
        created = self.request('POST', '/admin/identidades/papeis', {
            'chave_idempotencia': str(uuid4()), 'pessoa': {'nome_completo': 'Native B', 'cpf': '11144477735'},
            'papel': 'PROFISSIONAL', 'motivo': 'Explicit native role'})
        self.assertEqual(created.status_code, 200, created.text)
        person = created.json()['pessoa_id']
        professional = created.json()['profissional_id']
        for action, active in ((None, False), ('ativar', True), ('inativar', False)):
            if action:
                response = self.request('POST', f'/admin/identidades/pessoas/{person}/profissional/{action}')
                self.assertEqual(response.status_code, 200, response.text)
            self.db.close()
            response = self.read('vinculos', person)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json(), dict(pessoa_id=person, paciente_id=None,
                profissional_id=professional, profissional_ativo=active, pacientes=[], profissionais=[]))

    def test_professional_state_independent_of_link_state(self):
        with self.engine.begin() as c:
            c.execute(text('UPDATE profissionais SET pessoa_id=:p WHERE id=:id'),
                      {'p': self.person, 'id': self.professional})
            c.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2025-01-01')"),
                      {'p': self.professional, 'i': self.institution, 'o': self.occupation})
        for role_active, link_active in ((True, True), (False, True), (True, False)):
            self.db.close()
            with self.engine.begin() as c:
                c.execute(text('UPDATE profissionais SET ativo=:a WHERE id=:id'), {'a': role_active, 'id': self.professional})
                c.execute(text('UPDATE profissional_instituicoes SET ativo=:a WHERE profissional_id=:id'), {'a': link_active, 'id': self.professional})
            response = self.read('vinculos')
            self.assertEqual(response.status_code, 200, response.text)
            data = response.json()
            self.assertEqual(data['profissional_id'], self.professional)
            self.assertEqual(data['profissional_ativo'], role_active)
            self.assertEqual(data['profissionais'][0]['ativo'], link_active)

    def test_post_then_fresh_read_multiple_inactive_history_no_secrets(self):
        created = self.enable()
        second = self.request('POST', f'/admin/pessoas/{self.person}/acesso', dict(email='native@example.com',
            senha_inicial='Ignored-password', instituicao_id=self.other, perfil_institucional='GESTOR', ativo=False))
        self.assertEqual(second.status_code, 200, second.text)
        self.db.close()  # Read from a new transaction, not an in-memory POST result.
        response = self.read('acessos')
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data['usuario'], dict(id=created['usuario_id'], email='native@example.com', ativo=True))
        self.assertEqual([r['ativo'] for r in data['autorizacoes']], [True, False])
        self.assertEqual([r['perfil_institucional'] for r in data['autorizacoes']], ['SUPORTE', 'GESTOR'])
        self.assertEqual([r['instituicao_nome'] for r in data['autorizacoes']], ['Synthetic', 'Other'])
        for value in ('senha', 'hash', 'Synthetic-password', 'capabil', 'autoridade', 'participacao', 'clinica'):
            self.assertNotIn(value, response.text.lower())

    def test_inactive_account_and_institution_remain_visible(self):
        created = self.enable()
        with self.engine.begin() as c:
            c.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'), {'id': created['usuario_id']})
            c.execute(text('UPDATE instituicoes SET ativo=false WHERE id=:id'), {'id': self.institution})
        data = self.read('acessos').json()
        self.assertFalse(data['usuario']['ativo'])
        self.assertFalse(data['autorizacoes'][0]['instituicao_ativa'])
        self.assertTrue(data['autorizacoes'][0]['ativo'])  # Raw state, not inferred effective authorization.

    def test_links_include_both_explicit_roles_and_history(self):
        with self.engine.begin() as c:
            c.execute(text('UPDATE profissionais SET pessoa_id=:p WHERE id=:id'), {'p':self.person, 'id':self.professional})
            c.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio,data_fim,ativo) VALUES (:p,:i,:o,'2025-01-01','2025-12-31',false)"),
                      {'p':self.professional, 'i':self.institution, 'o':self.occupation})
        data = self.read('vinculos').json()
        self.assertEqual(data['paciente_id'], self.patient)
        self.assertEqual(data['profissional_id'], self.professional)
        self.assertEqual([r['id'] for r in data['pacientes']], self.links)
        self.assertEqual([r['instituicao_id'] for r in data['pacientes']], [self.institution, self.other])
        self.assertEqual(data['profissionais'][0]['data_fim'], '2025-12-31')
        self.assertFalse(data['profissionais'][0]['ativo'])

    def test_reads_only_select_and_never_commit_or_entitle(self):
        with self.engine.begin() as c:
            c.execute(text('UPDATE profissionais SET pessoa_id=:p WHERE id=:id'),
                      {'p': self.person, 'id': self.professional})
        statements = []
        def capture(conn, cursor, statement, params, context, many):
            statements.append(statement.strip().upper())
        event.listen(self.engine, 'before_cursor_execute', capture)
        try:
            with patch.object(self.db, 'commit', wraps=self.db.commit) as commit:
                for _ in range(2):
                    for suffix in ('acessos', 'vinculos'):
                        self.assertEqual(self.read(suffix).status_code, 200)
                commit.assert_not_called()
        finally:
            event.remove(self.engine, 'before_cursor_execute', capture)
        self.assertTrue(statements)
        self.assertTrue(all(s.startswith('SELECT') for s in statements), statements)
        for table in ('usuario_instituicao_acessos', 'autoridades_delegacao', 'concessoes_assistenciais', 'contexto_profissionais'):
            self.assertEqual(self.count(table), 0)
        self.assertEqual(self.request('GET','/saude-mental/pessoas',params={'instituicao_id':self.institution}).json()['itens'], [])

    def test_admin_only_missing_and_sanitized_error(self):
        from app.routers import pessoas
        for suffix in ('acessos', 'vinculos'):
            for role in ('ADMIN_CLINICA', 'PROFISSIONAL', 'SUPORTE', 'UNKNOWN'):
                self.assertEqual(self.read(suffix, role=role).status_code, 403)
            self.assertEqual(self.read(suffix, role=None).status_code, 401)
            self.assertEqual(self.read(suffix, token='invalid').status_code, 401)
            self.assertEqual(self.read(suffix, 2147483647).status_code, 404)
        with patch.object(pessoas.PessoaAdministrativaService, 'acessos', side_effect=RuntimeError('private')):
            response = self.read('acessos')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('private', response.text)

    def test_unassociated_legacy_account_is_not_inferred(self):
        with self.engine.begin() as c:
            c.execute(text("UPDATE pessoas SET email='SUPORTE@example.invalid' WHERE id=:p"), {'p':self.person})
        self.assertIsNone(self.read('acessos').json()['usuario'])
