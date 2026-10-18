"""Real HTTP + PostgreSQL search contract; only an explicitly disposable DB.

Run with G2_SEARCH_POSTGRES_URL pointing to localhost/g2_people_search in a
fresh isolated PostgreSQL container. No migrations or shared database fixtures.
"""
import json
import os
import socket
import threading
import time
import unittest
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
import uvicorn

URL = os.getenv('G2_SEARCH_POSTGRES_URL')


@unittest.skipUnless(URL, 'Explicit disposable PostgreSQL required')
class PeopleSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.database != 'g2_people_search':
            raise RuntimeError('Only isolated localhost/g2_people_search is allowed')
        from app.models.pessoa import Pessoa
        from app.database import get_db
        from app.core.deps import get_usuario_atual
        from app.routers.pessoas import router
        cls.engine = create_engine(URL)
        with cls.engine.connect() as connection:
            assert int(connection.scalar(text('SHOW server_version_num'))) // 10000 == 18
            assert connection.scalar(text('SHOW server_encoding')) == 'UTF8'
            assert not connection.scalar(text("SELECT count(*) FROM pg_extension WHERE extname='unaccent'"))
            if connection.scalar(text("SELECT to_regclass('public.pessoas')")):
                raise RuntimeError('Database must be fresh; refusing existing table')
        Pessoa.__table__.create(cls.engine)
        cls.sessions = sessionmaker(bind=cls.engine)
        with cls.sessions() as db:
            db.add_all([
                Pessoa(id=1, nome_completo='Álvaro José', nome_social='ZÉ', cpf='52998224725', ativo=True),
                Pessoa(id=2, nome_completo='Maria', nome_social='Jósefa', cpf='11144477735', ativo=False),
                Pessoa(id=3, nome_completo='Outro', nome_social=None),
                Pessoa(id=4, nome_completo='Jose\u0301 Campos', nome_social=None),
                Pessoa(id=5, nome_completo='Literal %_\\ Nome'),
            ] + [Pessoa(id=i, nome_completo=f'Pessoa fictícia {i}') for i in range(6, 31)]
              + [Pessoa(id=31, nome_completo='José Final')])
            db.commit()
        cls.statements = []
        def capture(conn, cursor, statement, params, context, many):
            cls.statements.append(statement)  # Deliberately never store parameter values.
        event.listen(cls.engine, 'before_cursor_execute', capture)
        def db_dependency():
            with cls.sessions() as db:
                yield db
        def actor(x_test_role: str = Header(default='ADMIN')):
            if x_test_role == 'NONE':
                raise HTTPException(401)
            return SimpleNamespace(id=1, perfil=x_test_role, ativo=True)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = db_dependency
        # Only identity is simulated; the real exigir_admin dependency is retained.
        app.dependency_overrides[get_usuario_atual] = actor
        cls.sock = socket.socket()
        cls.sock.bind(('127.0.0.1', 0))
        cls.base = f'http://127.0.0.1:{cls.sock.getsockname()[1]}/admin/pessoas/'
        cls.server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False))
        cls.thread = threading.Thread(target=cls.server.run, kwargs={'sockets': [cls.sock]}, daemon=True)
        cls.thread.start()
        for _ in range(100):
            if cls.server.started:
                break
            time.sleep(.05)
        if not cls.server.started:
            raise RuntimeError('HTTP test server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=5)
        cls.sock.close()
        cls.engine.dispose()

    def request(self, role='ADMIN', **params):
        req = Request(self.base + '?' + urlencode(params), headers={'X-Test-Role': role})
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def ids(self, **params):
        status, rows = self.request(**params)
        self.assertEqual(status, 200)
        self.assertIsInstance(rows, list)
        return [row['id'] for row in rows]

    def test_01_unfiltered_regression(self):
        self.assertEqual(self.ids(), list(range(1, 32)))
        self.assertEqual(self.ids(offset=1, limit=2), [2, 3])

    def test_02_full_name_substring(self):
        self.assertEqual(self.ids(nome='lvar'), [1])

    def test_03_social_name_substring(self):
        self.assertEqual(self.ids(nome='sefa'), [2])

    def test_04_case(self):
        self.assertEqual(self.ids(nome='MARIA'), [2])

    def test_05_accents_and_decomposed_unicode(self):
        for term in ('jose', 'JOSÉ', 'Jose\u0301', '  josé  '):
            with self.subTest(term=term):
                self.assertEqual(self.ids(nome=term), [1, 2, 4, 31])
        self.assertEqual(self.ids(nome='ZE'), [1])

    def test_06_exact_cpf(self):
        for cpf in ('52998224725', ' 529.982.247-25 '):
            self.assertEqual(self.ids(cpf=cpf), [1])

    def test_07_invalid_cpf(self):
        for cpf in ('123', '52998224724', '11111111111'):
            status, body = self.request(cpf=cpf)
            self.assertEqual(status, 422)
            self.assertEqual(body, {'detail': {'code': 'INVALID_PAYLOAD'}})
            self.assertNotIn(cpf, json.dumps(body))

    def test_08_invalid_name_length(self):
        for name in (' a ', 'a' * 101):
            self.assertEqual(self.request(nome=name)[0], 422)
        self.assertEqual(self.ids(nome='ab'), [])
        self.assertEqual(self.ids(nome='a' * 100), [])

    def test_09_empty_filters(self):
        self.assertEqual(self.ids(nome=' ', cpf='  '), self.ids())
        self.assertEqual(self.ids(nome='', cpf=''), self.ids())

    def test_10_combination_and(self):
        self.assertEqual(self.ids(nome='jose', cpf='11144477735'), [2])
        self.assertEqual(self.ids(nome='alvaro', cpf='11144477735'), [])

    def test_11_filtered_pagination_and_sql(self):
        self.statements.clear()
        self.assertEqual(self.ids(nome='jose', offset=2, limit=2), [4, 31])
        sql = next(s.upper() for s in self.statements if 'SELECT' in s.upper())
        self.assertLess(sql.index('WHERE'), sql.index('ORDER BY'))
        self.assertLess(sql.index('ORDER BY'), sql.index('LIMIT'))
        self.assertIn('STRPOS', sql)
        self.assertIn('NORMALIZE', sql)
        self.assertNotIn('jose', sql.lower())

    def test_12_ordering(self):
        self.assertEqual(self.ids(nome='jose'), [1, 2, 4, 31])
        self.assertEqual(self.ids(nome='jose'), [1, 2, 4, 31])

    def test_13_inactive_included(self):
        status, rows = self.request(nome='jose')
        self.assertEqual(status, 200)
        self.assertEqual([(r['id'], r['ativo']) for r in rows], [(1, True), (2, False), (4, True), (31, True)])

    def test_14_admin_and_response_contract(self):
        status, rows = self.request(cpf='52998224725')
        self.assertEqual(status, 200)
        self.assertEqual(set(rows[0]), {'id', 'nome_completo', 'nome_social', 'data_nascimento', 'sexo', 'cpf', 'email', 'telefone', 'ativo', 'criado_em', 'atualizado_em'})

    def test_15_forbidden_roles(self):
        for role in ('GESTOR', 'PROFISSIONAL', 'SUPORTE', 'ADMIN_CLINICA'):
            status, body = self.request(role=role, nome='jose')
            self.assertEqual(status, 403)
            self.assertEqual(set(body), {'detail'})

    def test_16_no_results(self):
        self.assertEqual(self.ids(nome='Inexistente'), [])

    def test_17_pagination_validation(self):
        for params in ({'offset': -1}, {'limit': 0}, {'limit': 101}, {'offset': 'bad'}):
            self.assertEqual(self.request(**params)[0], 422)

    def test_18_literal_wildcards(self):
        self.assertEqual(self.ids(nome='%_\\'), [5])
        self.assertEqual(self.ids(nome="' OR 1=1 --"), [])

    def test_19_unauthenticated(self):
        self.assertEqual(self.request(role='NONE')[0], 401)


if __name__ == '__main__':
    unittest.main()
