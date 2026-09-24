"""Real disposable PG18, including separate concurrent transactions and HTTP."""
import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from unittest.mock import patch
from alembic import command
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import FastAPI
from test_whatsapp_security import LocalClient as TestClient
from app.database import get_db
from app.core.deps import get_usuario_atual
from app.models import Pessoa, Paciente, Profissional, Responsavel, Usuario
from app.models.identidade_operacao import IdentidadeOperacao
from app.schemas.identidade import IdentidadeComando, AdicionarPapel, AssociarPapelLegado, AssociarContaLegada
from app.services.identidade import IdentidadeService, IdentidadeErro
from app.routers.identidades import router, write
from test_m0_baseline import config

URL=os.getenv('G2A3_TEST_POSTGRES_URL')
CPF='52998224725'


@unittest.skipUnless(URL,'Requires disposable PostgreSQL 18')
class IdentityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=make_url(URL)
        if url.host!='127.0.0.1' or url.database!='m0_baseline':
            raise RuntimeError('Disposable local database only')
        cls.admin=create_engine(url,isolation_level='AUTOCOMMIT')
        cls.name='g2a3_'+uuid4().hex
        with cls.admin.connect() as c:
            assert int(c.execute(text('SHOW server_version_num')).scalar())//10000==18
            c.execute(text('CREATE DATABASE '+cls.name))
        cls.engine=create_engine(url.set(database=cls.name),connect_args={'options':'-c lock_timeout=5000 -c statement_timeout=15000'})
        with cls.engine.begin() as c: command.upgrade(config(c),'g2a3_identidade_v1')

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:c.execute(text('DROP DATABASE '+cls.name))
        cls.admin.dispose()

    def setUp(self):
        self.db=Session(self.engine)
        self.actor=Usuario(nome='Admin synthetic',email=uuid4().hex+'@example.invalid',senha_hash='test-only-existing',perfil='ADMIN',ativo=True)
        self.db.add(self.actor);self.db.commit();self.actor_id=self.actor.id
        self.service=IdentidadeService()

    def tearDown(self):
        self.db.rollback();self.db.close()
        # Dedicated test database; no production URLs can pass setUpClass.
        with self.engine.begin() as c:
            c.execute(text('TRUNCATE identidade_operacoes, pessoas, pacientes, profissionais, responsaveis, usuarios CASCADE'))

    def cmd(self, cls=IdentidadeComando, **kw):
        values=dict(chave_idempotencia=uuid4(),pessoa=dict(nome_completo='Canonical',cpf=CPF),motivo='Synthetic test')
        values.update(kw)
        return cls(**values)

    def test_physical_contract_and_preserved_nullable_cpf(self):
        i=inspect(self.engine)
        for t in ('pacientes','profissionais','responsaveis','usuarios'):
            self.assertIn(['pessoa_id'],[u['column_names'] for u in i.get_unique_constraints(t)])
            self.assertTrue(next(c for c in i.get_columns(t) if c['name']=='pessoa_id')['nullable'])
        self.assertTrue(next(c for c in i.get_columns('pessoas') if c['name']=='cpf')['nullable'])
        self.assertEqual(len(i.get_foreign_keys('identidade_operacoes')),7)
        self.assertTrue(all(f['options']['ondelete']=='RESTRICT' for f in i.get_foreign_keys('identidade_operacoes')))
        self.assertEqual(self.db.query(Pessoa).count(),0)
        self.assertIsNone(self.actor.pessoa_id)
        self.assertEqual(self.db.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g2a3_identidade_v1')

    def test_create_reuse_roles_and_no_access_or_account_creation(self):
        first=self.service.executar(self.db,self.actor_id,self.cmd(AdicionarPapel,papel='PACIENTE'))
        second=self.service.executar(self.db,self.actor_id,self.cmd(AdicionarPapel,papel='PROFISSIONAL'))
        third=self.service.executar(self.db,self.actor_id,self.cmd(AdicionarPapel,papel='PACIENTE'))
        self.assertEqual(first['pessoa_id'],second['pessoa_id'])
        self.assertEqual(first['paciente_id'],third['paciente_id'])
        self.assertEqual(self.db.query(Pessoa).count(),1)
        self.assertEqual(self.db.query(Usuario).count(),1)
        for model in (Paciente,Profissional):
            row=self.db.query(model).one();self.assertFalse(row.ativo);self.assertIsNone(row.clinica_id)
        for table in ('paciente_modulos','profissional_modulos','responsavel_paciente'):
            self.assertEqual(self.db.execute(text('SELECT count(*) FROM '+table)).scalar(),0)
        self.assertEqual(self.db.query(IdentidadeOperacao).count(),3)

    def test_responsible_creation_unavailable_without_side_effects(self):
        with self.assertRaisesRegex(IdentidadeErro,'ROLE_CREATION_UNAVAILABLE'):
            self.service.executar(self.db,self.actor_id,self.cmd(AdicionarPapel,papel='RESPONSAVEL'))
        self.db.rollback()
        self.assertEqual(self.db.query(Pessoa).count(),0)
        self.assertEqual(self.db.query(Responsavel).count(),0)

    def test_idempotency_same_request_and_conflict(self):
        cmd=self.cmd()
        first=self.service.executar(self.db,self.actor_id,cmd);self.db.commit()
        self.assertEqual(first,self.service.executar(self.db,self.actor_id,cmd))
        with self.assertRaisesRegex(IdentidadeErro,'IDEMPOTENCY_CONFLICT'):
            self.service.executar(self.db,self.actor_id,self.cmd(chave_idempotencia=cmd.chave_idempotencia,motivo='different'))
        self.db.rollback()
        self.assertEqual(self.db.query(IdentidadeOperacao).count(),1)

    def test_cadastral_conflict_never_overwrites(self):
        self.service.executar(self.db,self.actor_id,self.cmd());self.db.commit()
        with self.assertRaisesRegex(IdentidadeErro,'CADASTRAL_CONFLICT'):
            self.service.executar(self.db,self.actor_id,self.cmd(pessoa=dict(nome_completo='Different',cpf=CPF)))
        self.db.rollback()
        self.assertEqual(self.db.query(Pessoa).one().nome_completo,'Canonical')

    def test_legacy_account_preserves_all_fields(self):
        before={c.name:getattr(self.actor,c.name) for c in Usuario.__table__.columns}
        result=self.service.executar(self.db,self.actor_id,self.cmd(AssociarContaLegada,registro_id=self.actor_id,tipo_evidencia='verified',referencia_evidencia='ticket',divergencias_confirmadas=['nome']))
        self.db.flush()
        after={c.name:getattr(self.actor,c.name) for c in Usuario.__table__.columns}
        self.assertEqual({k:v for k,v in after.items() if k!='pessoa_id'},{k:v for k,v in before.items() if k!='pessoa_id'})
        self.assertEqual(after['pessoa_id'],result['pessoa_id'])
        self.assertEqual(self.db.query(IdentidadeOperacao).one().tipo_operacao,'ASSOCIAR_CONTA')

    def test_legacy_responsible_and_patient_regularization(self):
        responsible=Responsavel(nome='Canonical',email='r@example.invalid',senha_hash='existing',telefone='existing-phone',ativo=True)
        self.db.add(responsible);self.db.flush()
        before=responsible.senha_hash,responsible.email,responsible.telefone,responsible.ativo
        self.service.executar(self.db,self.actor_id,self.cmd(AssociarPapelLegado,papel='RESPONSAVEL',registro_id=responsible.id,tipo_evidencia='verified',referencia_evidencia='ticket'))
        self.assertEqual(before,(responsible.senha_hash,responsible.email,responsible.telefone,responsible.ativo))
        self.assertIsNotNone(responsible.pessoa_id)

    def test_existing_responsible_reused_without_credentials(self):
        row=Responsavel(nome='Canonical',email='legacy@example.invalid',senha_hash='existing',ativo=True)
        self.db.add(row);self.db.flush()
        self.service.executar(self.db,self.actor_id,self.cmd(AssociarPapelLegado,papel='RESPONSAVEL',registro_id=row.id,tipo_evidencia='verified',referencia_evidencia='ticket'))
        result=self.service.executar(self.db,self.actor_id,self.cmd(AdicionarPapel,papel='RESPONSAVEL'))
        self.assertEqual(result['responsavel_id'],row.id)
        self.assertEqual(result['resultado'],'PAPEL_REUTILIZADO')
        self.assertEqual(self.db.query(Responsavel).count(),1)
        self.assertEqual((row.email,row.senha_hash),('legacy@example.invalid','existing'))

    def test_concurrent_legacy_claims_do_not_reassign(self):
        row=Paciente(nome='Canonical',ativo=True)
        self.db.add(row);self.db.commit();record_id=row.id
        self.db.rollback()
        barrier=Barrier(2)
        def worker(cpf):
            with Session(self.engine) as db:
                barrier.wait(timeout=5)
                try:
                    result=self.service.executar(db,self.actor_id,self.cmd(AssociarPapelLegado,
                        pessoa=dict(nome_completo='Canonical',cpf=cpf),papel='PACIENTE',registro_id=record_id,
                        tipo_evidencia='verified',referencia_evidencia='ticket'))
                    db.commit();return result['resultado']
                except IdentidadeErro as exc:
                    db.rollback();return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,[CPF,'11144477735']))
        self.assertCountEqual(results,['LEGADO_ASSOCIADO','ASSOCIATION_CONFLICT'])
        self.assertEqual(self.db.query(Pessoa).count(),1)
        self.assertEqual(self.db.query(IdentidadeOperacao).count(),1)
        self.assertEqual(self.db.get(Paciente,record_id).pessoa_id,self.db.query(Pessoa).one().id)

    def test_legacy_conflict_and_institutional_context_stop(self):
        patient=Paciente(nome='Legacy',ativo=True);self.db.add(patient);self.db.commit()
        with self.assertRaisesRegex(IdentidadeErro,'LEGACY_CADASTRAL_CONFLICT'):
            self.service.executar(self.db,self.actor_id,self.cmd(AssociarPapelLegado,papel='PACIENTE',registro_id=patient.id,tipo_evidencia='verified',referencia_evidencia='ticket'))
        self.db.rollback();self.assertEqual(self.db.query(Pessoa).count(),0)
        with self.assertRaisesRegex(IdentidadeErro,'INSTITUTIONAL_CONTEXT_PENDING'):
            self.service.executar(self.db,self.actor_id,self.cmd(AdicionarPapel,papel='PACIENTE',contexto_clinica_id=99))
        self.db.rollback();self.assertIsNone(self.db.get(Paciente,patient.id).pessoa_id)

    def test_failure_in_provenance_rolls_back_entire_operation(self):
        original=self.db.flush
        def failing(*a,**k):
            if any(isinstance(o,IdentidadeOperacao) for o in self.db.new): raise RuntimeError('synthetic failure')
            return original(*a,**k)
        with patch.object(self.db,'flush',side_effect=failing):
            with self.assertRaises(Exception):write(self.db,self.actor,self.cmd(AdicionarPapel,papel='PACIENTE'))
        self.assertEqual(self.db.query(Pessoa).count(),0)
        self.assertEqual(self.db.query(Paciente).count(),0)
        self.assertEqual(self.db.query(IdentidadeOperacao).count(),0)

    def race(self,same_key):
        self.db.rollback()
        barrier=Barrier(2);key=uuid4()
        def worker(n):
            with Session(self.engine) as db:
                barrier.wait(timeout=5)
                result=self.service.executar(db,self.actor_id,self.cmd(AdicionarPapel,papel='PACIENTE',chave_idempotencia=key if same_key else uuid4()))
                db.commit();return result
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(worker,range(2)))
        self.assertEqual(results[0]['pessoa_id'],results[1]['pessoa_id'])
        self.assertEqual(results[0]['paciente_id'],results[1]['paciente_id'])
        self.assertEqual(self.db.query(Pessoa).count(),1)
        self.assertEqual(self.db.query(Paciente).count(),1)
        self.assertEqual(self.db.query(IdentidadeOperacao).count(),1 if same_key else 2)

    def test_real_concurrency_same_cpf_and_role(self):self.race(False)
    def test_real_concurrency_same_idempotency_key(self):self.race(True)

    def test_http_admin_contract_and_no_account_creation_route(self):
        app=FastAPI();app.include_router(router)
        def db_override():yield self.db
        app.dependency_overrides[get_db]=db_override
        app.dependency_overrides[get_usuario_atual]=lambda:self.actor
        client=TestClient(app)
        payload=self.cmd().model_dump(mode='json')
        response=client.post('/admin/identidades/pessoas',json=payload)
        self.assertEqual(response.status_code,200,response.text)
        self.assertNotIn('senha',response.text)
        self.actor.perfil='PROFISSIONAL';self.db.flush()
        self.assertEqual(client.post('/admin/identidades/pessoas',json=payload).status_code,403)
        self.assertEqual(client.post('/admin/identidades/usuarios',json={}).status_code,404)

    def test_downgrade_guard(self):
        self.service.executar(self.db,self.actor_id,self.cmd());self.db.commit()
        with self.engine.begin() as c:
            with self.assertRaisesRegex(RuntimeError,'proveniência'):
                command.downgrade(config(c),'g2a2_pessoas_v1')
        self.assertEqual(self.db.query(IdentidadeOperacao).count(),1)

    def test_incremental_duplicate_preflight_is_atomic(self):
        name='g2a3_duplicate_'+uuid4().hex
        with self.admin.connect() as c:c.execute(text('CREATE DATABASE '+name))
        engine=create_engine(make_url(URL).set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'g2a2_pessoas_v1')
                c.execute(text("INSERT INTO pessoas(nome_completo) VALUES ('Legacy')"))
                c.execute(text("INSERT INTO pacientes(nome,pessoa_id) SELECT 'One',id FROM pessoas UNION ALL SELECT 'Two',id FROM pessoas"))
            with self.assertRaisesRegex(RuntimeError,'STOP_DUPLICATE_ASSOCIATION'):
                with engine.begin() as c:command.upgrade(config(c),'g2a3_identidade_v1')
            with engine.connect() as c:
                self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'g2a2_pessoas_v1')
                self.assertNotIn('identidade_operacoes',inspect(c).get_table_names())
                self.assertEqual(c.execute(text('SELECT count(*) FROM pacientes')).scalar(),2)
            with engine.begin() as c:
                c.execute(text('UPDATE pacientes SET pessoa_id=NULL'))
                command.upgrade(config(c),'g2a3_identidade_v1')
                command.downgrade(config(c),'g2a2_pessoas_v1')
        finally:
            engine.dispose()
            with self.admin.connect() as c:c.execute(text('DROP DATABASE '+name))
