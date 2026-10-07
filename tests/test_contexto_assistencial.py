"""W1A domain, catalogue and real cross-link races on disposable PostgreSQL 18."""
import os
import unittest
from datetime import date
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import dialect
from pydantic import ValidationError
from app.models.contexto_assistencial import ContextoAssistencial as Contexto, ContextoAssistencialLinha as Linha
from app.services.contexto_assistencial import ContextoAssistencialService as Service, ContextoAssistencialErro as Error
from app.schemas.contexto_assistencial import ContextoCreate, ContextoLinhaCreate
from test_m0_baseline import config

URL = os.getenv('M0_TEST_POSTGRES_URL')


class ContextContractTests(unittest.TestCase):
    def test_no_legacy_or_independent_identity_inputs(self):
        for extra in ('clinica_id', 'paciente_id', 'instituicao_id', 'pessoa_id', 'modulo_id', 'natureza_assistencial'):
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                ContextoCreate(paciente_instituicao_id=1, data_inicio='2026-01-01', **{extra: 1})
        for model in (Contexto, Linha):
            self.assertNotIn('clinica_id', model.__table__.c)
        self.assertNotIn('pessoa_id', Contexto.__table__.c)

    def test_schema_explicit_link_and_period(self):
        for payload in ({'data_inicio':'2026-01-01'},
                        {'paciente_instituicao_id':True,'data_inicio':'2026-01-01'},
                        {'paciente_instituicao_id':1,'data_inicio':'2026-02-01','data_fim':'2026-01-01'}):
            with self.assertRaises(ValidationError): ContextoCreate(**payload)
        with self.assertRaises(ValidationError):
            ContextoLinhaCreate(contexto_assistencial_id=1, modulo_id=1, ativo=True)

    def test_head_and_frozen_parent(self):
        script = ScriptDirectory.from_config(config())
        self.assertEqual(script.get_heads(), ['w3_intervencao_autoria_v1'])
        self.assertEqual(script.get_revision('w1a_contexto_v1').down_revision, 'f1_economia_v1')
        self.assertEqual(script.get_revision('f1_economia_v1').down_revision, 'g2c1_autorizacao_v1')


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL 18')
class ContextPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url = make_url(URL)
        if url.host != '127.0.0.1' or url.database != 'm0_baseline':
            raise RuntimeError('Dedicated local database required')
        cls.url=url; cls.admin=create_engine(url,isolation_level='AUTOCOMMIT')
        cls.name='w1a_'+uuid4().hex
        with cls.admin.connect() as c:
            if int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000 != 18:
                raise RuntimeError('PG18 required')
            c.exec_driver_sql('CREATE DATABASE '+cls.name)
        cls.engine=create_engine(url.set(database=cls.name),connect_args={'options':'-c lock_timeout=5000 -c statement_timeout=15000'})
        # Historical downgrade assertions must start before the non-destructive adoption barrier.
        with cls.engine.begin() as c: command.upgrade(config(c),'w2b_checkin_v1')

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+cls.name)
        cls.admin.dispose()

    def setUp(self):
        with self.engine.begin() as c:
            self.actor=c.execute(text("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES ('Synthetic',:email,'test','SUPORTE',true) RETURNING id"),dict(email=uuid4().hex+'@example.invalid')).scalar()
            self.person=c.exec_driver_sql("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic') RETURNING id").scalar()
            self.patient=c.execute(text("INSERT INTO pacientes(nome,pessoa_id) VALUES ('Synthetic',:p) RETURNING id"),dict(p=self.person)).scalar()
            self.other=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Other synthetic') RETURNING id").scalar()
            self.a=c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('A','OUTRO') RETURNING id").scalar()
            self.b=c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('B','OUTRO') RETURNING id").scalar()
            self.links=[]
            for institution,kind in ((self.a,'COLABORADOR'),(self.a,'BENEFICIARIO'),(self.b,'ASSISTENCIAL')):
                self.links.append(c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,:t,'2026-01-01') RETURNING id"),dict(p=self.patient,i=institution,t=kind)).scalar())
            self.module=c.execute(text("INSERT INTO modulos_clinicos(nome,slug,descricao,ativo) VALUES (:n,:n,'Synthetic',true) RETURNING id"),dict(n='W1A-'+uuid4().hex)).scalar()
        self.db=Session(self.engine);self.service=Service()

    def tearDown(self):
        self.db.rollback();self.db.close()

    def create(self, link=0, start='2026-01-01', end=None):
        return self.service.create(self.db,dict(paciente_instituicao_id=self.links[link],data_inicio=start,data_fim=end),actor_id=self.actor)

    def raw(self, connection, link=0, start='2026-01-01', end=None, patient=None, institution=None, active=True):
        return connection.execute(text('INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,data_fim,criado_por_usuario_id,ativo) VALUES (:l,:p,:i,:s,:e,:u,:a) RETURNING id'),
            dict(l=self.links[link],p=patient or self.patient,i=institution or (self.b if link==2 else self.a),s=start,e=end,u=self.actor,a=active)).scalar()

    def test_create_derives_identity_without_grants_or_person_creation(self):
        before=self.db.execute(text('SELECT count(*) FROM pessoas')).scalar()
        row=self.create()
        self.assertEqual((row.paciente_id,row.instituicao_id,row.paciente_instituicao_id),(self.patient,self.a,self.links[0]))
        self.assertEqual(row.criado_por_usuario_id,self.actor)
        self.assertTrue(row.ativo);self.assertIsNone(row.data_fim)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM pessoas')).scalar(),before)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM paciente_modulos WHERE paciente_id=:p'),dict(p=self.patient)).scalar(),0)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM usuario_instituicao_acessos WHERE usuario_id=:u'),dict(u=self.actor)).scalar(),0)

    def test_missing_person_rejected(self):
        self.db.execute(text('UPDATE pacientes SET pessoa_id=NULL WHERE id=:p'),dict(p=self.patient))
        with self.assertRaisesRegex(Error,'EXPLICIT_PERSON_REQUIRED'):self.create()

    def test_missing_link_rejected(self):
        with self.assertRaisesRegex(Error,'RESOURCE_NOT_FOUND'):
            self.service.create(self.db,dict(paciente_instituicao_id=2147483647,data_inicio='2026-01-01'),actor_id=self.actor)

    def test_period_and_invalidated_link_rejected(self):
        with self.assertRaisesRegex(Error,'LINK_PERIOD'):self.create(start='2025-12-31')
        self.db.execute(text("UPDATE paciente_instituicoes SET data_fim='2026-12-31' WHERE id=:id"),dict(id=self.links[0]))
        with self.assertRaisesRegex(Error,'LINK_PERIOD'):self.create()
        self.create(end='2026-12-31')
        self.db.execute(text('UPDATE paciente_instituicoes SET ativo=false WHERE id=:id'),dict(id=self.links[2]))
        with self.assertRaisesRegex(Error,'LINK_PERIOD'):self.create(link=2)

    def test_close_no_reopening_and_next_day_return(self):
        row=self.create();self.service.close(self.db,row.id,dict(data_fim='2026-12-31'))
        self.assertTrue(row.ativo)
        self.assertEqual(self.service.close(self.db,row.id,dict(data_fim='2026-12-31')).id,row.id)
        with self.assertRaisesRegex(Error,'ALREADY_CLOSED'):
            self.service.close(self.db,row.id,dict(data_fim='2027-01-01'))
        with self.assertRaises(ValidationError): self.service.close(self.db,row.id,dict(data_fim=None))
        new=self.create(link=1,start='2027-01-01')
        self.assertNotEqual(row.id,new.id)
        self.assertEqual(row.data_fim,date(2026,12,31))

    def test_invalid_close_keeps_context(self):
        row=self.create()
        with self.assertRaisesRegex(Error,'INVALID_PERIOD'):self.service.close(self.db,row.id,dict(data_fim='2025-12-31'))
        self.assertIsNone(row.data_fim)

    def test_overlap_across_links_domain_and_physical(self):
        self.create(end='2026-12-31')
        with self.assertRaisesRegex(Error,'CONTEXT_PERIOD_CONFLICT'):
            self.create(link=1,start='2026-12-31')
        with self.assertRaises(IntegrityError) as raised:
            with self.db.begin_nested(): self.raw(self.db,link=1,start='2026-06-01')
        self.assertEqual(raised.exception.orig.pgcode,'23P01')
        self.assertEqual(raised.exception.orig.diag.constraint_name,'ex_contexto_vigencia')

    def test_other_institution_allowed(self):
        a=self.create();b=self.create(link=2)
        self.assertNotEqual(a.instituicao_id,b.instituicao_id)

    def test_invalidation_excludes_but_preserves_history(self):
        a=self.create();self.service.invalidate(self.db,a.id)
        b=self.create(link=1)
        self.assertFalse(a.ativo);self.assertNotEqual(a.id,b.id)
        self.assertIsNotNone(self.db.get(Contexto,a.id))
        with self.assertRaisesRegex(Error,'INVALIDATED'):self.service.close(self.db,a.id,dict(data_fim='2026-05-01'))

    def test_composite_fk_rejects_contradictory_patient_and_institution(self):
        for kwargs in (dict(patient=self.other),dict(institution=self.b)):
            with self.subTest(kwargs=kwargs),self.assertRaises(IntegrityError) as raised:
                with self.db.begin_nested():self.raw(self.db,**kwargs)
            self.assertEqual(raised.exception.orig.pgcode,'23503')
            self.assertEqual(raised.exception.orig.diag.constraint_name,'fk_contexto_vinculo_identidade')

    def test_parent_keys_and_deletion_restricted(self):
        self.create()
        for sql in ('UPDATE paciente_instituicoes SET paciente_id=:v WHERE id=:id',
                    'UPDATE paciente_instituicoes SET instituicao_id=:v WHERE id=:id',
                    'DELETE FROM paciente_instituicoes WHERE id=:id'):
            with self.subTest(sql=sql), self.assertRaises(IntegrityError):
                with self.db.begin_nested():self.db.execute(text(sql),dict(id=self.links[0],v=self.other if 'SET paciente_id' in sql else self.b))

    def test_physical_invalid_period(self):
        with self.assertRaises(IntegrityError) as raised:
            with self.db.begin_nested():self.raw(self.db,start='2026-02-01',end='2026-01-01')
        self.assertEqual(raised.exception.orig.pgcode,'23514')

    def test_line_default_duplicate_and_deactivation(self):
        c=self.create();payload=dict(contexto_assistencial_id=c.id,modulo_id=self.module)
        line=self.service.add_line(self.db,payload);self.assertFalse(line.ativo)
        with self.assertRaisesRegex(Error,'CONTEXT_LINE_DUPLICATE'):self.service.add_line(self.db,payload)
        line.ativo=True;self.db.flush()  # Synthetic historical state; W1A exposes no activation command.
        self.service.deactivate_line(self.db,c.id,line.id)
        self.assertFalse(line.ativo);self.assertIsNotNone(self.db.get(Linha,line.id))
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():self.db.delete(c);self.db.flush()

    def test_line_missing_module_and_wrong_context(self):
        c=self.create();other=self.create(link=2)
        with self.assertRaisesRegex(Error,'RESOURCE_NOT_FOUND'):
            self.service.add_line(self.db,dict(contexto_assistencial_id=c.id,modulo_id=2147483647))
        line=self.service.add_line(self.db,dict(contexto_assistencial_id=c.id,modulo_id=self.module))
        with self.assertRaisesRegex(Error,'CONTEXT_LINE_MISMATCH'):self.service.deactivate_line(self.db,other.id,line.id)
        self.service.close(self.db,c.id,dict(data_fim='2026-12-31'))
        with self.assertRaisesRegex(Error,'CONTEXT_NOT_OPEN'):
            self.service.add_line(self.db,dict(contexto_assistencial_id=c.id,modulo_id=self.module))

    def test_exact_catalogue(self):
        inspector=inspect(self.engine)
        for model in (Contexto,Linha):
            name=model.__tablename__;cols=inspector.get_columns(name)
            self.assertEqual({c['name'] for c in cols},set(model.__table__.c.keys()))
            for col in cols:
                self.assertEqual(col['nullable'],model.__table__.c[col['name']].nullable)
                self.assertEqual(str(col['type'].compile(dialect=dialect())),
                                 str(model.__table__.c[col['name']].type.compile(dialect=dialect())))
                if col['name'] not in ('id','ativo','criado_em','atualizado_em'):
                    self.assertIsNone(col['default'])
            self.assertIn('identity',next(c for c in cols if c['name']=='id'))
            self.assertEqual(next(c for c in cols if c['name']=='ativo')['default'],'true' if model is Contexto else 'false')
            for column in ('criado_em','atualizado_em'):
                self.assertEqual(next(c for c in cols if c['name']==column)['default'],'now()')
            self.assertEqual(inspector.get_pk_constraint(name)['constrained_columns'],['id'])
            self.assertTrue(all(f['options'].get('ondelete')=='RESTRICT' for f in inspector.get_foreign_keys(name)))
        self.assertEqual({x['name'] for x in inspector.get_check_constraints('contextos_assistenciais')}, {'ck_contexto_periodo'})
        self.assertEqual({tuple(x['column_names']) for x in inspector.get_unique_constraints('contexto_assistencial_linhas')}, {('contexto_assistencial_id','modulo_id')})
        self.assertIn(('id','paciente_id','instituicao_id'), {tuple(x['column_names']) for x in inspector.get_unique_constraints('paciente_instituicoes')})
        self.assertEqual({(tuple(f['constrained_columns']),f['referred_table'],tuple(f['referred_columns'])) for f in inspector.get_foreign_keys('contexto_assistencial_linhas')}, {(('contexto_assistencial_id',),'contextos_assistenciais',('id',)), (('modulo_id',),'modulos_clinicos',('id',))})
        fk=next(f for f in inspector.get_foreign_keys('contextos_assistenciais') if f['name']=='fk_contexto_vinculo_identidade')
        self.assertEqual(fk['constrained_columns'],['paciente_instituicao_id','paciente_id','instituicao_id'])
        self.assertEqual(fk['referred_columns'],['id','paciente_id','instituicao_id'])
        self.assertEqual(fk['options']['onupdate'],'RESTRICT')
        for name,columns in (('contextos_assistenciais',('paciente_instituicao_id','paciente_id','instituicao_id')),
                             ('contexto_assistencial_linhas',('contexto_assistencial_id','modulo_id'))):
            indexes={x['name']:x for x in inspector.get_indexes(name)}
            for column in columns:
                idx=indexes['ix_'+name+'_'+column];self.assertFalse(idx['unique']);self.assertEqual(idx['column_names'],[column])
        with self.engine.connect() as conn:
            definition=conn.execute(text("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ex_contexto_vigencia'")).scalar()
            self.assertIn('paciente_id WITH =',definition);self.assertIn('instituicao_id WITH =',definition)
            self.assertIn('WHERE (ativo)',definition);self.assertIn('&&',definition)

    def test_caller_rollback_is_integral(self):
        c=self.create();identity=c.id
        self.service.add_line(self.db,dict(contexto_assistencial_id=c.id,modulo_id=self.module))
        self.db.rollback()
        with self.engine.connect() as conn:
            self.assertEqual(conn.execute(text('SELECT count(*) FROM contextos_assistenciais WHERE id=:id'),dict(id=identity)).scalar(),0)
            self.assertEqual(conn.execute(text('SELECT count(*) FROM contexto_assistencial_linhas WHERE contexto_assistencial_id=:id'),dict(id=identity)).scalar(),0)

    def test_concurrent_different_links_physical_constraint(self):
        barrier=Barrier(2)
        def insert(link):
            try:
                with self.engine.begin() as c:
                    barrier.wait(timeout=10)
                    self.raw(c,link=link)
                return 'persisted'
            except IntegrityError as exc:
                return (exc.orig.pgcode,exc.orig.diag.constraint_name)
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(insert,(0,1)))
        self.assertCountEqual(result,['persisted',('23P01','ex_contexto_vigencia')])
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM contextos_assistenciais WHERE paciente_id=:p'),dict(p=self.patient)).scalar(),1)

    def test_concurrent_sequential_periods_allowed(self):
        barrier=Barrier(2)
        def insert(link):
            with self.engine.begin() as c:
                barrier.wait(timeout=10)
                self.raw(c,link=link,start='2026-01-01' if link==0 else '2027-01-01',end='2026-12-31' if link==0 else None)
            return 'persisted'
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(list(pool.map(insert,(0,1))),['persisted','persisted'])

    def test_incremental_empty_downgrade_and_no_backfill(self):
        name='w1a_roundtrip_'+uuid4().hex
        with self.admin.connect() as c:c.exec_driver_sql('CREATE DATABASE '+name)
        engine=create_engine(self.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'f1_economia_v1')
                p=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Legacy synthetic') RETURNING id").scalar()
                command.upgrade(config(c),'w1a_contexto_v1')
                for table in ('contextos_assistenciais','contexto_assistencial_linhas','pessoas','paciente_modulos'):
                    self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM '+table).scalar(),0)
                self.assertIsNone(c.execute(text('SELECT pessoa_id FROM pacientes WHERE id=:id'),dict(id=p)).scalar())
                command.downgrade(config(c),'f1_economia_v1')
                self.assertNotIn('contextos_assistenciais',inspect(c).get_table_names())
                self.assertTrue(c.exec_driver_sql("SELECT EXISTS(SELECT FROM pg_extension WHERE extname='btree_gist')").scalar())
                command.upgrade(config(c),'head')
                self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'w3_intervencao_autoria_v1')
        finally:
            engine.dispose()
            with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+name)

    def test_populated_downgrade_blocked(self):
        self.create()
        with self.assertRaisesRegex(RuntimeError,'W1A_DOWNGRADE_BLOCKED'):
            with self.db.begin_nested():command.downgrade(config(self.db.connection()),'f1_economia_v1')
