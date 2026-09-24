"""Real PostgreSQL tests, opt-in only on the disposable Wave 5 database."""
from fixtures.cardio_intervention_schema import create_cardio_intervention_table
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from uuid import uuid4

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from alembic.config import Config
from app.models import Pessoa, Clinica, OcupacaoProfissional, Profissional, Usuario, Paciente, Intervencao, ProfissionalModulo
from app.models.modular import ModuloClinico, PacienteModulo
from app.services.interventions import InterventionService, InterventionSubmission
from app.services.interventions.models import ActorRef, SourceType
from test_interventions import DAY

URL = os.getenv('WAVE5_TEST_POSTGRES_URL')
ALLOWED = 'postgresql+psycopg2://wave5@127.0.0.1/wave5_test'
ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(URL, 'Disposable Wave 5 PostgreSQL not configured')
class MigrationTests(unittest.TestCase):
    def setUp(self):
        if URL != ALLOWED:
            raise RuntimeError('Only the disposable Wave 5 test database is allowed.')
        self.schema = 'wave5_' + uuid4().hex
        self.bootstrap = create_engine(URL)
        with self.bootstrap.begin() as conn:
            conn.execute(text('CREATE SCHEMA ' + self.schema))
        self.engine = create_engine(URL, connect_args={'options': '-csearch_path=' + self.schema})
        spec=importlib.util.spec_from_file_location('wave5_migration',ROOT/'alembic/versions/5a01c7e2d903_add_intervention_module.py')
        self.migration=importlib.util.module_from_spec(spec); spec.loader.exec_module(self.migration)

    def tearDown(self):
        self.engine.dispose()
        with self.bootstrap.begin() as conn:
            conn.execute(text('DROP SCHEMA ' + self.schema + ' CASCADE'))
        self.bootstrap.dispose()

    def test_upgrade_downgrade_preserves_legacy_rows_and_fk(self):
        with self.engine.begin() as conn:
            conn.execute(text('CREATE TABLE modulos_clinicos (id INTEGER PRIMARY KEY)'))
            conn.execute(text('INSERT INTO modulos_clinicos VALUES (1)'))
            conn.execute(text('CREATE TABLE intervencoes (id INTEGER PRIMARY KEY, descricao TEXT)'))
            conn.execute(text("INSERT INTO intervencoes VALUES (10, 'synthetic')"))
            with Operations.context(MigrationContext.configure(conn)):
                self.migration.upgrade()
            column=next(c for c in inspect(conn).get_columns('intervencoes') if c['name']=='modulo_id')
            self.assertTrue(column['nullable'])
            self.assertIsNone(column['default'])
            fk=inspect(conn).get_foreign_keys('intervencoes')[0]
            self.assertEqual(fk['constrained_columns'],['modulo_id'])
            self.assertEqual(fk['referred_table'],'modulos_clinicos')
            self.assertNotIn('ondelete',fk['options'])
            self.assertEqual(tuple(conn.execute(text('SELECT * FROM intervencoes')).one()),(10,'synthetic',None))
            from sqlalchemy.exc import IntegrityError
            with self.assertRaises(IntegrityError):
                with conn.begin_nested():
                    conn.execute(text('UPDATE intervencoes SET modulo_id=999'))
            conn.execute(text('UPDATE intervencoes SET modulo_id=1'))
            with Operations.context(MigrationContext.configure(conn)):
                self.migration.downgrade()
            self.assertEqual(tuple(conn.execute(text('SELECT * FROM intervencoes')).one()),(10,'synthetic'))
            self.assertNotIn('modulo_id',[c['name'] for c in inspect(conn).get_columns('intervencoes')])

    def test_revision_is_single_successor_of_approved_head(self):
        config=Config(str(ROOT/'alembic.ini'))
        config.set_main_option('script_location',str(ROOT/'alembic'))
        scripts=ScriptDirectory.from_config(config)
        self.assertEqual(scripts.get_heads(),['8c01a0d1a004'])
        self.assertEqual(scripts.get_revision('8c01a0d1a004').down_revision,'8c01a0d1a003')
        self.assertEqual(scripts.get_revision('5a01c7e2d903').down_revision,'fb27d5139e1e')

    def test_postgres_adapters_defaults_and_namespaces(self):
        for model in (Pessoa,Clinica,OcupacaoProfissional,Profissional,Usuario,Paciente,ModuloClinico,PacienteModulo,Intervencao,ProfissionalModulo):
            model.__table__.create(self.engine)
        with self.engine.begin() as conn:
            create_cardio_intervention_table(conn)
        inspector = inspect(self.engine)
        columns = {c['name']: c for c in inspector.get_columns('intervencoes_cardiometabolicas')}
        self.assertEqual(set(columns), {'id','paciente_id','tipo','descricao','prioridade','created_at','modulo_id'})
        self.assertEqual({n for n,c in columns.items() if not c['nullable']}, {'id','paciente_id','tipo','modulo_id'})
        self.assertTrue(columns['created_at']['type'].timezone)
        self.assertEqual(columns['created_at']['default'], 'now()')
        self.assertIn('nextval', columns['id']['default'])
        for name in ('tipo','prioridade'):
            self.assertIsNone(columns[name]['type'].length)
            self.assertIsNone(columns[name]['default'])
        foreign_keys = {fk['constrained_columns'][0]: fk for fk in inspector.get_foreign_keys('intervencoes_cardiometabolicas')}
        self.assertEqual(foreign_keys['paciente_id']['options']['ondelete'], 'CASCADE')
        self.assertEqual(foreign_keys['modulo_id']['referred_table'], 'modulos_clinicos')
        self.assertEqual(inspector.get_pk_constraint('intervencoes_cardiometabolicas')['constrained_columns'], ['id'])
        self.assertEqual([i['column_names'] for i in inspector.get_indexes('intervencoes_cardiometabolicas')], [['paciente_id']])
        with Session(self.engine) as db:
            db.add(Clinica(id=1,nome='Synthetic')); db.flush()
            db.add(Profissional(id=700,nome='Synthetic',clinica_id=1,ativo=True)); db.flush()
            db.add(Usuario(id=50,nome='Synthetic',email='test@example.invalid',senha_hash='unused',clinica_id=1,profissional_id=700)); db.flush()
            db.add(Paciente(id=10,nome='Synthetic',clinica_id=1)); db.flush()
            for mid,slug in ((1,'neurodesenvolvimento'),(2,'cardiometabolico')):
                db.add(ModuloClinico(id=mid,nome=slug,slug=slug,ativo=True)); db.flush()
                db.add(PacienteModulo(paciente_id=10,modulo_id=mid,ativo=True)); db.flush()
                db.add(ProfissionalModulo(profissional_id=700,modulo_id=mid)); db.flush()
            db.commit()
            service=InterventionService()
            user=SimpleNamespace(id=50,perfil='PROFISSIONAL',clinica_id=1,profissional_id=700)
            generic=service.create(db,InterventionSubmission(10,'NEURO',ActorRef('PROFESSIONAL',50),'authored','Synthetic',DAY),user=user)
            cardio=service.create(db,InterventionSubmission(10,'CARDIO',ActorRef('PROFESSIONAL',50),'authored','Synthetic',payload={'priority':'alta'}),user=user)
            self.assertEqual(service.get(db,SourceType.GENERIC_INTERVENTION,generic.source_id,user=user).module_id,1)
            self.assertEqual(generic.actor,{'namespace':'usuarios','id':50})
            self.assertIsNone(cardio.actor)
            self.assertIsNotNone(generic.created_at.tzinfo)
            self.assertIsNotNone(cardio.created_at.tzinfo)
            self.assertIsNone(cardio.reference_datetime)
            self.assertEqual(cardio.metadata,{'priority':'alta'})

            self.assertEqual(service.get(db,SourceType.CARDIO_INTERVENTION,cardio.source_id,user=user).actor, None)
            listed = service.list_for_patient(db,10,user=user,requested_care_line='CARDIO')
            self.assertEqual([r.source_id for r in listed], [cardio.source_id])
            self.assertIsNone(listed[0].actor)
