"""Mandatory-line migrations on a disposable database only; synthetic rows."""
import importlib.util
import os
from pathlib import Path
import unittest
from uuid import uuid4
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations

URL = os.getenv('CARDIO_GATE1_POSTGRES_URL')
ALLOWED = 'postgresql+psycopg2://gate1@127.0.0.1/gate1_test'


@unittest.skipUnless(URL, 'Requires disposable Gate 1 PostgreSQL')
class MandatoryLineMigrationTests(unittest.TestCase):
    def setUp(self):
        if URL != ALLOWED:
            raise RuntimeError('Only the disposable Gate 1 database is allowed.')
        self.schema = 'gate1_' + uuid4().hex
        self.admin = create_engine(URL)
        with self.admin.begin() as conn:
            conn.execute(text('CREATE SCHEMA ' + self.schema))
        self.engine = create_engine(URL, connect_args={'options': '-csearch_path=' + self.schema})
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE modulos_clinicos (id INT PRIMARY KEY, slug TEXT UNIQUE)'))
            conn.execute(text("INSERT INTO modulos_clinicos VALUES (1,'neurodesenvolvimento'),(2,'cardiometabolico')"))
            conn.execute(text('CREATE TABLE diagnosticos (id INT PRIMARY KEY, paciente_id INT)'))
            conn.execute(text('CREATE TABLE intervencoes (id INT PRIMARY KEY, modulo_id INT REFERENCES modulos_clinicos(id))'))
            conn.execute(text('CREATE TABLE intervencoes_cardiometabolicas (id INT PRIMARY KEY)'))

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        self.admin.dispose()

    def upgrade(self, conn, revision):
        path = next((Path(__file__).resolve().parents[1] / 'alembic/versions').glob(revision + '_*.py'))
        spec = importlib.util.spec_from_file_location(revision, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()

    def test_unknown_diagnoses_block_without_deleting_or_assigning(self):
        with self.engine.begin() as conn:
            conn.execute(text('INSERT INTO diagnosticos VALUES (10,1)'))
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as conn:
                self.upgrade(conn, '8c01a0d1a000')
                self.upgrade(conn, '8c01a0d1a001')
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT count(*) FROM diagnosticos')).scalar(), 1)
            self.assertNotIn('modulo_id', [c['name'] for c in inspect(conn).get_columns('diagnosticos')])

    def test_unknown_interventions_block_without_fallback(self):
        with self.engine.begin() as conn:
            conn.execute(text('INSERT INTO intervencoes VALUES (10,NULL)'))
        with self.assertRaises(RuntimeError):
            with self.engine.begin() as conn:
                self.upgrade(conn, '8c01a0d1a002')
        with self.engine.connect() as conn:
            self.assertIsNone(conn.execute(text('SELECT modulo_id FROM intervencoes')).scalar())

    def test_coherent_data_constraints_and_proven_cardio_source(self):
        with self.engine.begin() as conn:
            conn.execute(text('INSERT INTO intervencoes VALUES (1,1),(2,2)'))
            conn.execute(text('INSERT INTO intervencoes_cardiometabolicas VALUES (3)'))
            for revision in ('8c01a0d1a000', '8c01a0d1a001', '8c01a0d1a002', '8c01a0d1a003'):
                self.upgrade(conn, revision)
            for table in ('diagnosticos', 'intervencoes', 'intervencoes_cardiometabolicas'):
                column = next(c for c in inspect(conn).get_columns(table) if c['name'] == 'modulo_id')
                self.assertFalse(column['nullable'])
                self.assertIsNone(column['default'])
                for value in ('NULL', '999'):
                    with self.assertRaises(IntegrityError):
                        with conn.begin_nested():
                            conn.execute(text('INSERT INTO ' + table + ' (id,modulo_id) VALUES (99,' + value + ')'))
            self.assertEqual(conn.execute(text('SELECT modulo_id FROM intervencoes_cardiometabolicas')).scalar(), 2)
            self.assertEqual(list(conn.execute(text('SELECT modulo_id FROM intervencoes ORDER BY id')).scalars()), [1,2])
