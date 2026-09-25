"""Canonical bootstrap/catalogue and legacy compatibility on disposable PG18."""
import json
import os
from datetime import date
from pathlib import Path
import unittest
from uuid import uuid4

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, configure_mappers
from sqlalchemy.dialects.postgresql import dialect

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "alembic_canonical/baseline_v1.json").read_text())
URL = os.environ.get("M0_TEST_POSTGRES_URL")


def config(connection=None):
    cfg = Config(str(ROOT / "alembic-canonical.ini"))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


class ModelContractTests(unittest.TestCase):
    def test_all_mapped_columns_match_physical_contract(self):
        import app.models  # noqa: F401
        from app.database import Base
        configure_mappers()
        for name, table in Base.metadata.tables.items():
            if name in {"capacidade_instalada", "institucional_operacoes", "identidade_operacoes", "pessoas", "instituicoes", "instituicao_papeis", "paciente_instituicoes", "profissional_instituicoes", "paciente_profissionais"}:
                continue  # Explicit transitional model; never bootstrap it.
            physical = {c["column_name"]: c for c in CONTRACT["tables"][name]["columns"]}
            for col in table.c:
                if name in {"pacientes", "profissionais", "usuarios", "responsaveis"} and col.name == "pessoa_id":
                    continue  # G2.A.2 addition, verified on the current canonical head.
                with self.subTest(table=name, column=col.name):
                    self.assertIn(col.name, physical)
                    actual_type = str(col.type.compile(dialect=dialect())).lower().replace("varchar", "character varying").replace(", ", ",")
                    self.assertEqual(actual_type, physical[col.name]["formatted_type"])
                    self.assertEqual(col.nullable, physical[col.name]["nullable"])

    def test_explicit_approved_legacy_boundaries(self):
        from app.models.registro import RegistroDiario
        from app.models.paciente import Paciente
        from app.models.usuario import Usuario
        from app.models.sessao_assistencial import SessaoAssistencial
        self.assertFalse(Paciente.__table__.c.profissional_id.foreign_keys)
        fk = next(iter(Usuario.__table__.c.profissional_id.foreign_keys))
        self.assertEqual(fk.ondelete, "SET NULL")
        self.assertFalse(SessaoAssistencial.__table__.c.agenda_cuidado_id.nullable)
        for field in ("tempo_tela", "seletividade_alimentar", "aceitou_alimento_novo"):
            self.assertNotIn(field, RegistroDiario.__table__.c)
        self.assertIn("alimentacao", RegistroDiario.__table__.c)
        self.assertNotIn("capacidade_instalada", CONTRACT["tables"])
        self.assertNotIn("planejamento_atividades", CONTRACT["tables"])

    def test_separate_single_heads(self):
        self.assertEqual(ScriptDirectory.from_config(config()).get_heads(), ["g2b1_institucional_v1"])
        historical = Config(str(ROOT / "alembic.ini"))
        historical.set_main_option("script_location", str(ROOT / "alembic"))
        self.assertEqual(ScriptDirectory.from_config(historical).get_heads(), ["8c01a0d1a004"])


@unittest.skipUnless(URL, "Requires dedicated disposable M0 PostgreSQL")
class BaselinePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host not in ("127.0.0.1", "localhost") or url.database != "m0_baseline":
            raise RuntimeError("Only the local disposable m0_baseline database is allowed")
        cls.admin = create_engine(url, isolation_level="AUTOCOMMIT")
        cls.database = "m0_validation_" + uuid4().hex
        with cls.admin.connect() as conn:
            if int(conn.execute(text("SHOW server_version_num")).scalar()) // 10000 != 18:
                raise RuntimeError("PG18 required")
            conn.execute(text('CREATE DATABASE "{}"'.format(cls.database)))
        cls.engine = create_engine(url.set(database=cls.database))
        with cls.engine.begin() as conn:
            command.upgrade(config(conn), "m0_baseline_v1")

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as conn:
            conn.execute(text('DROP DATABASE "{}"'.format(cls.database)))
        cls.admin.dispose()

    def test_bootstrap_catalogue_columns_defaults_and_constraints(self):
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text("SELECT version_num FROM alembic_version")).scalar(), "m0_baseline_v1")
            inspector = inspect(conn)
            self.assertEqual(set(inspector.get_table_names()) - {"alembic_version"}, set(CONTRACT["tables"]))
            self.assertEqual(set(inspector.get_view_names()), {v["name"] for v in CONTRACT["views"]})
            for name, table in CONTRACT["tables"].items():
                with self.subTest(table=name):
                    actual = conn.execute(text("""
                        SELECT a.attname, format_type(a.atttypid,a.atttypmod), NOT a.attnotnull,
                               pg_get_expr(d.adbin,d.adrelid)
                        FROM pg_attribute a
                        LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum
                        WHERE a.attrelid=to_regclass(:name) AND a.attnum>0 AND NOT a.attisdropped
                        ORDER BY a.attnum
                    """), {"name": name}).all()
                    self.assertEqual([tuple(r) for r in actual], [(c["column_name"], c["formatted_type"], c["nullable"], c["default_expression"]) for c in table["columns"]])
                    constraints = conn.execute(text("""
                        SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                        WHERE conrelid=to_regclass(:name) AND contype IN ('p','u','f','c')
                    """), {"name": name}).all()
                    self.assertEqual(set(map(tuple, constraints)), {(c["constraint_name"], c["definition"]) for c in table["constraints"] + table["foreign_keys"]})
                    indexes = dict(conn.execute(text("SELECT indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename=:name"), {"name": name}).all())
                    for index in table["indexes"]:
                        self.assertEqual(indexes[index["index_name"]], index["definition"])
                    self.assertEqual(len(indexes), len(table["indexes"]) + len(table["constraints"]))
            for view in CONTRACT["views"]:
                actual = conn.execute(text("SELECT pg_get_viewdef(to_regclass(:name),true)"), {"name": view["name"]}).scalar()
                self.assertEqual(" ".join(actual.split()), " ".join(view["definition"].split()))

    def test_sequences_ownership_and_empty_domain(self):
        with self.engine.connect() as conn:
            self.assertEqual(len(inspect(conn).get_sequence_names()), 29)
            for sequence in CONTRACT["sequences"]:
                actual = conn.execute(text("SELECT pg_get_serial_sequence(:table,:col)"), {"table": sequence["owner_table"], "col": sequence["owner_column"]}).scalar()
                self.assertEqual(actual, "public." + sequence["sequence_name"])
                actual = conn.execute(text("SELECT start_value,increment_by,min_value,max_value,cache_size,cycle FROM pg_sequences WHERE schemaname='public' AND sequencename=:name"), {"name": sequence["sequence_name"]}).one()
                self.assertEqual(tuple(actual), tuple(sequence[k] for k in ("start_value", "increment_by", "min_value", "max_value", "cache_size", "cycle")))
            for name in CONTRACT["tables"]:
                self.assertEqual(conn.execute(text('SELECT count(*) FROM "{}"'.format(name))).scalar(), 0)

    def test_orm_constraints_indexes_and_defaults_match_catalogue(self):
        from app.database import Base
        from sqlalchemy import UniqueConstraint
        with self.engine.connect() as conn:
            inspector = inspect(conn)
            for name, table in Base.metadata.tables.items():
                if name in {"capacidade_instalada", "institucional_operacoes", "identidade_operacoes", "pessoas", "instituicoes", "instituicao_papeis", "paciente_instituicoes", "profissional_instituicoes", "paciente_profissionais"}:
                    continue
                with self.subTest(table=name):
                    actual = {(tuple(f["constrained_columns"]), f["referred_table"], tuple(f["referred_columns"]), f["options"].get("ondelete", "NO ACTION")) for f in inspector.get_foreign_keys(name)}
                    expected = {(tuple(c.name for c in f.columns), f.elements[0].column.table.name, tuple(e.column.name for e in f.elements), f.ondelete or "NO ACTION") for f in table.foreign_key_constraints if f.elements[0].column.table.name != "pessoas"}
                    self.assertEqual(actual, expected)
                    actual_unique = {tuple(u["column_names"]) for u in inspector.get_unique_constraints(name)}
                    expected_unique = {tuple(c.name for c in u.columns) for u in table.constraints if isinstance(u, UniqueConstraint) and tuple(c.name for c in u.columns) != ("pessoa_id",)}
                    self.assertEqual(actual_unique, expected_unique)
                    actual_indexes = {(i["name"], tuple(i["column_names"]), i["unique"]) for i in inspector.get_indexes(name) if not i.get("duplicates_constraint")}
                    expected_indexes = {(i.name, tuple(c.name for c in i.columns), i.unique) for i in table.indexes if tuple(c.name for c in i.columns) != ("pessoa_id",)}
                    self.assertEqual(actual_indexes, expected_indexes)
                    physical = {c["column_name"]: c for c in CONTRACT["tables"][name]["columns"]}
                    for column in table.c:
                        if column.name == "pessoa_id" and name in {"pacientes", "profissionais", "usuarios", "responsaveis"}:
                            continue  # Not part of frozen M0.
                        expected_default = physical[column.name]["default_expression"]
                        if expected_default and expected_default.startswith("nextval("):
                            continue  # SERIAL/autoincrement, verified separately.
                        actual_default = str(column.server_default.arg) if column.server_default else None
                        if expected_default:
                            expected_default = expected_default.replace("::character varying", "")
                            if isinstance(getattr(column.server_default, "arg", None), str):
                                expected_default = expected_default.strip("'")
                        self.assertEqual(actual_default, expected_default, (name, column.name))

    def test_second_upgrade_preserves_schema(self):
        with self.engine.begin() as conn:
            command.upgrade(config(conn), "m0_baseline_v1")
        self.test_bootstrap_catalogue_columns_defaults_and_constraints()

    def test_refuse_existing_nonempty_database(self):
        # Simulate an unversioned existing schema inside a rolled-back transaction.
        with self.engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.execute(text("DELETE FROM alembic_version"))
                with self.assertRaisesRegex(RuntimeError, "not empty"):
                    command.upgrade(config(conn), "m0_baseline_v1")
            finally:
                tx.rollback()

    def test_legacy_alimentacao_router_and_relationship(self):
        from app.models.paciente import Paciente
        from app.models.profissional import Profissional
        from app.models.registro import RegistroDiario
        from app.routers.registros import criar_registro
        from app.schemas.registro import RegistroDiarioCreate
        with self.engine.connect() as conn:
            tx = conn.begin()
            # Current ORM includes nullable G2.A.2 fields; keep the M0 catalogue
            # frozen and roll this test-only schema upgrade back with the rows.
            command.upgrade(config(conn), "g2a2_pessoas_v1")
            session = Session(conn, join_transaction_mode="create_savepoint")
            try:
                professional = Profissional(nome="M0 synthetic")
                patient = Paciente(nome="M0 synthetic", profissional=professional)
                session.add(patient)
                session.flush()
                self.assertEqual(patient.profissional_id, professional.id)
                record = criar_registro(RegistroDiarioCreate(paciente_id=patient.id, data=date(2026, 1, 1), alimentacao="M0 synthetic"), session)
                session.expire_all()
                self.assertEqual(session.get(RegistroDiario, record.id).alimentacao, "M0 synthetic")
                self.assertIsNone(record.origem)
                self.assertIn(patient, professional.pacientes)
            finally:
                session.close()
                tx.rollback()

    def test_neuro_fields_remain_canonical_answers(self):
        from app.services.neuro_engine import obter_registros_neuro_paciente, calcular_pontuacao_risco_registro
        with self.engine.connect() as conn:
            tx = conn.begin()
            try:
                conn.execute(text("INSERT INTO pacientes(id,nome) VALUES(901,'M0 synthetic')"))
                conn.execute(text("INSERT INTO modulos_clinicos(id,nome,slug) VALUES(1,'Neuro','neurodesenvolvimento')"))
                conn.execute(text("INSERT INTO formularios_modulo(id,modulo_id,nome,tipo) VALUES(901,1,'M0 synthetic','REGISTRO_DIARIO')"))
                conn.execute(text("INSERT INTO registros_longitudinais(id,paciente_id,modulo_id,formulario_id,origem,data_registro) VALUES(901,901,1,901,'PROFISSIONAL','2026-01-01')"))
                for ident, field, typ, value in [(901,"tempo_tela","texto","MAIS_4H"),(902,"seletividade_alimentar","texto","ALTA"),(903,"aceitou_alimento_novo","booleano",False)]:
                    conn.execute(text("INSERT INTO campos_formulario(id,formulario_id,nome_campo,label,tipo_campo) VALUES(:id,901,:field,:field,:typ)"), {"id":ident,"field":field,"typ":typ})
                    conn.execute(text("INSERT INTO respostas_registro(registro_id,campo_id,valor_{}) VALUES(901,:id,:value)".format(typ)), {"id":ident,"value":value})
                record = obter_registros_neuro_paciente(conn, 901)[0]
                self.assertEqual(record.tempo_tela, "MAIS_4H")
                self.assertEqual(record.seletividade_alimentar, "ALTA")
                self.assertFalse(record.aceitou_alimento_novo)
                self.assertGreater(calcular_pontuacao_risco_registro(record), 0)
            finally:
                tx.rollback()
