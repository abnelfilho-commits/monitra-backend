"""Native professional lifecycle through HTTP on disposable PostgreSQL."""
import os
import unittest
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import text
from app.routers import identidades, vinculos_institucionais
from app.models.profissional import Profissional
from app.services.identidade import IdentidadeService, IdentidadeErro
from app.main import app as main_app
import test_operacao_assistencial_http as fixture


class LifecycleRoutesTests(unittest.TestCase):
    def test_registered_in_canonical_router(self):
        paths = {r.path for r in main_app.routes}
        for action in ('ativar', 'inativar'):
            self.assertIn('/admin/identidades/pessoas/{pessoa_id}/profissional/' + action, paths)


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class NativeProfessionalTests(unittest.TestCase):
    request = fixture.OperationalAuthorizationTests.request
    tearDown = fixture.OperationalAuthorizationTests.tearDown
    count = fixture.OperationalAuthorizationTests.count
    op = fixture.OperationalAuthorizationTests.op
    nominate = fixture.OperationalAuthorizationTests.nominate
    grant = fixture.OperationalAuthorizationTests.grant

    def setUp(self):
        fixture.OperationalAuthorizationTests.setUp(self)
        self.app.include_router(identidades.router)
        self.app.include_router(vinculos_institucionais.router)
        result = self.request('POST', '/admin/identidades/papeis', {
            'chave_idempotencia': str(uuid4()), 'pessoa': {'nome_completo': 'Native B', 'cpf': '11144477735'},
            'papel': 'PROFISSIONAL', 'ocupacao_id': self.occupation, 'motivo': 'Explicit native role'})
        self.assertEqual(result.status_code, 200, result.text)
        self.b_person = result.json()['pessoa_id']
        self.b_role = result.json()['profissional_id']
        self.path = f'/admin/identidades/pessoas/{self.b_person}/profissional'
        # Operational fixture uses self.path for its context endpoint.
        self.context_path = f'/operacao-assistencial/contextos/{self.context}'

    def change(self, action='ativar', **kwargs):
        return self.request('POST', self.path + '/' + action, **kwargs)

    def role(self):
        return self.db.query(Profissional).populate_existing().filter_by(id=self.b_role).one()

    def test_creation_inactive_activation_deactivation_idempotent(self):
        self.assertFalse(self.role().ativo)
        for action, active in (('ativar', True), ('ativar', True), ('inativar', False), ('inativar', False)):
            with patch.object(self.db, 'commit', wraps=self.db.commit) as commit:
                response = self.change(action)
                self.assertEqual(response.status_code, 200, response.text)
                commit.assert_called_once()
            self.assertEqual(response.json(), dict(profissional_id=self.b_role, pessoa_id=self.b_person, ativo=active))
            role = self.role()
            self.assertEqual(role.ativo, active)
            self.assertIsNone(role.clinica_id)
            self.assertEqual(role.pessoa_id, self.b_person)

    def test_admin_only_http_and_service(self):
        for action in ('ativar', 'inativar'):
            for actor in ('SUPORTE', 'ADMIN_CLINICA', 'PROFISSIONAL', 'UNKNOWN'):
                self.assertEqual(self.change(action, role=actor).status_code, 403)
            self.assertEqual(self.change(action, role=None).status_code, 401)
            self.assertEqual(self.change(action, role='INACTIVE').status_code, 401)
        with self.assertRaises(IdentidadeErro) as error:
            IdentidadeService().set_profissional_active(self.db, self.users['SUPORTE'], self.b_person, True)
        self.assertEqual(error.exception.code, 'ADMIN_REQUIRED')
        self.assertFalse(self.role().ativo)

    def test_missing_person_or_role(self):
        for person, code in ((2147483647, 'PERSON_NOT_FOUND'), (self.person, 'PROFESSIONAL_ROLE_NOT_FOUND')):
            for action in ('ativar', 'inativar'):
                r = self.request('POST', f'/admin/identidades/pessoas/{person}/profissional/{action}')
                self.assertEqual(r.status_code, 404, r.text)
                self.assertEqual(r.json()['detail']['code'], code)
        self.assertEqual(self.request('POST', '/admin/identidades/pessoas/0/profissional/ativar').status_code, 422)

    def test_legacy_clinic_role_is_not_changed(self):
        self.db.rollback()
        with self.engine.begin() as c:
            clinic = c.execute(text("INSERT INTO clinicas(nome) VALUES ('Rejected legacy fixture') RETURNING id")).scalar()
            c.execute(text('UPDATE profissionais SET clinica_id=:c WHERE id=:p'), {'c': clinic, 'p': self.b_role})
        for action in ('ativar', 'inativar'):
            r = self.change(action)
            self.assertEqual(r.status_code, 409, r.text)
            self.assertEqual(r.json()['detail']['code'], 'LEGACY_PROFESSIONAL_NOT_SUPPORTED')
        self.assertFalse(self.role().ativo)
        self.assertEqual(self.role().clinica_id, clinic)

    def test_only_role_state_changes_no_implicit_side_effects(self):
        tables = ('usuarios', 'usuario_instituicao_acessos', 'profissional_instituicoes',
                  'contexto_profissionais', 'concessoes_assistenciais', 'autoridades_delegacao',
                  'profissional_modulos')
        before = {t: self.count(t) for t in tables}
        role_before = dict(self.db.execute(text('SELECT * FROM profissionais WHERE id=:id'), {'id': self.b_role}).mappings().one())
        self.assertEqual(self.change().status_code, 200)
        self.assertEqual(before, {t: self.count(t) for t in tables})
        role_after = dict(self.db.execute(text('SELECT * FROM profissionais WHERE id=:id'), {'id': self.b_role}).mappings().one())
        self.assertEqual(role_after, {**role_before, 'ativo': True})

    def test_output_failure_rolls_back_and_service_never_commits(self):
        with patch.object(identidades.ProfissionalEstadoOut, 'model_validate', side_effect=RuntimeError('private')):
            r = self.change()
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('private', r.text)
        self.assertFalse(self.role().ativo)
        with patch.object(self.db, 'commit', wraps=self.db.commit) as commit:
            IdentidadeService().set_profissional_active(self.db, self.users['ADMIN'], self.b_person, True)
            commit.assert_not_called()
        self.db.rollback()
        self.assertFalse(self.role().ativo)

    def test_native_role_becomes_selector_eligible_without_clinic_or_clinical_grant(self):
        role_path = self.path
        self.path = self.context_path
        self.nominate()
        self.grant('ADMIN_CLINICA', 'CONTEXTO_ADMINISTRAR')
        access = self.request('POST', f'/admin/pessoas/{self.b_person}/acesso', {
            'email': 'native-b@example.com', 'senha_inicial': 'Synthetic-password',
            'instituicao_id': self.institution, 'perfil_institucional': 'PROFISSIONAL', 'ativo': True})
        self.assertEqual(access.status_code, 200, access.text)
        link = self.request('POST', '/admin/vinculos-institucionais/profissionais', {
            'profissional_id': self.b_role, 'instituicao_id': self.institution,
            'ocupacao_id': self.occupation, 'data_inicio': '2020-01-01', 'motivo': 'Explicit membership'})
        self.assertEqual(link.status_code, 200, link.text)
        def options():
            response = self.op(method='GET', role='ADMIN_CLINICA')
            self.assertEqual(response.status_code, 200, response.text)
            return [r['id'] for r in response.json()['profissionais']]
        self.assertNotIn(link.json()['id'], options())
        self.assertEqual(self.request('POST', role_path + '/ativar').status_code, 200)
        self.assertIn(link.json()['id'], options())
        self.assertIsNone(self.role().clinica_id)
        self.assertEqual(self.count('contexto_profissionais'), 0)
        self.assertEqual(self.count('concessoes_assistenciais'), 1)  # Only the pre-existing D administration grant.
        self.assertEqual(self.request('POST', role_path + '/inativar').status_code, 200)
        self.assertNotIn(link.json()['id'], options())
