"""Canonical patient activation and real HTTP PDF on disposable PostgreSQL."""
import os
import asyncio
import unittest
from types import SimpleNamespace
from urllib.parse import urlencode
from uuid import uuid4
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import text, event
from sqlalchemy.orm import Session
from app.models import Usuario
from app.models.paciente import Paciente
from app.routers import identidades, vinculos_institucionais, pacientes
from app.services.identidade import IdentidadeService, IdentidadeErro
from app.main import app as main_app
from app.core.security import criar_access_token
import test_operacao_assistencial_http as fixture


class RoutesTests(unittest.TestCase):
    def test_activation_only_registered(self):
        paths = {r.path for r in main_app.routes}
        self.assertIn('/admin/identidades/pessoas/{pessoa_id}/paciente/ativar', paths)
        self.assertNotIn('/admin/identidades/pessoas/{pessoa_id}/paciente/inativar', paths)


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class PatientLifecycleTests(unittest.TestCase):
    request = fixture.OperationalAuthorizationTests.request
    tearDown = fixture.OperationalAuthorizationTests.tearDown
    count = fixture.OperationalAuthorizationTests.count
    op = fixture.OperationalAuthorizationTests.op
    nominate = fixture.OperationalAuthorizationTests.nominate
    grant = fixture.OperationalAuthorizationTests.grant
    participation = fixture.OperationalAuthorizationTests.participation

    def setUp(self):
        fixture.OperationalAuthorizationTests.setUp(self)
        for router in (identidades.router, vinculos_institucionais.router, pacientes.router):
            self.app.include_router(router)
        r = self.request('POST', '/admin/identidades/papeis', {
            'chave_idempotencia': str(uuid4()), 'papel': 'PACIENTE',
            'pessoa': {'nome_completo': 'Synthetic native patient', 'cpf': '11144477735'},
            'motivo': 'Synthetic canonical preparation'})
        self.assertEqual(r.status_code, 200, r.text)
        self.native_person = r.json()['pessoa_id']
        self.native_patient = r.json()['paciente_id']
        self.activation = f'/admin/identidades/pessoas/{self.native_person}/paciente/ativar'

    def role(self):
        return self.db.query(Paciente).populate_existing().filter_by(id=self.native_patient).one()

    def read(self, person=None):
        return self.request('GET', f'/admin/pessoas/{person or self.native_person}/vinculos')

    def test_creation_activation_idempotence_and_persisted_read(self):
        self.assertFalse(self.role().ativo)
        self.assertFalse(self.read().json()['paciente_ativo'])
        for _ in range(2):
            with self.assertLogs('uvicorn.error.identidades', level='INFO') as audit:
                r = self.request('POST', self.activation)
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json(), dict(paciente_id=self.native_patient, pessoa_id=self.native_person, ativo=True))
            self.assertIn('actor_usuario_id=', audit.output[0])
            self.assertNotIn('11144477735', audit.output[0])
            self.assertNotIn('Synthetic native patient', audit.output[0])
            self.db.expire_all()
            self.assertTrue(self.role().ativo)
            self.assertIsNone(self.role().clinica_id)
            self.assertTrue(self.read().json()['paciente_ativo'])

    def test_admin_only_and_missing_targets(self):
        for actor in ('SUPORTE', 'ADMIN_CLINICA', 'PROFISSIONAL', 'UNKNOWN'):
            self.assertEqual(self.request('POST', self.activation, role=actor).status_code, 403)
        for actor in (None, 'INACTIVE'):
            self.assertEqual(self.request('POST', self.activation, role=actor).status_code, 401)
        with self.assertRaises(IdentidadeErro):
            IdentidadeService().activate_patient(self.db, self.users['SUPORTE'], self.native_person)
        for person, code in ((2147483647, 'PERSON_NOT_FOUND'),
                             (self.db.execute(text('SELECT pessoa_id FROM usuarios WHERE id=:u'), {'u': self.users['SUPORTE']}).scalar(), 'PATIENT_ROLE_NOT_FOUND')):
            r = self.request('POST', f'/admin/identidades/pessoas/{person}/paciente/ativar')
            self.assertEqual(r.status_code, 404, r.text)
            self.assertEqual(r.json()['detail']['code'], code)
        self.assertFalse(self.role().ativo)

    def test_legacy_with_or_without_clinic_rejected(self):
        # Existing fixture patient has no canonical role-creation provenance.
        r = self.request('POST', f'/admin/identidades/pessoas/{self.person}/paciente/ativar')
        self.assertEqual(r.status_code, 409, r.text)
        self.assertEqual(r.json()['detail']['code'], 'LEGACY_PATIENT_NOT_SUPPORTED')
        with self.engine.begin() as c:
            clinic = c.execute(text("INSERT INTO clinicas(nome) VALUES ('Synthetic legacy') RETURNING id")).scalar()
            c.execute(text('UPDATE pacientes SET clinica_id=:c WHERE id=:p'), {'c': clinic, 'p': self.native_patient})
        self.assertEqual(self.request('POST', self.activation).status_code, 409)
        self.assertFalse(self.role().ativo)

    def test_no_side_effects_and_independent_link_state(self):
        tables = ('usuarios', 'usuario_instituicao_acessos', 'paciente_instituicoes',
                  'profissional_instituicoes', 'contextos_assistenciais', 'contexto_assistencial_linhas',
                  'contexto_profissionais', 'concessoes_assistenciais', 'autoridades_delegacao',
                  'paciente_modulos', 'identidade_operacoes')
        before = {t: self.count(t) for t in tables}
        previous = dict(self.db.execute(text('SELECT * FROM pacientes WHERE id=:p'), {'p': self.native_patient}).mappings().one())
        self.assertEqual(self.request('POST', self.activation).status_code, 200)
        self.assertEqual(before, {t: self.count(t) for t in tables})
        after = dict(self.db.execute(text('SELECT * FROM pacientes WHERE id=:p'), {'p': self.native_patient}).mappings().one())
        self.assertEqual(after, {**previous, 'ativo': True})
        self.assertEqual(self.read().json()['pacientes'], [])
        missing = self.db.execute(text('SELECT pessoa_id FROM usuarios WHERE id=:u'), {'u': self.users['SUPORTE']}).scalar()
        self.assertIsNone(self.read(missing).json()['paciente_id'])
        self.assertIsNone(self.read(missing).json()['paciente_ativo'])

    def test_output_failure_rolls_back_without_success_audit(self):
        with patch.object(identidades.PacienteEstadoOut, 'model_validate', side_effect=RuntimeError('private')), patch.object(identidades.logger, 'info') as audit:
            r = self.request('POST', self.activation)
            audit.assert_not_called()
        self.assertEqual(r.status_code, 500)
        self.assertNotIn('private', r.text)
        self.assertFalse(self.role().ativo)
        with patch.object(self.db, 'commit', wraps=self.db.commit) as commit:
            IdentidadeService().activate_patient(self.db, self.users['ADMIN'], self.native_person)
            commit.assert_not_called()
        self.db.rollback()
        self.assertFalse(self.role().ativo)

    def test_concurrent_activation_independent_connections(self):
        self.db.rollback()
        barrier = Barrier(2)
        def activate(_):
            with Session(self.engine) as db:
                actor = db.get(Usuario, self.users['ADMIN'])
                connection_id = db.execute(text('SELECT pg_backend_pid()')).scalar()
                barrier.wait(timeout=10)
                result = identidades.activate_patient(self.native_person, db, actor)
                return connection_id, result.model_dump()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(activate, range(2)))
        self.assertNotEqual(results[0][0], results[1][0])
        expected = dict(paciente_id=self.native_patient, pessoa_id=self.native_person, ativo=True)
        self.assertEqual([r[1] for r in results], [expected, expected])
        self.assertTrue(self.role().ativo)
        self.assertEqual(self.request('POST', self.activation).json(), expected)

    def test_commit_failure_rolls_back_without_success_audit(self):
        with patch.object(self.db, 'commit', side_effect=RuntimeError('private commit failure')), patch.object(identidades.logger, 'info') as audit:
            response = self.request('POST', self.activation)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()['detail']['code'], 'IDENTITY_OPERATION_FAILED')
        audit.assert_not_called()
        with Session(self.engine) as independent:
            self.assertFalse(independent.get(Paciente, self.native_patient).ativo)

    def test_logging_failure_after_commit_preserves_http_success(self):
        with patch.object(identidades.logger, 'info', side_effect=RuntimeError('private logging failure')):
            response = self.request('POST', self.activation)
        self.assertEqual(response.status_code, 200, response.text)
        with Session(self.engine) as independent:
            self.assertTrue(independent.get(Paciente, self.native_patient).ativo)
        self.assertEqual(self.request('POST', self.activation).json(), response.json())

    def test_no_database_access_after_commit_for_audit(self):
        with Session(self.engine) as db:
            actor = db.get(Usuario, self.users['ADMIN'])
            committed = []
            def after_commit(session):
                committed.append(True)
            def before_execute(*args):
                if committed:
                    raise AssertionError('Database access after confirmed activation')
            event.listen(db, 'after_commit', after_commit)
            event.listen(self.engine, 'before_cursor_execute', before_execute)
            try:
                with self.assertLogs('uvicorn.error.identidades', level='INFO') as audit:
                    result = identidades.activate_patient(self.native_person, db, actor)
                self.assertTrue(result.ativo)
                self.assertEqual(len(audit.output), 1)
                self.assertTrue(committed)
            finally:
                event.remove(self.engine, 'before_cursor_execute', before_execute)

    def prepare_context(self):
        r = self.request('POST', '/admin/vinculos-institucionais/pacientes', {
            'paciente_id': self.native_patient, 'instituicao_id': self.institution,
            'tipo_vinculo': 'ASSISTENCIAL', 'data_inicio': '2020-01-01', 'motivo': 'Synthetic membership'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.request('POST', '/admin/contextos-assistenciais/', {
            'paciente_instituicao_id': r.json()['id'], 'data_inicio': '2020-01-01'})
        self.assertEqual(r.status_code, 201, r.text)
        self.context = r.json()['id']
        self.path = f'/operacao-assistencial/contextos/{self.context}'
        r = self.request('POST', f'/admin/contextos-assistenciais/{self.context}/linhas',
                         {'modulo_id': 3}, params={'instituicao_id': self.institution})
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(self.op('/saude-mental/ativar').status_code, 200)
        self.nominate()
        self.grant('ADMIN_CLINICA', 'CONTEXTO_ADMINISTRAR')
        self.assertEqual(self.participation().status_code, 200)
        self.grant('PROFISSIONAL', 'ASSISTENCIAL_LER')
        self.assertFalse(self.role().ativo)

    def pdf(self, role='PROFISSIONAL', context=None):
        # Existing LocalClient repeatedly returns http.request and decodes UTF-8;
        # a binary streaming response needs a yielding receive and raw bytes.
        async def run():
            events = []
            delivered = False
            async def receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {'type': 'http.request', 'body': b'', 'more_body': False}
                await asyncio.Event().wait()
            async def send(event):
                events.append(event)
            path = f'/pacientes/{self.native_patient}/relatorio-pdf'
            token = criar_access_token({'sub': str(self.users[role]), 'tipo': 'usuario'})
            scope = dict(type='http', asgi={'version': '3.0'}, http_version='1.1',
                         method='GET', scheme='http', path=path, raw_path=path.encode(),
                         query_string=urlencode({'care_line': 'MENTAL_HEALTH',
                                                 'contexto_assistencial_id': context or self.context}).encode(),
                         headers=[(b'authorization', ('Bearer ' + token).encode())],
                         client=('127.0.0.1', 1), server=('synthetic', 80), root_path='')
            await asyncio.wait_for(self.app(scope, receive, send), timeout=30)
            status = next(e['status'] for e in events if e['type'] == 'http.response.start')
            content = b''.join(e.get('body', b'') for e in events if e['type'] == 'http.response.body')
            return SimpleNamespace(status_code=status, content=content, text=content.decode(errors='replace'))
        return asyncio.run(run())


@unittest.skipUnless(os.getenv('G2C1_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class PatientReportHTTPTests(unittest.TestCase):
    setUp = PatientLifecycleTests.setUp
    tearDown = PatientLifecycleTests.tearDown
    request = PatientLifecycleTests.request
    op = PatientLifecycleTests.op
    nominate = PatientLifecycleTests.nominate
    grant = PatientLifecycleTests.grant
    participation = PatientLifecycleTests.participation
    role = PatientLifecycleTests.role
    read = PatientLifecycleTests.read
    prepare_context = PatientLifecycleTests.prepare_context
    pdf = PatientLifecycleTests.pdf

    def test_http_inactive_then_activated_real_pdf(self):
        self.prepare_context()
        state = self.read().json()
        self.assertFalse(state['paciente_ativo'])
        self.assertTrue(state['pacientes'][0]['ativo'])
        self.assertEqual(self.pdf().status_code, 404)
        self.assertEqual(self.request('POST', self.activation).status_code, 200)
        r = self.pdf()
        self.assertEqual(r.status_code, 200, r.text[:100])
        self.assertTrue(r.content.startswith(b'%PDF'))

    def test_http_active_without_authorization_denied(self):
        self.prepare_context()
        self.assertEqual(self.request('POST', self.activation).status_code, 200)
        for actor in ('ADMIN', 'UNKNOWN', 'SUPORTE'):
            response = self.pdf(role=actor)
            if actor == 'UNKNOWN':
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.text, '{"detail":"Perfil sem acesso assistencial."}')
                continue
            # Existing PDF route maps MentalHealthUnavailable to generic 500.
            # Preserve that contract here; importantly no PDF/content is exposed.
            self.assertEqual(response.status_code, 500)
            self.assertEqual(response.text, '{"detail":"Erro ao gerar Relatório Longitudinal Inteligente: Consulte o suporte."}')

    def test_http_foreign_institution_context_denied(self):
        self.prepare_context()
        self.assertEqual(self.request('POST', self.activation).status_code, 200)
        r = self.request('POST', '/admin/vinculos-institucionais/pacientes', {
            'paciente_id': self.native_patient, 'instituicao_id': self.other,
            'tipo_vinculo': 'ASSISTENCIAL', 'data_inicio': '2020-01-01', 'motivo': 'Other synthetic institution'})
        self.assertEqual(r.status_code, 200, r.text)
        r = self.request('POST', '/admin/contextos-assistenciais/', {
            'paciente_instituicao_id': r.json()['id'], 'data_inicio': '2020-01-01'})
        self.assertEqual(r.status_code, 201, r.text)
        foreign_context = r.json()['id']
        line = self.request('POST', f'/admin/contextos-assistenciais/{foreign_context}/linhas',
                            {'modulo_id': 3}, params={'instituicao_id': self.other})
        self.assertEqual(line.status_code, 201, line.text)
        activated = self.request('POST', f'/operacao-assistencial/contextos/{foreign_context}/saude-mental/ativar',
                                 params={'instituicao_id': self.other})
        self.assertEqual(activated.status_code, 200, activated.text)
        self.assertTrue(activated.json()['ativo'])
        # The same actor/patient works in the authorized context; only scope differs.
        self.assertEqual(self.pdf().status_code, 200)
        with patch.object(pacientes.ReportService, 'render', wraps=pacientes.ReportService().render) as render:
            response = self.pdf(context=foreign_context)
            render.assert_not_called()
        self.assertFalse(response.content.startswith(b'%PDF'))
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.text, '{"detail":"Erro ao gerar Relatório Longitudinal Inteligente: Consulte o suporte."}')
