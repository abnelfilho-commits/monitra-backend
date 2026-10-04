"""W1C-H physical-only contract; synthetic data on disposable PostgreSQL 18."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from test_m0_baseline import config

ROOTS = ('registros_longitudinais', 'diagnosticos', 'pts', 'intervencoes')
REVISION = 'w1c_contexto_clinico_v1'
PARENT = 'w1b_permissoes_v1'
URL = os.getenv('M0_TEST_POSTGRES_URL')


class StructuralTests(unittest.TestCase):
    def test_head_and_no_descendant_context(self):
        from app.database import Base
        import app.models
        scripts = ScriptDirectory.from_config(config())
        self.assertEqual(scripts.get_heads(), ['w2a_saude_mental_v1'])
        self.assertEqual(scripts.get_revision(REVISION).down_revision, PARENT)
        for name in ('respostas_registro', 'avaliacoes_clinicas', 'pts_objetivos', 'agenda_cuidados', 'sessoes_assistenciais'):
            self.assertNotIn('contexto_assistencial_id', Base.metadata.tables[name].c)
        for name in ROOTS:
            column = Base.metadata.tables[name].c.contexto_assistencial_id
            self.assertTrue(column.nullable)
            self.assertIsNone(column.default)
            self.assertIsNone(column.server_default)
            self.assertNotIn('instituicao_id', Base.metadata.tables[name].c)


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL 18')
class PhysicalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = make_url(URL)
        if cls.url.host != '127.0.0.1' or cls.url.database != 'm0_baseline':
            raise RuntimeError('Disposable local database required')
        cls.admin = create_engine(cls.url, isolation_level='AUTOCOMMIT')
        cls.name = 'w1ch_' + uuid4().hex
        with cls.admin.connect() as c:
            if int(c.exec_driver_sql('SHOW server_version_num').scalar()) // 10000 != 18:
                raise RuntimeError('PG18 required')
            c.exec_driver_sql('CREATE DATABASE ' + cls.name)
        cls.engine = create_engine(cls.url.set(database=cls.name), connect_args={
            'options': '-c lock_timeout=5000 -c statement_timeout=15000'})
        with cls.engine.begin() as c:
            command.upgrade(config(c), REVISION)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:
            c.exec_driver_sql('DROP DATABASE ' + cls.name)
        cls.admin.dispose()

    def setUp(self):
        with self.engine.begin() as c:
            self.seed(c)

    def seed(self, c):
        self.actor = c.execute(text("INSERT INTO usuarios(nome,email,senha_hash) VALUES ('Synthetic',:e,'test') RETURNING id"), {'e': uuid4().hex+'@example.invalid'}).scalar_one()
        self.patient = c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar_one()
        self.other = c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Other synthetic') RETURNING id").scalar_one()
        self.modules = [c.execute(text("INSERT INTO modulos_clinicos(nome,slug) VALUES (:n,:n) RETURNING id"), {'n': uuid4().hex}).scalar_one() for _ in range(3)]
        self.form = c.execute(text("INSERT INTO formularios_modulo(modulo_id,nome,tipo) VALUES (:m,'Synthetic','LONGITUDINAL') RETURNING id"), {'m': self.modules[0]}).scalar_one()
        self.contexts = []
        for _ in range(2):
            institution = c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Synthetic','OUTRO') RETURNING id").scalar_one()
            link = c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'OUTRO','2020-01-01') RETURNING id"), {'p': self.patient, 'i': institution}).scalar_one()
            context = c.execute(text("INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,criado_por_usuario_id) VALUES (:l,:p,:i,'2020-01-01',:u) RETURNING id"), {'l': link, 'p': self.patient, 'i': institution, 'u': self.actor}).scalar_one()
            self.contexts.append(context)
            for module in self.modules[:2]:
                c.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id) VALUES (:c,:m)'), {'c': context, 'm': module})

    def insert(self, c, table, *, contextual=True, **changes):
        values = dict(paciente_id=self.patient, modulo_id=self.modules[0])
        if contextual:
            values['contexto_assistencial_id'] = self.contexts[0]
        values.update({
            'registros_longitudinais': dict(formulario_id=self.form, origem='PROFISSIONAL', data_registro='2026-01-01'),
            'diagnosticos': dict(descricao_clinica='Synthetic', medico_nome='Synthetic', data_diagnostico='2026-01-01'),
            'pts': dict(data_inicio='2026-01-01'),
            'intervencoes': dict(tipo='Synthetic', data_intervencao='2026-01-01'),
        }[table])
        values.update(changes)
        return c.execute(text('INSERT INTO '+table+' ('+', '.join(values)+') VALUES ('+', '.join(':'+k for k in values)+') RETURNING id'), values).scalar_one()

    def rejected(self, table, state, **changes):
        with self.engine.connect() as c:
            tx = c.begin()
            try:
                with self.assertRaises(IntegrityError) as caught:
                    self.insert(c, table, **changes)
                self.assertEqual(caught.exception.orig.pgcode, state)
            finally:
                tx.rollback()

    def test_catalog_matches_orm(self):
        import app.models
        from app.database import Base
        with self.engine.connect() as c:
            inspector = inspect(c)
            self.assertIn(['id', 'paciente_id'], [u['column_names'] for u in inspector.get_unique_constraints('contextos_assistenciais')])
            for table in ROOTS:
                with self.subTest(table=table):
                    column = next(x for x in inspector.get_columns(table) if x['name']=='contexto_assistencial_id')
                    self.assertTrue(column['nullable']); self.assertIsNone(column['default'])
                    self.assertEqual(str(column['type']), 'INTEGER')
                    actual = {f['name']: f for f in inspector.get_foreign_keys(table) if f['name'].startswith('fk_'+table+'_contexto_')}
                    expected = [f for f in Base.metadata.tables[table].foreign_key_constraints if f.name and f.name.startswith('fk_'+table+'_contexto_')]
                    self.assertEqual(len(actual), 2); self.assertEqual(len(expected), 2)
                    for fk in expected:
                        found = actual[fk.name]
                        self.assertEqual(found['constrained_columns'], [e.parent.name for e in fk.elements])
                        self.assertEqual(found['referred_columns'], [e.column.name for e in fk.elements])
                        self.assertEqual(found['referred_table'], fk.referred_table.name)
                        self.assertEqual(found['options']['ondelete'], 'RESTRICT')
                        self.assertEqual(found['options']['onupdate'], 'RESTRICT')
                    self.assertIn('ck_'+table+'_contexto_identidade', [x['name'] for x in inspector.get_check_constraints(table)])
                    self.assertIn('ix_'+table+'_contexto', [x['name'] for x in inspector.get_indexes(table)])
            index = next(x for x in inspector.get_indexes('pts') if x['name']=='uq_pts_contexto_linha_ativo')
            self.assertTrue(index['unique'])
            self.assertEqual(index['column_names'], ['contexto_assistencial_id','modulo_id'])
            self.assertIn('IS NOT NULL', index['dialect_options']['postgresql_where'])
            self.assertIn('ATIVO', index['dialect_options']['postgresql_where'])

    def test_all_roots_accept_legacy_and_contextual_without_operational_inference(self):
        with self.engine.begin() as c:
            # Inactive context/line is valid historical membership, not authorization.
            c.execute(text('UPDATE contextos_assistenciais SET ativo=false WHERE id=:id'), {'id': self.contexts[0]})
            for table in ROOTS:
                self.insert(c, table)
                identity = self.insert(c, table, contextual=False)
                self.assertIsNone(c.execute(text('SELECT contexto_assistencial_id FROM '+table+' WHERE id=:id'), {'id':identity}).scalar_one())

    def test_all_roots_reject_wrong_patient(self):
        for table in ROOTS:
            with self.subTest(table=table): self.rejected(table, '23503', paciente_id=self.other)

    def test_all_roots_reject_wrong_line(self):
        for table in ROOTS:
            with self.subTest(table=table): self.rejected(table, '23503', modulo_id=self.modules[2])

    def test_all_roots_reject_missing_context(self):
        for table in ROOTS:
            with self.subTest(table=table): self.rejected(table, '23503', contexto_assistencial_id=2147483647)

    def test_all_roots_reject_null_patient(self):
        for table in ROOTS:
            with self.subTest(table=table): self.rejected(table, '23514' if table=='intervencoes' else '23502', paciente_id=None)

    def test_all_roots_reject_null_module(self):
        for table in ROOTS:
            with self.subTest(table=table): self.rejected(table, '23514' if table=='pts' else '23502', modulo_id=None)

    def test_legacy_nullability_and_duplicates_preserved(self):
        with self.engine.begin() as c:
            self.insert(c, 'intervencoes', contextual=False, paciente_id=None)
            self.insert(c, 'pts', contextual=False, modulo_id=None)
            for _ in range(2): self.insert(c, 'pts', contextual=False)

    def test_pts_closed_active_contexts_and_lines(self):
        with self.engine.begin() as c:
            for _ in range(2): self.insert(c, 'pts', status='ENCERRADO')
            self.insert(c, 'pts')
            self.insert(c, 'pts', contexto_assistencial_id=self.contexts[1])
            self.insert(c, 'pts', modulo_id=self.modules[1])
        self.rejected('pts', '23505')

    def test_reopen_cannot_bypass_partial_unique(self):
        with self.engine.begin() as c:
            self.insert(c, 'pts')
            closed = self.insert(c, 'pts', status='ENCERRADO')
        with self.engine.connect() as c:
            tx = c.begin()
            try:
                with self.assertRaises(IntegrityError) as caught:
                    c.execute(text("UPDATE pts SET status='ATIVO' WHERE id=:id"), {'id':closed})
                self.assertEqual(caught.exception.orig.diag.constraint_name, 'uq_pts_contexto_linha_ativo')
            finally: tx.rollback()

    def test_no_destructive_cascade(self):
        with self.engine.begin() as c: self.insert(c, 'intervencoes')
        for sql in ('DELETE FROM contexto_assistencial_linhas WHERE contexto_assistencial_id=:id',
                    'DELETE FROM contextos_assistenciais WHERE id=:id'):
            with self.engine.connect() as c:
                tx = c.begin()
                try:
                    with self.assertRaises(IntegrityError): c.execute(text(sql), {'id':self.contexts[0]})
                finally: tx.rollback()

    def test_downgrade_blocked_for_each_root(self):
        for table in ROOTS:
            with self.subTest(table=table), self.engine.connect() as c:
                tx = c.begin()
                try:
                    # Isolate the root under test from rows created by prior cases.
                    for root in ROOTS:
                        c.exec_driver_sql("DELETE FROM " + root + " WHERE contexto_assistencial_id IS NOT NULL")
                    self.insert(c, table)
                    with self.assertRaisesRegex(RuntimeError, 'W1C_DOWNGRADE_BLOCKED_CONTEXTUAL_HISTORY'):
                        command.downgrade(config(c), PARENT)
                    self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), REVISION)
                finally: tx.rollback()

    def test_downgrade_rejects_stale_snapshot(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            tx = c.begin()
            try:
                with self.assertRaisesRegex(RuntimeError, 'W1C_READ_COMMITTED_REQUIRED'):
                    command.downgrade(config(c), PARENT)
            finally: tx.rollback()

    def test_concurrent_active_pts(self):
        barrier = Barrier(2)
        def write():
            try:
                with self.engine.begin() as c:
                    barrier.wait(timeout=10)
                    self.insert(c, 'pts')
                return 'persisted'
            except IntegrityError as exc:
                return exc.orig.diag.constraint_name
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _:write(), range(2)))
        self.assertCountEqual(results, ['persisted', 'uq_pts_contexto_linha_ativo'])

    def test_incremental_no_backfill_downgrade_reupgrade(self):
        name = 'w1ch_roundtrip_'+uuid4().hex
        with self.admin.connect() as c: c.exec_driver_sql('CREATE DATABASE '+name)
        engine = create_engine(self.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c), REVISION)
                command.downgrade(config(c), PARENT)
                self.seed(c)
                for table in ROOTS: self.insert(c, table, contextual=False)
                before = {t:c.exec_driver_sql('SELECT row_to_json(r) FROM '+t+' r').scalars().all() for t in ROOTS}
                views = c.exec_driver_sql("SELECT viewname,definition FROM pg_views WHERE schemaname='public' ORDER BY viewname").all()
                command.upgrade(config(c), REVISION)
                for table in ROOTS:
                    after = c.exec_driver_sql('SELECT row_to_json(r) FROM '+table+' r').scalars().all()
                    for row in after: self.assertIsNone(row.pop('contexto_assistencial_id'))
                    self.assertEqual(after, before[table])
                self.assertEqual(views,c.exec_driver_sql("SELECT viewname,definition FROM pg_views WHERE schemaname='public' ORDER BY viewname").all())
                command.downgrade(config(c), PARENT)
                for table in ROOTS:
                    self.assertNotIn('contexto_assistencial_id',[x['name'] for x in inspect(c).get_columns(table)])
                    self.assertEqual(before[table],c.exec_driver_sql('SELECT row_to_json(r) FROM '+table+' r').scalars().all())
                command.upgrade(config(c), REVISION)
                self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(),REVISION)
        finally:
            engine.dispose()
            with self.admin.connect() as c: c.exec_driver_sql('DROP DATABASE '+name)
