"""Exercise the executor's shared validator on disposable PostgreSQL 18 only."""
import os
import unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from alembic import command
from test_m0_baseline import config
from scripts.g1_hml_validation import (
    validate_result, views, EXPECTED_NOT_NULL, EXPECTED_CONSTRAINTS,
)

URL = os.getenv('G1_TEST_POSTGRES_URL')


@unittest.skipUnless(URL, 'Requires disposable G1 PostgreSQL')
class OperationalValidatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.port not in (None, 5432, 55614) or url.database != 'm0_baseline':
            raise RuntimeError('Only the dedicated local G1 database is allowed')
        cls.admin = create_engine(url, isolation_level='AUTOCOMMIT')
        cls.database = 'g1_validator_' + uuid4().hex
        with cls.admin.connect() as c:
            if c.execute(text('SHOW server_version_num')).scalar()[:2] != '18':
                raise RuntimeError('PostgreSQL 18 required')
            c.execute(text('CREATE DATABASE ' + cls.database))
        cls.engine = create_engine(url.set(database=cls.database))
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'm0_baseline_v1')
            # Additional preserved HML views: synthetic structural stand-ins,
            # no HML definitions or clinical data are imported.
            c.execute(text('CREATE VIEW vw_dimensionamento_equipe AS SELECT 1 AS synthetic'))
            c.execute(text('CREATE VIEW vw_timeline_paciente AS SELECT 1 AS synthetic'))
            command.upgrade(config(c), 'g1_institucional_v1')

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:
            c.execute(text('DROP DATABASE ' + cls.database))
        cls.admin.dispose()

    def setUp(self):
        self.c = self.engine.connect()
        self.tx = self.c.begin()
        self.events = []
        self.prior = views(self.c, self.emit)

    def tearDown(self):
        self.tx.rollback()
        self.c.close()

    def emit(self, event, **data):
        self.events.append((event, data))

    def fail_closed(self, label):
        with self.assertRaisesRegex(RuntimeError, label):
            validate_result(self.c, self.prior, self.emit)
        event, data = self.events[-1]
        self.assertEqual(event, 'VALIDATION_MISMATCH')
        self.assertIn('expected', data)
        self.assertIn('actual', data)
        self.assertNotEqual(data['expected'], data['actual'])
        self.assertNotIn('password', str(data).lower())
        self.assertNotIn('postgresql://', str(data))
        return data

    def test_correct_catalogue_pg18_not_null_and_excludes_pass(self):
        validate_result(self.c, self.prior, self.emit)
        tables = [d for e, d in self.events if e == 'TABLE_VALIDATED']
        self.assertEqual(len(tables), 5)
        for result in tables:
            table = result['table']
            nn = [r for r in result['constraints'] if r['contype'] == 'n']
            self.assertEqual(len(nn), EXPECTED_CONSTRAINTS[table]['n'])
            self.assertEqual({r['columns'][0] for r in nn}, EXPECTED_NOT_NULL[table])
        self.assertEqual(sum(r['contype'] == 'x' for t in tables for r in t['constraints']), 3)

    def test_missing_not_null_fails(self):
        self.c.execute(text('ALTER TABLE instituicoes ALTER COLUMN criado_em DROP NOT NULL'))
        data = self.fail_closed('Conjunto de constraints divergente')
        self.assertEqual(data['expected']['n'], 6)
        self.assertEqual(data['actual']['n'], 5)

    def test_same_count_wrong_not_null_column_fails(self):
        self.c.execute(text('ALTER TABLE instituicoes ALTER COLUMN criado_em DROP NOT NULL'))
        self.c.execute(text('ALTER TABLE instituicoes ALTER COLUMN nome_fantasia SET NOT NULL'))
        self.fail_closed('Colunas NOT NULL divergentes')

    def test_other_constraint_class_missing_fails(self):
        self.c.execute(text('ALTER TABLE instituicoes DROP CONSTRAINT ck_instituicao_nome'))
        self.fail_closed('Conjunto de constraints divergente')

    def test_unknown_extra_constraint_fails(self):
        self.c.execute(text('ALTER TABLE instituicoes ADD CONSTRAINT unexpected CHECK (id > 0)'))
        self.fail_closed('Conjunto de constraints divergente')

    def test_each_exclude_missing_fails(self):
        for table, constraint in (
            ('paciente_instituicoes', 'ex_paciente_instituicao_vigencia'),
            ('profissional_instituicoes', 'ex_profissional_instituicao_vigencia'),
            ('paciente_profissionais', 'ex_paciente_profissional_vigencia'),
        ):
            with self.subTest(table=table):
                savepoint = self.c.begin_nested()
                try:
                    self.c.execute(text('ALTER TABLE ' + table + ' DROP CONSTRAINT ' + constraint))
                    self.fail_closed('Conjunto de constraints divergente')
                finally:
                    savepoint.rollback()

    def test_missing_index_fails(self):
        self.c.execute(text('DROP INDEX ix_instituicao_papeis_instituicao_id'))
        self.fail_closed('Quantidade de índices divergente')

    def test_wrong_revision_fails(self):
        self.c.execute(text("UPDATE alembic_version SET version_num='m0_baseline_v1'"))
        self.fail_closed('Revision final divergente')

    def test_changed_view_fails(self):
        self.c.execute(text('CREATE OR REPLACE VIEW vw_timeline_paciente AS SELECT 2 AS synthetic'))
        self.fail_closed('Views alteradas')

    def test_missing_view_fails(self):
        self.c.execute(text('DROP VIEW vw_timeline_paciente'))
        self.fail_closed('View esperada ausente')

    def test_missing_extension_fails(self):
        self.c.execute(text('DROP EXTENSION btree_gist CASCADE'))
        self.fail_closed('btree_gist ausente')
