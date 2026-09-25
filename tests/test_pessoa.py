"""Canonical identity contract: PG18 is the physical gate, never HML/PROD."""
import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from uuid import uuid4

from alembic import command
from alembic.script import ScriptDirectory
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import dialect
from fastapi import HTTPException

from test_m0_baseline import config
from app.models import Pessoa, Paciente, Profissional, Usuario, Responsavel
from app.schemas.pessoa import PessoaCreate, PessoaOut, normalize_cpf
from app.services.pessoa import PessoaService
from app.services.care_lines.access import authorized_patient

URL = os.getenv('G2A2_TEST_POSTGRES_URL')
DOMAINS = ('pacientes', 'profissionais', 'usuarios', 'responsaveis')
VALID_CPF = '52998224725'  # Algorithm fixture only; no claim of real ownership.


class PessoaContractTests(unittest.TestCase):
    def test_optional_mask_and_digits(self):
        for value in (None, '', '   '):
            self.assertIsNone(normalize_cpf(value))
        self.assertEqual(normalize_cpf(' 529.982.247-25 '), VALID_CPF)
        self.assertEqual(normalize_cpf(VALID_CPF), VALID_CPF)

    def test_invalid_cpf_rejected(self):
        for value in ('52998224724', '52998224715', '00000000000', '11111111111',
                      '123', 'x52998224725', '529-982-24725', '５２９９８２２４７２５', 52998224725):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_cpf(value)

    def test_names_optional_contacts_and_no_gender_conversion(self):
        p = PessoaCreate(cpf=VALID_CPF, nome_completo='  Nome Sintético  ', nome_social=' ', sexo=None,
                         email='  Synthetic@example.org  ', telefone='  +55 (00) 1234  ')
        self.assertEqual(p.nome_completo, 'Nome Sintético')
        self.assertIsNone(p.nome_social)
        self.assertIsNone(p.sexo)
        self.assertEqual(p.telefone, '+55 (00) 1234')
        self.assertEqual(str(p.email), 'Synthetic@example.org')
        for values in ({'nome_completo': ' '}, {'email': 'invalid'}, {'sexo': 'x'*33},
                       {'telefone': 'x'*33}, {'genero': 'X'}, {'pessoa_id': 1}, {'clinica_id': 1},
                       {'data_nascimento': date.today()+timedelta(days=1)}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                PessoaCreate(**dict({'nome_completo': 'Synthetic', 'cpf': VALID_CPF}, **values))

    def test_canonical_head_and_direct_parent(self):
        scripts = ScriptDirectory.from_config(config())
        self.assertEqual(scripts.get_heads(), ['g2c1_autorizacao_v1'])
        self.assertEqual(scripts.get_revision('g2b1_institucional_v1').down_revision, 'g2a3_identidade_v1')
        self.assertEqual(scripts.get_revision('g2a2_pessoas_v1').down_revision, 'g1_institucional_v1')


@unittest.skipUnless(URL, 'Requires explicitly disposable G2.A.2 PostgreSQL 18')
class PessoaPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.port not in (None, 5432) or url.database != 'm0_baseline':
            raise RuntimeError('Only the isolated local G2.A.2 database is allowed')
        cls.admin = create_engine(url, isolation_level='AUTOCOMMIT')
        cls.engines = []
        with cls.admin.connect() as c:
            if int(c.execute(text('SHOW server_version_num')).scalar()) // 10000 != 18:
                raise RuntimeError('PostgreSQL 18 required')
        for mode in ('empty', 'incremental'):
            name = 'g2a2_' + mode + '_' + uuid4().hex
            with cls.admin.connect() as c:
                c.execute(text('CREATE DATABASE ' + name))
            engine = create_engine(url.set(database=name), connect_args={'options': '-c lock_timeout=5000 -c statement_timeout=15000'})
            cls.engines.append((name, engine))
            with engine.begin() as c:
                if mode == 'incremental':
                    command.upgrade(config(c), 'g1_institucional_v1')
                    # Existing, explicitly associated legacy actors, plus a responsible link.
                    c.execute(text("INSERT INTO profissionais(id,nome) VALUES(810,'Synthetic professional')"))
                    c.execute(text("INSERT INTO pacientes(id,nome,genero,profissional_id) VALUES(810,'Synthetic patient','legacy',810)"))
                    c.execute(text("INSERT INTO usuarios(id,nome,email,senha_hash,profissional_id) VALUES(810,'Different legacy name','u@example.invalid','unused',810)"))
                    c.execute(text("INSERT INTO responsaveis(id,nome,email,senha_hash) VALUES(810,'Synthetic responsible','r@example.invalid','unused')"))
                    c.execute(text("INSERT INTO responsavel_paciente(responsavel_id,paciente_id,principal) VALUES(810,810,true)"))
                    cls.before = {t: c.execute(text('SELECT to_jsonb(t) FROM public.'+t+' t')).scalars().all()
                                  for t in DOMAINS + ('responsavel_paciente',)}
                command.upgrade(config(c), 'g2a2_pessoas_v1')
        cls.engine = cls.engines[0][1]

    @classmethod
    def tearDownClass(cls):
        for name, engine in cls.engines:
            engine.dispose()
            with cls.admin.connect() as c:
                c.execute(text('DROP DATABASE ' + name))
        cls.admin.dispose()

    def setUp(self):
        self.c = self.engine.connect()
        self.tx = self.c.begin()
        self.db = Session(self.c)
        self.service = PessoaService()

    def tearDown(self):
        self.db.close()
        if self.tx.is_active:
            self.tx.rollback()
        self.c.close()

    def create_person(self, payload):
        payload = dict(payload)
        if 'cpf' not in payload:
            base = f"{self.db.query(Pessoa).count()+100:09d}"
            for length in (9, 10):
                rest = sum(int(n)*w for n,w in zip(base, range(length+1,1,-1))) % 11
                base += str(0 if rest < 2 else 11-rest)
            payload['cpf'] = base
        return self.service.create(self.db, payload)

    def rejected(self, sql, params=None):
        with self.assertRaises((IntegrityError, DataError)):
            with self.c.begin_nested():
                self.c.execute(text(sql), params or {})

    def test_empty_and_incremental_catalogues_match(self):
        def catalogue(engine):
            with engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT version_num FROM public.alembic_version')).scalar(), 'g2a2_pessoas_v1')
                result = []
                for query in (
                    "SELECT c.relname,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,a.attidentity,pg_get_expr(d.adbin,d.adrelid) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_attribute a ON a.attrelid=c.oid LEFT JOIN pg_attrdef d ON d.adrelid=c.oid AND d.adnum=a.attnum WHERE n.nspname='public' AND c.relkind='r' AND a.attnum>0 AND NOT a.attisdropped ORDER BY 1,2",
                    "SELECT conrelid::regclass::text,conname,pg_get_constraintdef(oid) FROM pg_constraint WHERE connamespace='public'::regnamespace ORDER BY 1,2",
                    "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY 1,2",
                    "SELECT sequencename,data_type,start_value,min_value,max_value,increment_by,cycle FROM pg_sequences WHERE schemaname='public' ORDER BY 1",
                ):
                    result.append(c.execute(text(query)).all())
                return result
        self.assertEqual(catalogue(self.engine), catalogue(self.engines[1][1]))

    def test_exact_physical_person_contract_and_orm(self):
        columns = inspect(self.c).get_columns('pessoas', schema='public')
        expected = {'id': ('integer', False), 'nome_completo': ('text', False),
                    'nome_social': ('text', True), 'data_nascimento': ('date', True),
                    'sexo': ('character varying(32)', True), 'cpf': ('character varying(11)', True),
                    'email': ('text', True), 'telefone': ('character varying(32)', True),
                    'ativo': ('boolean', False), 'criado_em': ('timestamp with time zone', False),
                    'atualizado_em': ('timestamp with time zone', False)}
        actual = self.c.execute(text("SELECT a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull FROM pg_attribute a WHERE a.attrelid='public.pessoas'::regclass AND a.attnum>0 AND NOT a.attisdropped")).all()
        self.assertEqual({n:(t,v) for n,t,v in actual}, expected)
        self.assertEqual(set(Pessoa.__table__.c.keys()), set(expected))
        for col in columns:
            model = Pessoa.__table__.c[col['name']]
            self.assertEqual(col['nullable'], model.nullable)
            self.assertEqual(str(col['type'].compile(dialect=dialect())), str(model.type.compile(dialect=dialect())))
            if col['name']=='id':
                self.assertFalse(col['identity']['always'])
                self.assertIsNotNone(model.identity)
            else:
                self.assertEqual(col['default'], {'ativo':'true','criado_em':'now()','atualizado_em':'now()'}.get(col['name']))
        inspector = inspect(self.c)
        self.assertEqual(inspector.get_pk_constraint('pessoas')['constrained_columns'], ['id'])
        self.assertEqual([u['column_names'] for u in inspector.get_unique_constraints('pessoas')], [['cpf']])
        self.assertEqual({c['name'] for c in inspector.get_check_constraints('pessoas')},
                         {'ck_pessoas_nome_completo','ck_pessoas_nome_social','ck_pessoas_sexo','ck_pessoas_email','ck_pessoas_telefone','ck_pessoas_cpf_formato','ck_pessoas_timestamps'})
        self.assertEqual(self.c.execute(text("SELECT attidentity FROM pg_attribute WHERE attrelid='public.pessoas'::regclass AND attname='id'")).scalar(), 'd')
        self.assertIsNotNone(self.c.execute(text("SELECT pg_get_serial_sequence('public.pessoas','id')")).scalar())

    def test_no_backfill_or_legacy_changes(self):
        with self.engines[1][1].connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM pessoas')).scalar(),0)
            for table in DOMAINS:
                self.assertEqual(c.execute(text(f'SELECT count(*) FROM {table} WHERE pessoa_id IS NOT NULL')).scalar(),0)
                current=c.execute(text(f"SELECT to_jsonb(t)-'pessoa_id' FROM {table} t")).scalars().all()
                self.assertEqual(current,self.before[table])
            self.assertEqual(c.execute(text('SELECT to_jsonb(t) FROM responsavel_paciente t')).scalars().all(), self.before['responsavel_paciente'])

    def test_four_nullable_nonunique_fks_and_indexes(self):
        inspector=inspect(self.c)
        for model in (Paciente,Profissional,Usuario,Responsavel):
            table=model.__tablename__
            column=next(c for c in inspector.get_columns(table) if c['name']=='pessoa_id')
            self.assertTrue(column['nullable']); self.assertIsNone(column['default'])
            fk=next(f for f in inspector.get_foreign_keys(table) if f['constrained_columns']==['pessoa_id'])
            self.assertEqual(fk['referred_table'],'pessoas'); self.assertEqual(fk['referred_columns'],['id'])
            self.assertEqual(fk['options']['ondelete'],'RESTRICT')
            index=next(i for i in inspector.get_indexes(table) if i['name']==f'ix_{table}_pessoa_id')
            self.assertFalse(index['unique']); self.assertEqual(index['column_names'],['pessoa_id'])
            method=self.c.execute(text('SELECT a.amname FROM pg_class i JOIN pg_am a ON a.oid=i.relam WHERE i.oid=to_regclass(:name)'),{'name':index['name']}).scalar()
            self.assertEqual(method,'btree')
            self.assertFalse(any(u['column_names']==['pessoa_id'] for u in inspector.get_unique_constraints(table)))
            orm_fk=next(iter(model.__table__.c.pessoa_id.foreign_keys))
            self.assertEqual(orm_fk.target_fullname,'pessoas.id'); self.assertEqual(orm_fk.ondelete,'RESTRICT')

    def test_identity_null_cpf_and_duplicate_contact_allowed(self):
        first=Pessoa(nome_completo='Synthetic',email='same@example.org',telefone='same')
        second=Pessoa(nome_completo='Synthetic',email='same@example.org',telefone='same')
        self.db.add_all([first,second]); self.db.flush()
        self.assertNotEqual(first.id,second.id)
        self.assertIsNone(first.cpf); self.assertIsNone(second.cpf)
        self.assertTrue(first.ativo)
        self.assertEqual(first.criado_em,first.atualizado_em)
        self.assertEqual(PessoaOut.model_validate(first).id, first.id)
        self.c.execute(text("INSERT INTO pessoas(id,nome_completo) VALUES(90000,'Explicit identity allowed')"))

    def test_duplicate_cpf_rejected_even_inactive_without_matching(self):
        self.create_person(dict(nome_completo='Synthetic',cpf=VALID_CPF,ativo=False))
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.create_person(dict(nome_completo='Other',cpf='529.982.247-25'))
        self.assertEqual(self.db.query(Pessoa).count(),1)

    def test_database_structural_guards(self):
        for field,value in [('nome_completo',''),('nome_completo',' untrimmed'),('nome_social',' '),
                            ('sexo',' '),('email',' '),('telefone',' '),('cpf','123'),('cpf','529.982.247-25'),('cpf','abcdefghijk')]:
            if field=='nome_completo':
                self.rejected('INSERT INTO pessoas(nome_completo) VALUES(:v)',{'v':value})
            else:
                self.rejected(f"INSERT INTO pessoas(nome_completo,{field}) VALUES('Synthetic',:v)",{'v':value})
        self.rejected("INSERT INTO pessoas(nome_completo,ativo) VALUES('Synthetic',NULL)")
        self.rejected("INSERT INTO pessoas(nome_completo,criado_em,atualizado_em) VALUES('Synthetic','2026-02-01','2026-01-01')")
        # Database deliberately enforces representation, not CPF check digits.
        self.c.execute(text("INSERT INTO pessoas(nome_completo,cpf) VALUES('Synthetic','52998224724')"))
        with self.assertRaises(ValidationError): PessoaCreate(nome_completo='Synthetic',cpf='52998224724')

    def test_cardinality_and_restrict_for_all_four_domains(self):
        for model in (Paciente,Profissional,Usuario,Responsavel):
            person=self.create_person(dict(nome_completo='Synthetic'))
            for n in range(2):
                args=dict(nome='Synthetic',pessoa_id=person.id)
                if model in (Usuario,Responsavel): args.update(email=f'{model.__tablename__}{n}@example.invalid',senha_hash='unused')
                self.db.add(model(**args))
            self.db.flush()
            self.assertEqual(self.db.query(model).filter_by(pessoa_id=person.id).count(),2)
            self.rejected('DELETE FROM pessoas WHERE id=:id',{'id':person.id})
            self.rejected(f'UPDATE {model.__tablename__} SET pessoa_id=-1')

    def test_service_update_and_transaction_owned_by_caller(self):
        row=self.create_person(dict(nome_completo='Synthetic'))
        identity=row.id
        self.service.update(self.db,identity,{'nome_social':' Chosen '})
        self.assertEqual(row.nome_social,'Chosen'); self.assertIsNotNone(row.cpf)
        self.assertGreaterEqual(row.atualizado_em,row.criado_em)
        with self.assertRaises(ValueError): self.service.update(self.db,identity,{'clinica_id':1})
        with self.assertRaises(ValueError): self.service.update(self.db,identity,{'cpf':'123'})
        self.db.close(); self.tx.rollback()
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM pessoas WHERE id=:id'),{'id':identity}).scalar(),0)

    def test_person_association_never_grants_access_or_changes_legacy(self):
        from app.models import Clinica, ModuloClinico, ProfissionalModulo
        one=Clinica(nome='One'); two=Clinica(nome='Two'); self.db.add_all([one,two]); self.db.flush()
        person=self.create_person(dict(nome_completo='Canonical',ativo=False))
        professional=Profissional(nome='Legacy professional',clinica_id=one.id,ativo=True,pessoa_id=person.id)
        patient=Paciente(nome='Legacy patient',genero='legacy',clinica_id=two.id,ativo=True,pessoa_id=person.id)
        self.db.add_all([professional,patient]); self.db.flush()
        user=Usuario(nome='Legacy user',email='legacy@example.invalid',senha_hash='unused',perfil='PROFISSIONAL',clinica_id=one.id,profissional_id=professional.id,ativo=True,pessoa_id=person.id)
        self.db.add(user)
        self.db.add(ModuloClinico(id=2,nome='Cardio',slug='cardiometabolico',ativo=True));self.db.flush()
        self.db.add(ProfissionalModulo(profissional_id=professional.id,modulo_id=2));self.db.flush()
        with self.assertRaises(HTTPException) as e: authorized_patient(self.db,user,patient.id,'CARDIO')
        self.assertEqual(e.exception.status_code,404)
        self.assertTrue(user.ativo);self.assertTrue(patient.ativo)
        self.assertEqual(patient.nome,'Legacy patient');self.assertEqual(patient.genero,'legacy')
        self.assertIsNone(person.sexo)

    def test_downgrade_empty_and_reupgrade(self):
        command.downgrade(config(self.c),'g1_institucional_v1')
        self.assertNotIn('pessoas',inspect(self.c).get_table_names())
        for table in DOMAINS:
            self.assertNotIn('pessoa_id',[c['name'] for c in inspect(self.c).get_columns(table)])
        self.assertEqual(self.c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g1_institucional_v1')
        command.upgrade(config(self.c),'g2a2_pessoas_v1')
        self.assertEqual(self.c.execute(text('SELECT count(*) FROM pessoas')).scalar(),0)

    def test_downgrade_blocks_person_even_without_links(self):
        self.create_person(dict(nome_completo='Synthetic'))
        with self.assertRaisesRegex(RuntimeError,'existem Pessoas'):
            command.downgrade(config(self.c),'g1_institucional_v1')
        self.assertEqual(self.c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g2a2_pessoas_v1')
        self.assertEqual(self.db.query(Pessoa).count(),1)

    def test_downgrade_blocks_linked_person(self):
        p=self.create_person(dict(nome_completo='Synthetic'))
        self.db.add(Paciente(nome='Synthetic',pessoa_id=p.id));self.db.flush()
        with self.assertRaisesRegex(RuntimeError,'downgrade bloqueado'):
            command.downgrade(config(self.c),'g1_institucional_v1')
        self.assertEqual(self.db.query(Paciente).filter_by(pessoa_id=p.id).count(),1)

    def test_downgrade_refuses_stale_snapshot_isolation(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c:
            with c.begin():
                with self.assertRaisesRegex(RuntimeError,'exige READ COMMITTED'):
                    command.downgrade(config(c),'g1_institucional_v1')
                self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g2a2_pessoas_v1')

    def test_downgrade_preserves_populated_unreconciled_legacy(self):
        with self.engines[1][1].connect() as c:
            tx = c.begin()
            try:
                command.downgrade(config(c),'g1_institucional_v1')
                for table in DOMAINS + ('responsavel_paciente',):
                    self.assertEqual(c.execute(text(f'SELECT to_jsonb(t) FROM {table} t')).scalars().all(),self.before[table])
                command.upgrade(config(c),'g2a2_pessoas_v1')
                self.assertEqual(c.execute(text('SELECT count(*) FROM pessoas')).scalar(),0)
            finally:
                tx.rollback()
