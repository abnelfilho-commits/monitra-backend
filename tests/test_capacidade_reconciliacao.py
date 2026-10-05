"""Frozen capacity reconciliation on isolated PostgreSQL 18 databases."""
import importlib.util
import os
import unittest
from pathlib import Path
from uuid import uuid4
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.engine import make_url
from alembic import command
from alembic.script import ScriptDirectory
from test_m0_baseline import config

HEAD='capacidade_reconciliacao_v1'
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('capacity_revision',ROOT/'alembic_canonical/versions'/f'{HEAD}.py')
migration=importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

# Independent legacy fixture: not built by invoking the new revision/helper.
LEGACY_DDL = '''
CREATE TABLE capacidades_profissionais (
 id SERIAL PRIMARY KEY,
 profissional_instituicao_id integer NOT NULL REFERENCES profissional_instituicoes(id) ON DELETE RESTRICT,
 minutos_semanais integer NOT NULL CHECK (minutos_semanais > 0),
 data_inicio date NOT NULL, data_fim date,
 ativo boolean NOT NULL DEFAULT true,
 criado_em timestamptz NOT NULL DEFAULT now(), atualizado_em timestamptz NOT NULL DEFAULT now(),
 CHECK (data_fim IS NULL OR data_fim >= data_inicio),
 CONSTRAINT ex_capacidade_profissional_vigencia EXCLUDE USING gist
 (profissional_instituicao_id WITH =, daterange(data_inicio,data_fim,'[]') WITH &&) WHERE (ativo));
CREATE INDEX ix_capacidades_profissionais_profissional_instituicao_id ON capacidades_profissionais (profissional_instituicao_id);
ALTER TABLE institucional_operacoes ADD COLUMN capacidade_profissional_id integer;
ALTER TABLE institucional_operacoes ADD CONSTRAINT fk_institucional_operacoes_capacidade_profissional
 FOREIGN KEY (capacidade_profissional_id) REFERENCES capacidades_profissionais(id) ON DELETE RESTRICT;
ALTER TABLE institucional_operacoes DROP CONSTRAINT ck_institucional_operacao_alvo;
ALTER TABLE institucional_operacoes ADD CONSTRAINT ck_institucional_operacao_alvo CHECK (
 (tipo_alvo='PACIENTE_INSTITUICAO' AND paciente_instituicao_id IS NOT NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NULL AND capacidade_profissional_id IS NULL) OR
 (tipo_alvo='PROFISSIONAL_INSTITUICAO' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NOT NULL AND paciente_profissional_id IS NULL AND capacidade_profissional_id IS NULL) OR
 (tipo_alvo='PACIENTE_PROFISSIONAL' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NOT NULL AND capacidade_profissional_id IS NULL) OR
 (tipo_alvo='CAPACIDADE_PROFISSIONAL' AND paciente_instituicao_id IS NULL AND profissional_instituicao_id IS NULL AND paciente_profissional_id IS NULL AND capacidade_profissional_id IS NOT NULL));
ALTER TABLE institucional_operacoes DROP CONSTRAINT ck_institucional_operacao_resultado;
ALTER TABLE institucional_operacoes ADD CONSTRAINT ck_institucional_operacao_resultado CHECK (
 (operacao='CREATE_LINK' AND resultado='CREATED') OR (operacao='CLOSE_LINK' AND resultado='CLOSED') OR
 (operacao='INVALIDATE_LINK' AND resultado='INVALIDATED') OR (operacao='CREATE_CAPACITY' AND resultado='CREATED') OR
 (operacao='CLOSE_CAPACITY' AND resultado='CLOSED') OR (operacao='INVALIDATE_CAPACITY' AND resultado='INVALIDATED'));
'''


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL 18 required')
class CapacityReconciliationTests(unittest.TestCase):
    def setUp(self):
        url=make_url(os.environ['M0_TEST_POSTGRES_URL'])
        if url.host not in ('127.0.0.1','localhost') or url.database!='m0_baseline':
            raise RuntimeError('Local disposable database required')
        self.admin=create_engine(url,isolation_level='AUTOCOMMIT')
        self.name='capacity_test_'+uuid4().hex
        with self.admin.connect() as c:
            self.assertEqual(int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000,18)
            c.exec_driver_sql('CREATE DATABASE '+self.name)
        self.engine=create_engine(url.set(database=self.name))

    def tearDown(self):
        self.engine.dispose()
        with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+self.name)
        self.admin.dispose()

    def upgrade(self,target):
        with self.engine.begin() as c:command.upgrade(config(c),target)

    def assert_contract(self,c):
        migration.validate_capacity(c)
        self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),HEAD)
        self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=\'capacidades_profissionais\'').scalar(),8)
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(),[HEAD])

    def test_empty_bootstrap_and_idempotence(self):
        self.upgrade('head')
        with self.engine.begin() as c:
            self.assert_contract(c)
            statements=[]
            def record(conn,cursor,statement,*args):statements.append(statement)
            event.listen(c,'before_cursor_execute',record)
            command.upgrade(config(c),'head')
            command.current(config(c))
            command.heads(config(c))
            event.remove(c,'before_cursor_execute',record)
            self.assertFalse(any(s.lstrip().upper().startswith(('CREATE ','ALTER ','DROP ','INSERT ','UPDATE ','DELETE ')) for s in statements))

    def test_canonical_w2b(self):
        self.upgrade('w2b_checkin_v1')
        with self.engine.connect() as c:self.assertFalse(migration.exists(c,migration.CAP))
        self.upgrade('head')
        with self.engine.connect() as c:self.assert_contract(c)

    def legacy(self,revision='w2b_checkin_v1'):
        self.upgrade(revision)
        with self.engine.begin() as c:c.exec_driver_sql(LEGACY_DDL)

    def test_i1_f1_to_head_preserves_data_oids_and_history(self):
        self.legacy('f1_economia_v1')
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO instituicoes(id,razao_social,tipo_instituicao) VALUES (901,'Synthetic','OUTRO')")
            c.exec_driver_sql("INSERT INTO ocupacoes_profissionais(id,nome) VALUES (901,'Synthetic')")
            c.exec_driver_sql("INSERT INTO profissionais(id,nome) VALUES (901,'Synthetic')")
            c.exec_driver_sql("INSERT INTO usuarios(id,nome,email,senha_hash,perfil) VALUES (901,'Synthetic','synthetic@example.test','synthetic','ADMIN')")
            c.exec_driver_sql("INSERT INTO profissional_instituicoes(id,profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (901,901,901,901,'2026-01-01')")
            c.exec_driver_sql("INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio) VALUES (901,120,'2026-01-01')")
            c.exec_driver_sql("INSERT INTO institucional_operacoes(ator_usuario_id,instituicao_id,operacao,tipo_alvo,motivo,resultado,estado_final,capacidade_profissional_id) VALUES (901,901,'CREATE_CAPACITY','CAPACIDADE_PROFISSIONAL','Synthetic','CREATED','{}',1)")
            before=self.snapshot(c)
        statements=[]
        def record(conn,cursor,statement,*args):statements.append(statement)
        event.listen(self.engine,'before_cursor_execute',record)
        self.upgrade('head')
        event.remove(self.engine,'before_cursor_execute',record)
        with self.engine.connect() as c:
            self.assert_contract(c)
            self.assertEqual(before,self.snapshot(c))
        with self.assertRaisesRegex(RuntimeError,'DOWNGRADE_BLOCKED'):
            with self.engine.begin() as c:command.downgrade(config(c),'w2b_checkin_v1')
        with self.engine.connect() as c:self.assertEqual(before,self.snapshot(c))
        self.assertFalse(any(s.lstrip().upper().startswith(('CREATE ','ALTER ','DROP ')) and
            ('capacidades_profissionais' in s or 'institucional_operacoes' in s) for s in statements))

    def test_physical_constraints_enforce_frozen_semantics(self):
        self.legacy('f1_economia_v1')
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO instituicoes(id,razao_social,tipo_instituicao) VALUES (901,'Synthetic','OUTRO')")
            c.exec_driver_sql("INSERT INTO ocupacoes_profissionais(id,nome) VALUES (901,'Synthetic')")
            c.exec_driver_sql("INSERT INTO profissionais(id,nome) VALUES (901,'Synthetic')")
            c.exec_driver_sql("INSERT INTO profissional_instituicoes(id,profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (901,901,901,901,'2026-01-01')")
        self.upgrade('head')
        with self.engine.begin() as c:
            c.exec_driver_sql("INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio,data_fim) VALUES (901,120,'2026-01-01','2026-01-31')")
            for sql in [
                "INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio) VALUES (901,0,'2027-01-01')",
                "INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio,data_fim) VALUES (901,120,'2027-01-01','2026-01-01')",
                "INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio) VALUES (901,120,'2026-01-31')",
                "INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio) VALUES (9999,120,'2027-01-01')",
                "DELETE FROM profissional_instituicoes WHERE id=901"]:
                with self.assertRaises(IntegrityError):
                    with c.begin_nested():c.exec_driver_sql(sql)
            c.exec_driver_sql("INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio) VALUES (901,120,'2026-02-01')")
            c.exec_driver_sql("INSERT INTO capacidades_profissionais(profissional_instituicao_id,minutos_semanais,data_inicio,ativo) VALUES (901,120,'2026-01-01',false)")

    def snapshot(self,c):
        return (c.exec_driver_sql('SELECT * FROM capacidades_profissionais ORDER BY id').all(),
            c.exec_driver_sql('SELECT * FROM institucional_operacoes ORDER BY id').all(),
            c.exec_driver_sql("SELECT 'capacidades_profissionais'::regclass::oid,'capacidades_profissionais_id_seq'::regclass::oid").one(),
            c.exec_driver_sql('SELECT last_value,is_called FROM capacidades_profissionais_id_seq').one())

    def test_reject_partial_variants_atomically(self):
        self.legacy()
        mutations=[
            'ALTER TABLE capacidades_profissionais DROP CONSTRAINT ex_capacidade_profissional_vigencia',
            'ALTER TABLE capacidades_profissionais ALTER COLUMN minutos_semanais TYPE bigint',
            'ALTER TABLE institucional_operacoes DROP CONSTRAINT fk_institucional_operacoes_capacidade_profissional',
            "ALTER TABLE institucional_operacoes DROP CONSTRAINT ck_institucional_operacao_resultado; ALTER TABLE institucional_operacoes ADD CONSTRAINT ck_institucional_operacao_resultado CHECK (operacao IN ('CREATE_LINK','CLOSE_LINK','INVALIDATE_LINK'))",
            'ALTER TABLE capacidades_profissionais ADD CONSTRAINT unexpected CHECK (minutos_semanais<1000)',
            'ALTER SEQUENCE capacidades_profissionais_id_seq INCREMENT BY 2',
            'ALTER TABLE capacidades_profissionais ALTER COLUMN ativo DROP NOT NULL',
            'DROP INDEX ix_capacidades_profissionais_profissional_instituicao_id',
            'ALTER TABLE capacidades_profissionais ENABLE ROW LEVEL SECURITY',
            'CREATE VIEW capacity_extra_view AS SELECT id FROM capacidades_profissionais',
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.engine.connect() as c:
                    tx=c.begin()
                    c.exec_driver_sql(mutation)
                    with self.assertRaisesRegex(RuntimeError,'CAPACITY_RECONCILIATION_STOP'):
                        command.upgrade(config(c),'head')
                    tx.rollback()
                with self.engine.connect() as c:
                    self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'w2b_checkin_v1')
                    migration.validate_capacity(c)

    def test_absent_table_with_orphan_fragment_rejected(self):
        self.upgrade('w2b_checkin_v1')
        with self.engine.begin() as c:c.exec_driver_sql('ALTER TABLE institucional_operacoes ADD COLUMN capacidade_profissional_id integer')
        with self.assertRaisesRegex(RuntimeError,'CAPACITY_RECONCILIATION_STOP'):
            self.upgrade('head')
        with self.engine.connect() as c:self.assertFalse(migration.exists(c,migration.CAP))

    def test_downgrade_blocked_even_empty(self):
        self.upgrade('head')
        with self.assertRaisesRegex(RuntimeError,'DOWNGRADE_BLOCKED'):
            with self.engine.begin() as c:command.downgrade(config(c),'w2b_checkin_v1')
        with self.engine.connect() as c:self.assert_contract(c)
