"""G1 domain and physical gates on an explicitly disposable PostgreSQL 18."""
import os
import unittest
from datetime import date
from types import SimpleNamespace
from uuid import uuid4
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic import command
from test_m0_baseline import config
from app.models.institucional import *
from app.schemas.institucional import normalize_cnpj
from app.services.institucional import InstitucionalService
from app.core.acl import assert_clinica_access
from fastapi import HTTPException

URL = os.getenv('G1_TEST_POSTGRES_URL')

class CnpjTests(unittest.TestCase):
    def test_valid_and_invalid(self):
        self.assertEqual(normalize_cnpj('11.222.333/0001-81'), '11222333000181')
        self.assertIsNone(normalize_cnpj(None))
        for value in ('11222333000182', '00000000000000', '', 'abc11222333000181', '123'):
            with self.assertRaises(ValueError): normalize_cnpj(value)

@unittest.skipUnless(URL, 'Requires disposable G1 PostgreSQL')
class InstitutionalPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.port not in (None, 5432, 55614) or url.database != 'm0_baseline':
            raise RuntimeError('Only the dedicated local G1 instance is allowed')
        cls.admin = create_engine(url, isolation_level='AUTOCOMMIT')
        cls.engines=[]
        for mode in ('empty','incremental'):
            name='g1_'+mode+'_'+uuid4().hex
            with cls.admin.connect() as conn: conn.execute(text('CREATE DATABASE '+name))
            engine=create_engine(url.set(database=name), connect_args={'options': '-c lock_timeout=5000 -c statement_timeout=15000'}); cls.engines.append((name,engine))
            with engine.begin() as conn:
                if mode=='incremental': command.upgrade(config(conn),'m0_baseline_v1')
                command.upgrade(config(conn),'head')
        cls.engine=cls.engines[0][1]

    @classmethod
    def tearDownClass(cls):
        for name,engine in cls.engines:
            engine.dispose()
            with cls.admin.connect() as conn: conn.execute(text('DROP DATABASE '+name))
        cls.admin.dispose()

    def setUp(self):
        self.conn=self.engine.connect(); self.tx=self.conn.begin(); self.db=Session(self.conn)
        self.s=InstitucionalService()
        self.p=self.db.execute(text("INSERT INTO pacientes(nome,ativo) VALUES ('Sintético',true) RETURNING id")).scalar()
        self.pr=self.db.execute(text("INSERT INTO profissionais(nome,ativo) VALUES ('Sintético',true) RETURNING id")).scalar()
        self.oc=self.db.execute(text("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Ocupação sintética') RETURNING id")).scalar()
        self.a=Instituicao(razao_social='A',tipo_instituicao='CLINICA')
        self.b=Instituicao(razao_social='B',tipo_instituicao='CLINICA')
        self.db.add_all([self.a,self.b]); self.db.flush()

    def tearDown(self):
        self.db.close(); self.tx.rollback(); self.conn.close()

    def institution(self,name,**extra):
        return self.s.create(self.db,Instituicao,dict(razao_social=name,tipo_instituicao='CLINICA',**extra))

    def link(self,model,**extra):
        return self.s.create(self.db,model,dict(data_inicio=date(2026,1,1),**extra))

    def rejected(self,fn):
        with self.assertRaises((IntegrityError,ValueError)):
            with self.db.begin_nested(): fn()

    def test_institution_hierarchy_roles_and_cnpj(self):
        c=self.institution('C',cnpj='11.222.333/0001-81',instituicao_pai_id=self.a.id)
        self.assertEqual(c.cnpj,'11222333000181')
        self.assertIsNone(self.a.cnpj)
        self.rejected(lambda:self.institution('Duplicada',cnpj=c.cnpj))
        self.rejected(lambda:self.institution('Inválida',cnpj='123'))
        self.rejected(lambda:self.s.set_parent(self.db,self.a.id,self.a.id))
        self.rejected(lambda:self.s.set_parent(self.db,self.a.id,c.id))
        for role in ('ASSISTENCIAL','CONTRATANTE'):
            self.s.create(self.db,InstituicaoPapel,dict(instituicao_id=self.a.id,papel=role))
        self.rejected(lambda:self.s.create(self.db,InstituicaoPapel,dict(instituicao_id=self.a.id,papel='ASSISTENCIAL')))
        self.assertEqual(self.db.query(InstituicaoPapel).count(),2)

    def test_patient_history_multiple_institutions_and_boundaries(self):
        args=dict(paciente_id=self.p,instituicao_id=self.a.id,tipo_vinculo='BENEFICIARIO')
        a=self.link(PacienteInstituicao,**args)
        self.link(PacienteInstituicao,paciente_id=self.p,instituicao_id=self.b.id,tipo_vinculo='ASSISTENCIAL')
        self.assertIsNone(a.identificador_externo)
        self.rejected(lambda:self.link(PacienteInstituicao,**args))
        self.rejected(lambda:self.link(PacienteInstituicao,data_fim=date(2025,1,1),**args))
        self.s.close(self.db,PacienteInstituicao,a.id,date(2026,2,1))
        self.rejected(lambda:self.s.create(self.db,PacienteInstituicao,dict(args,data_inicio=date(2026,2,1))))
        self.s.create(self.db,PacienteInstituicao,dict(args,data_inicio=date(2026,2,2)))
        self.assertEqual(self.s.effective(self.db,PacienteInstituicao,date(2026,1,1)).filter_by(paciente_id=self.p).count(),2)
        self.assertEqual(self.s.effective(self.db,PacienteInstituicao,date(2025,1,1)).filter_by(paciente_id=self.p).count(),0)
        self.assertTrue(self.db.execute(text('SELECT ativo FROM pacientes WHERE id=:id'),dict(id=self.p)).scalar())

    def test_professional_multiple_occupations_teams_and_history(self):
        args=dict(profissional_id=self.pr,instituicao_id=self.a.id,ocupacao_id=self.oc)
        a=self.link(ProfissionalInstituicao,**args)
        b=self.link(ProfissionalInstituicao,**dict(args,instituicao_id=self.b.id))
        oc=self.db.execute(text("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Outra') RETURNING id")).scalar()
        self.link(ProfissionalInstituicao,**dict(args,ocupacao_id=oc))
        self.rejected(lambda:self.link(ProfissionalInstituicao,**args))
        team=self.link(PacienteProfissional,paciente_id=self.p,profissional_instituicao_id=a.id)
        self.link(PacienteProfissional,paciente_id=self.p,profissional_instituicao_id=b.id)
        self.rejected(lambda:self.link(PacienteProfissional,paciente_id=self.p,profissional_instituicao_id=a.id))
        self.s.close(self.db,PacienteProfissional,team.id,date(2026,2,1))
        self.s.close(self.db,ProfissionalInstituicao,a.id,date(2026,2,1))
        self.s.create(self.db,ProfissionalInstituicao,dict(args,data_inicio=date(2026,2,2)))
        self.assertTrue(self.db.execute(text('SELECT ativo FROM profissionais WHERE id=:id'),dict(id=self.pr)).scalar())
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM sessoes_assistenciais')).scalar(),0)

    def test_new_links_never_grant_clinical_access(self):
        self.link(PacienteInstituicao,paciente_id=self.p,instituicao_id=self.a.id,tipo_vinculo='ASSISTENCIAL')
        a=self.link(ProfissionalInstituicao,profissional_id=self.pr,instituicao_id=self.a.id,ocupacao_id=self.oc)
        self.link(PacienteProfissional,paciente_id=self.p,profissional_instituicao_id=a.id)
        with self.assertRaises(HTTPException):
            assert_clinica_access(SimpleNamespace(perfil='PROFISSIONAL',clinica_id=1),2)

    def test_real_patient_boundary_stays_denied_with_new_team(self):
        from app.services.care_lines.access import authorized_patient
        from app.models import Clinica, Profissional, Paciente, ModuloClinico, ProfissionalModulo
        one=Clinica(nome='One'); two=Clinica(nome='Two')
        self.db.add_all([one,two]); self.db.flush()
        self.db.get(Profissional,self.pr).clinica_id=one.id
        self.db.get(Paciente,self.p).clinica_id=two.id
        self.db.add(ModuloClinico(id=2,nome='Cardio',slug='cardiometabolico',ativo=True))
        self.db.add(ProfissionalModulo(profissional_id=self.pr,modulo_id=2)); self.db.flush()
        user=SimpleNamespace(perfil='PROFISSIONAL',clinica_id=one.id,profissional_id=self.pr)
        def denied():
            with self.assertRaises(HTTPException) as error:
                authorized_patient(self.db,user,self.p,'CARDIO')
            self.assertEqual(error.exception.status_code,404)
        denied()
        a=self.link(ProfissionalInstituicao,profissional_id=self.pr,instituicao_id=self.a.id,ocupacao_id=self.oc)
        self.link(PacienteInstituicao,paciente_id=self.p,instituicao_id=self.a.id,tipo_vinculo='ASSISTENCIAL')
        self.link(PacienteProfissional,paciente_id=self.p,profissional_instituicao_id=a.id)
        denied()

    def test_multiple_people_and_administrative_validity(self):
        pr2=self.db.execute(text("INSERT INTO profissionais(nome,ativo) VALUES ('Outro',true) RETURNING id")).scalar()
        p2=self.db.execute(text("INSERT INTO pacientes(nome,ativo) VALUES ('Outro',true) RETURNING id")).scalar()
        a=self.link(ProfissionalInstituicao,profissional_id=self.pr,instituicao_id=self.a.id,ocupacao_id=self.oc)
        b=self.link(ProfissionalInstituicao,profissional_id=pr2,instituicao_id=self.a.id,ocupacao_id=self.oc)
        for patient, professional in ((self.p,a.id),(self.p,b.id),(p2,a.id)):
            self.link(PacienteProfissional,paciente_id=patient,profissional_instituicao_id=professional)
        self.assertEqual(self.s.effective(self.db,PacienteProfissional,date(2026,1,1)).count(),3)
        a.ativo=False
        self.db.flush()
        self.assertEqual(self.s.effective(self.db,ProfissionalInstituicao,date(2026,1,1)).count(),1)
        # No automatic propagation to the separately administered team history.
        self.assertEqual(self.db.query(PacienteProfissional).count(),3)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM vinculos')).scalar(),0)

    def test_concurrent_hierarchy_cannot_create_cycle(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        with Session(self.engine) as db, db.begin():
            a=self.s.create(db,Instituicao,dict(razao_social='Race A',tipo_instituicao='OUTRO'))
            b=self.s.create(db,Instituicao,dict(razao_social='Race B',tipo_instituicao='OUTRO'))
            identities=(a.id,b.id)
        barrier=Barrier(2)
        def move(pair):
            try:
                with Session(self.engine) as db, db.begin():
                    barrier.wait(timeout=5)
                    self.s.set_parent(db,*pair)
                return 'ok'
            except ValueError:
                return 'cycle'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(move,(identities,identities[::-1])))
        self.assertCountEqual(outcomes,['ok','cycle'])

    def test_concurrent_duplicate_exclusion(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        with Session(self.engine) as db, db.begin():
            institution=self.s.create(db,Instituicao,dict(razao_social='Race',tipo_instituicao='OUTRO')).id
            patient=db.execute(text("INSERT INTO pacientes(nome) VALUES ('Race') RETURNING id")).scalar()
        barrier=Barrier(2)
        def insert(_):
            try:
                with Session(self.engine) as db, db.begin():
                    barrier.wait(timeout=5)
                    self.s.create(db,PacienteInstituicao,dict(paciente_id=patient,instituicao_id=institution,
                        tipo_vinculo='OUTRO',data_inicio=date(2026,1,1)))
                return 'ok'
            except IntegrityError:
                return 'duplicate'
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes=list(pool.map(insert,range(2)))
        self.assertCountEqual(outcomes,['ok','duplicate'])

    def test_empty_and_incremental_catalogues_identical(self):
        def catalogue(engine):
            with engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g2a2_pessoas_v1')
                columns=c.execute(text("SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,pg_get_expr(d.adbin,d.adrelid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2")).all()
                constraints=c.execute(text("SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2")).all()
                indexes=c.execute(text("SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2")).all()
                sequences=c.execute(text("SELECT sequencename,data_type,start_value,min_value,max_value,increment_by,cycle FROM pg_sequences WHERE schemaname='public' ORDER BY 1")).all()
                return columns,constraints,indexes,sequences
        self.assertEqual(catalogue(self.engines[0][1]),catalogue(self.engines[1][1]))
        from app.database import Base
        inspector=inspect(self.engine)
        for model in (Instituicao,InstituicaoPapel,PacienteInstituicao,ProfissionalInstituicao,PacienteProfissional):
            table=model.__table__
            self.assertEqual({c['name'] for c in inspector.get_columns(table.name)},set(table.c.keys()))
            self.assertEqual(inspector.get_pk_constraint(table.name)['constrained_columns'],['id'])
            from sqlalchemy.dialects.postgresql import dialect
            for column in inspector.get_columns(table.name):
                expected=table.c[column['name']]
                self.assertEqual(str(column['type'].compile(dialect=dialect())),str(expected.type.compile(dialect=dialect())))
                self.assertEqual(column['nullable'],expected.nullable)
            actual={(tuple(f['constrained_columns']),f['referred_table'],tuple(f['referred_columns']),f['options'].get('ondelete')) for f in inspector.get_foreign_keys(table.name)}
            expected={(tuple(c.name for c in f.columns),f.elements[0].column.table.name,tuple(e.column.name for e in f.elements),f.ondelete) for f in table.foreign_key_constraints}
            self.assertEqual(actual,expected)
            self.assertEqual({tuple(u['column_names']) for u in inspector.get_unique_constraints(table.name)},
                {tuple(c.name for c in u.columns) for u in table.constraints if isinstance(u,UniqueConstraint)})
            self.assertEqual({c['name'] for c in inspector.get_check_constraints(table.name)},
                {c.name for c in table.constraints if isinstance(c,CheckConstraint)})
