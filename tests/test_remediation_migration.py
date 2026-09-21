"""Promotion chain on PG18 only; a synthetic schema at the HML revision.

The fixture models the affected pre-promotion tables, not an HML dump.
Historical migrations outside this promotion are not silently reconstructed.
"""
import os
from pathlib import Path
import unittest
from uuid import uuid4

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

ROOT = Path(__file__).resolve().parents[1]
URL = os.getenv('REMEDIATION_POSTGRES_URL')
ALLOWED = 'postgresql+psycopg2://gate1@127.0.0.1/gate1_test'


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL 18')
class RemediationTests(unittest.TestCase):
    def setUp(self):
        if URL != ALLOWED:
            raise RuntimeError('Only disposable remediation database allowed')
        self.admin = create_engine(URL)
        self.schema = 'remediation_' + uuid4().hex
        with self.admin.begin() as conn:
            self.assertEqual(int(conn.execute(text('SHOW server_version_num')).scalar()) // 10000, 18)
            conn.execute(text('CREATE SCHEMA ' + self.schema))
        self.engine = create_engine(URL, connect_args={'options': '-csearch_path=' + self.schema})
        config = Config(str(ROOT / 'alembic.ini'))
        config.set_main_option('script_location', str(ROOT / 'alembic'))
        self.scripts = ScriptDirectory.from_config(config)
        with self.engine.begin() as conn:
            for sql in (
                'CREATE TABLE pacientes (id INTEGER PRIMARY KEY)',
                'CREATE TABLE modulos_clinicos (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, ativo BOOLEAN)',
                'CREATE TABLE paciente_modulos (id SERIAL PRIMARY KEY, paciente_id INTEGER REFERENCES pacientes(id), modulo_id INTEGER REFERENCES modulos_clinicos(id), ativo BOOLEAN, data_inicio DATE, data_fim DATE, observacao TEXT, criado_em TIMESTAMP DEFAULT now())',
                'CREATE TABLE intervencoes (id INTEGER PRIMARY KEY, paciente_id INTEGER REFERENCES pacientes(id), descricao TEXT, data_intervencao DATE)',
                'CREATE TABLE responsaveis (id INTEGER PRIMARY KEY)',
                'CREATE TABLE formularios_modulo (id INTEGER PRIMARY KEY, modulo_id INTEGER REFERENCES modulos_clinicos(id), tipo TEXT)',
                'CREATE TABLE registros_longitudinais (id INTEGER PRIMARY KEY, paciente_id INTEGER REFERENCES pacientes(id), modulo_id INTEGER REFERENCES modulos_clinicos(id), formulario_id INTEGER REFERENCES formularios_modulo(id), data_registro DATE)',
                'CREATE TABLE whatsapp_conversas (id INTEGER PRIMARY KEY, responsavel_id INTEGER REFERENCES responsaveis(id), paciente_id INTEGER REFERENCES pacientes(id), etapa_atual TEXT, data_referencia DATE, respostas_json JSON, telefone TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)',
                'CREATE TABLE alembic_version (version_num VARCHAR(32) PRIMARY KEY)',
                "INSERT INTO alembic_version VALUES ('fb27d5139e1e')",
                "INSERT INTO modulos_clinicos VALUES (1,'neurodesenvolvimento',true),(2,'cardiometabolico',true)",
            ):
                conn.execute(text(sql))
            from fixtures.cardio_intervention_schema import create_cardio_intervention_table
            create_cardio_intervention_table(conn, pre_line=True)
            # Actual historical diagnosis migration: all original columns/FK/indexes.
            module = self.scripts.get_revision('a2464f3d64fc').module
            with Operations.context(MigrationContext.configure(conn)):
                module.upgrade()

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        self.admin.dispose()

    def upgrade(self, target):
        with self.engine.begin() as conn:
            context = MigrationContext.configure(conn, opts={
                'fn': lambda heads, ctx: self.scripts._upgrade_revs(target, heads)})
            with Operations.context(context):
                context.run_migrations()

    def seed(self):
        with self.engine.begin() as c:
            for sql in (
                'INSERT INTO pacientes SELECT generate_series(1,7)',
                "INSERT INTO diagnosticos (id,paciente_id,descricao_clinica,data_diagnostico,medico_nome,observacoes) SELECT i,i,'Synthetic diagnosis '||i,DATE '2026-06-09','Synthetic','Preserve exactly' FROM generate_series(1,5) i",
                "INSERT INTO intervencoes SELECT i,1,'Synthetic intervention '||i,DATE '2026-06-09' FROM generate_series(1,16) i",
                "INSERT INTO intervencoes_cardiometabolicas (id,paciente_id,tipo,descricao) VALUES (1,6,'synthetic','Synthetic Cardio'),(2,7,'synthetic','Synthetic Cardio')",
                "INSERT INTO paciente_modulos (paciente_id,modulo_id,ativo,data_inicio,observacao) SELECT i,1,true,DATE '2026-07-01','Synthetic Neuro' FROM generate_series(1,7) i",
                "INSERT INTO paciente_modulos (paciente_id,modulo_id,ativo) VALUES (7,2,true)",
                "INSERT INTO formularios_modulo VALUES (3,2,'REGISTRO_DIARIO')",
                "INSERT INTO registros_longitudinais SELECT i,6,2,3,DATE '2026-06-09' FROM generate_series(1,3) i",
                'INSERT INTO responsaveis VALUES (3)',
                "INSERT INTO whatsapp_conversas VALUES (1,3,NULL,'INICIO',NULL,'{}','synthetic',TIMESTAMP '2026-07-20',TIMESTAMP '2026-08-18')",
            ):
                c.execute(text(sql))

    def remediate(self):
        # Execute the exact approved operator script, including its transaction.
        raw = self.engine.raw_connection()
        try:
            with raw.cursor() as cursor:
                cursor.execute((ROOT / 'scripts/sql/hml_remediation_approved.sql').read_text())
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()

    def snapshot(self, table):
        with self.engine.connect() as c:
            return list(c.execute(text("SELECT to_jsonb(t)-'modulo_id' FROM " + table + ' t ORDER BY id')).scalars())

    def test_1_inventory_preserved_end_to_end(self):
        self.seed()
        before = {t: self.snapshot(t) for t in ('diagnosticos', 'intervencoes', 'intervencoes_cardiometabolicas', 'paciente_modulos', 'registros_longitudinais')}
        self.upgrade('8c01a0d1a000')
        self.remediate()
        self.upgrade('head')
        for t in ('diagnosticos', 'intervencoes', 'intervencoes_cardiometabolicas'):
            self.assertEqual(self.snapshot(t), before[t])
        with self.engine.connect() as c:
            for table, count, line in (('diagnosticos',5,1), ('intervencoes',16,1), ('intervencoes_cardiometabolicas',2,2)):
                self.assertEqual(c.execute(text('SELECT count(*) FROM ' + table + ' WHERE modulo_id=:m'), {'m':line}).scalar(), count)
                column = next(x for x in inspect(c).get_columns(table) if x['name']=='modulo_id')
                self.assertFalse(column['nullable'])
                self.assertIsNone(column['default'])
                self.assertTrue(any(f['constrained_columns']==['modulo_id'] for f in inspect(c).get_foreign_keys(table)))
            self.assertIn('ix_diagnosticos_paciente_modulo', [i['name'] for i in inspect(c).get_indexes('diagnosticos')])
            self.assertEqual(c.execute(text('SELECT count(*) FROM whatsapp_conversas')).scalar(),0)
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'8c01a0d1a004')
            self.assertEqual(list(c.execute(text('SELECT modulo_id FROM paciente_modulos WHERE paciente_id=6 AND ativo ORDER BY modulo_id')).scalars()), [1,2])
        self.assertEqual(self.snapshot('paciente_modulos')[:-1],before['paciente_modulos'])
        self.assertEqual(self.snapshot('registros_longitudinais'),before['registros_longitudinais'])

    def test_2_no_historical_rows(self):
        self.upgrade('head')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'8c01a0d1a004')

    def test_3_unknown_diagnosis_fails_and_retains_staging(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        with self.assertRaisesRegex(RuntimeError, 'diagnoses'):
            self.upgrade('head')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM diagnosticos WHERE modulo_id IS NULL')).scalar(),5)
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'8c01a0d1a000')

    def test_4_unknown_intervention_rolls_back_constraints(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        with self.engine.begin() as c:
            c.execute(text('UPDATE diagnosticos SET modulo_id=1'))
        with self.assertRaisesRegex(RuntimeError, 'interventions'):
            self.upgrade('head')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM intervencoes WHERE modulo_id IS NULL')).scalar(),16)
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'8c01a0d1a000')

    def test_5_changed_conversation_aborts_entire_remediation(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        with self.engine.begin() as c:
            c.execute(text("UPDATE whatsapp_conversas SET respostas_json=CAST(:payload AS json)"), {"payload": '{"synthetic":true}'})
        with self.assertRaisesRegex(Exception, 'Conversation changed'):
            self.remediate()
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM whatsapp_conversas')).scalar(),1)
            self.assertEqual(c.execute(text('SELECT count(*) FROM diagnosticos WHERE modulo_id IS NULL')).scalar(),5)
            self.assertEqual(c.execute(text('SELECT count(*) FROM paciente_modulos WHERE paciente_id=6 AND modulo_id=2')).scalar(),0)

    def test_explicit_cardio_context_is_not_overwritten(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        with self.engine.begin() as c:
            c.execute(text('UPDATE diagnosticos SET modulo_id=2'))
            c.execute(text('UPDATE intervencoes SET modulo_id=1'))
        self.upgrade('head')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM diagnosticos WHERE modulo_id=2')).scalar(),5)

    def test_invalid_explicit_module_fails_fk(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        with self.engine.begin() as c:
            c.execute(text('UPDATE diagnosticos SET modulo_id=999'))
        with self.assertRaises(IntegrityError):
            self.upgrade('8c01a0d1a001')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'8c01a0d1a000')

    def test_graph_single_linear_head(self):
        self.assertEqual(self.scripts.get_heads(), ['8c01a0d1a004'])
        chain = list(self.scripts.iterate_revisions('head','fb27d5139e1e'))
        self.assertEqual([r.revision for r in reversed(chain)], ['5a01c7e2d903','8c01a0d1a000','8c01a0d1a001','8c01a0d1a002','8c01a0d1a003','8c01a0d1a004'])

    def test_conversation_guard_checks_every_approved_condition(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        with self.engine.begin() as c:
            c.execute(text('INSERT INTO responsaveis VALUES (4)'))
        changes = ["id=2", "responsavel_id=4", "paciente_id=1",
                   "etapa_atual='CONFIRMAR_INICIO'", "data_referencia=DATE '2026-06-09'",
                   "respostas_json='null'"]
        for change in changes:
            with self.subTest(change=change):
                with self.engine.begin() as c:
                    c.execute(text("UPDATE whatsapp_conversas SET id=1,responsavel_id=3,paciente_id=NULL,etapa_atual='INICIO',data_referencia=NULL,respostas_json='{}'"))
                    c.execute(text('UPDATE whatsapp_conversas SET ' + change))
                with self.assertRaisesRegex(Exception, 'Conversation changed'):
                    self.remediate()
                with self.engine.connect() as c:
                    self.assertEqual(c.execute(text('SELECT count(*) FROM whatsapp_conversas')).scalar(),1)
                    self.assertEqual(c.execute(text('SELECT count(*) FROM diagnosticos WHERE modulo_id IS NULL')).scalar(),5)

    def test_reexecution_is_refused_without_partial_writes(self):
        self.seed()
        self.upgrade('8c01a0d1a000')
        self.remediate()
        before = self.snapshot('paciente_modulos')
        with self.assertRaisesRegex(Exception, 'Diagnosis inventory changed'):
            self.remediate()
        self.assertEqual(self.snapshot('paciente_modulos'), before)

    def test_unstaged_upgrade_rolls_back_ddl_and_revision(self):
        self.seed()
        with self.assertRaisesRegex(RuntimeError, 'diagnoses'):
            self.upgrade('head')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'fb27d5139e1e')
            self.assertNotIn('modulo_id', [x['name'] for x in inspect(c).get_columns('diagnosticos')])
            self.assertNotIn('modulo_id', [x['name'] for x in inspect(c).get_columns('intervencoes')])
