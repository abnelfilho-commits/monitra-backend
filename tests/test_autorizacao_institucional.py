"""G2.C.1 domain and physical contract on isolated PostgreSQL 18."""
import os
import unittest
from uuid import uuid4
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from types import SimpleNamespace
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Acesso
from app.models.usuario import Usuario
from app.models.institucional import Instituicao
from app.schemas.autorizacao_institucional import AcessoCreate, PerfilChange
from app.services.autorizacao_institucional import AutorizacaoInstitucionalService as Service, AutorizacaoInstitucionalErro as Error
from test_m0_baseline import config

URL = os.getenv('G2C1_TEST_POSTGRES_URL')
HEAD = 'g2c1_autorizacao_v1'
PARENT = 'g2b1_institucional_v1'


class AuthorizationContractTests(unittest.TestCase):
    def test_catalogue_defaults_and_no_temporal_or_extra_fields(self):
        for profile in ('GESTOR','PROFISSIONAL','SUPORTE'):
            self.assertFalse(AcessoCreate(usuario_id=1,instituicao_id=1,perfil_institucional=profile).ativo)
        for profile in ('ADMIN','ADMIN_CLINICA','UNKNOWN','gestor'):
            with self.assertRaises(ValidationError): PerfilChange(perfil_institucional=profile)
        for extra in ({'pessoa_id':1},{'clinica_id':1},{'data_inicio':'2026-01-01'},{'data_fim':'2026-12-31'}):
            with self.assertRaises(ValidationError):
                AcessoCreate(usuario_id=1,instituicao_id=1,perfil_institucional='GESTOR',**extra)
        self.assertEqual(set(Acesso.__table__.c.keys()),{'id','usuario_id','instituicao_id','perfil_institucional','ativo'})

    def test_single_head_direct_parent(self):
        s=ScriptDirectory.from_config(config())
        self.assertEqual(s.get_heads(),[HEAD]);self.assertEqual(s.get_revision(HEAD).down_revision,PARENT)


@unittest.skipUnless(URL,'Requires disposable PostgreSQL 18')
class AuthorizationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        url=make_url(URL)
        if url.host!='127.0.0.1' or url.database!='m0_baseline':raise RuntimeError('Disposable local database only')
        cls.admin=create_engine(url,isolation_level='AUTOCOMMIT');cls.name='g2c1_'+uuid4().hex
        with cls.admin.connect() as c:
            if int(c.execute(text('SHOW server_version_num')).scalar())//10000!=18:raise RuntimeError('PG18 required')
            c.execute(text('CREATE DATABASE '+cls.name))
        cls.engine=create_engine(url.set(database=cls.name))
        with cls.engine.begin() as c:command.upgrade(config(c),HEAD)

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:c.execute(text('DROP DATABASE '+cls.name))
        cls.admin.dispose()

    def setUp(self):
        self.s=Service()
        with self.engine.begin() as c:
            self.users={}
            for role in ('ADMIN','ADMIN_CLINICA','PROFISSIONAL','SUPORTE','UNKNOWN','ADMINISTRADOR'):
                self.users[role]=c.execute(text('INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES (:n,:e,:h,:p,true) RETURNING id'),
                    dict(n='Synthetic',e=role+'@example.invalid',h='synthetic-existing',p=role)).scalar()
            self.a=c.execute(text("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('A','OUTRO') RETURNING id")).scalar()
            self.b=c.execute(text("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('B','OUTRO') RETURNING id")).scalar()
        self.actor=self.users['ADMIN'];self.target=self.users['PROFISSIONAL'];self.db=Session(self.engine)

    def tearDown(self):
        self.db.rollback();self.db.close()
        with self.engine.begin() as c:c.execute(text('TRUNCATE usuario_instituicao_acessos,usuarios,instituicoes,pessoas,profissionais,pacientes CASCADE'))

    def create(self,db=None,profile='GESTOR',active=False,target=None,institution=None,actor=None):
        return self.s.create(db or self.db,dict(usuario_id=target or self.target,instituicao_id=institution or self.a,
            perfil_institucional=profile,ativo=active),actor_id=actor or self.actor)

    def test_exact_physical_contract(self):
        i=inspect(self.engine);cols=i.get_columns('usuario_instituicao_acessos')
        self.assertEqual({c['name'] for c in cols},set(Acesso.__table__.c.keys()))
        self.assertTrue(all(not c['nullable'] for c in cols))
        self.assertEqual({c['name']:str(c['type']) for c in cols},dict(id='INTEGER',usuario_id='INTEGER',instituicao_id='INTEGER',perfil_institucional='VARCHAR(16)',ativo='BOOLEAN'))
        self.assertEqual(next(c for c in cols if c['name']=='ativo')['default'],'false')
        self.assertEqual(i.get_pk_constraint('usuario_instituicao_acessos')['constrained_columns'],['id'])
        self.assertEqual(i.get_unique_constraints('usuario_instituicao_acessos')[0]['column_names'],['usuario_id','instituicao_id'])
        fks=i.get_foreign_keys('usuario_instituicao_acessos')
        self.assertEqual({(f['constrained_columns'][0],f['referred_table'],tuple(f['referred_columns']),f['options']['ondelete']) for f in fks},
                         {('usuario_id','usuarios',('id',),'RESTRICT'),('instituicao_id','instituicoes',('id',),'RESTRICT')})
        indexes=i.get_indexes('usuario_instituicao_acessos')
        self.assertTrue(any(x['column_names']==['instituicao_id'] and not x['unique'] for x in indexes))
        self.assertEqual(len(i.get_check_constraints('usuario_instituicao_acessos')),1)

    def test_admin_global_requires_no_grant_but_active_context(self):
        for institution in (self.a,self.b):
            result=self.s.authorize(self.db,self.actor,institution)
            self.assertTrue(result.admin_global);self.assertIsNone(result.perfil_institucional)
        self.assertEqual(self.db.query(Acesso).count(),0)
        for value in (None,0,-1,'1'):
            with self.assertRaisesRegex(Error,'EXPLICIT_INSTITUTION_REQUIRED'):self.s.authorize(self.db,self.actor,value)
        with self.assertRaisesRegex(Error,'INSTITUTION_NOT_FOUND'):self.s.authorize(self.db,self.actor,999999)

    def test_each_profile_authorizes_only_explicit_active_institution(self):
        for global_role,profile in [('ADMIN_CLINICA','GESTOR'),('PROFISSIONAL','SUPORTE'),('SUPORTE','PROFISSIONAL')]:
            user=self.users[global_role]
            with self.assertRaisesRegex(Error,'ACCESS_DENIED'):self.s.authorize(self.db,user,self.a)
            row=self.create(target=user,profile=profile)
            with self.assertRaisesRegex(Error,'ACCESS_DENIED'):self.s.authorize(self.db,user,self.a)
            self.s.activate(self.db,user,self.a,actor_id=self.actor)
            result=self.s.authorize(self.db,user,self.a)
            self.assertEqual(result.perfil_institucional,profile);self.assertFalse(result.admin_global)
            with self.assertRaisesRegex(Error,'ACCESS_DENIED'):self.s.authorize(self.db,user,self.b)
            self.assertTrue(row.ativo)

    def test_only_exact_active_admin_can_mutate(self):
        self.create()
        for role,user in self.users.items():
            if role=='ADMIN':continue
            operations=[lambda:self.create(actor=user),lambda:self.s.activate(self.db,self.target,self.a,actor_id=user),
                        lambda:self.s.deactivate(self.db,self.target,self.a,actor_id=user),
                        lambda:self.s.change_profile(self.db,self.target,self.a,{'perfil_institucional':'SUPORTE'},actor_id=user)]
            for operation in operations:
                with self.assertRaisesRegex(Error,'ADMIN_REQUIRED'):operation()
        self.db.execute(text('UPDATE usuarios SET ativo=false WHERE id=:id'),{'id':self.actor})
        with self.assertRaisesRegex(Error,'ADMIN_REQUIRED'):self.create()

    def test_idempotency_conflict_explicit_change_and_revocation(self):
        row=self.create();self.assertEqual(self.create().id,row.id)
        with self.assertRaisesRegex(Error,'ACCESS_CONFLICT'):self.create(profile='SUPORTE')
        with self.assertRaisesRegex(Error,'ACCESS_CONFLICT'):self.create(active=True)
        self.assertEqual(row.perfil_institucional,'GESTOR');self.assertFalse(row.ativo)
        self.s.activate(self.db,self.target,self.a,actor_id=self.actor)
        self.s.activate(self.db,self.target,self.a,actor_id=self.actor)
        self.s.change_profile(self.db,self.target,self.a,{'perfil_institucional':'SUPORTE'},actor_id=self.actor)
        self.s.change_profile(self.db,self.target,self.a,{'perfil_institucional':'SUPORTE'},actor_id=self.actor)
        self.assertEqual(self.s.authorize(self.db,self.target,self.a).perfil_institucional,'SUPORTE')
        self.s.deactivate(self.db,self.target,self.a,actor_id=self.actor)
        self.s.deactivate(self.db,self.target,self.a,actor_id=self.actor)
        with self.assertRaisesRegex(Error,'ACCESS_DENIED'):self.s.authorize(self.db,self.target,self.a)
        self.assertEqual(self.db.query(Acesso).count(),1)

    def test_account_and_institution_active_and_revocation_after_disabling(self):
        self.create(active=True);self.db.commit()
        for table,identity,code in [('usuarios',self.target,'USER_INACTIVE'),('instituicoes',self.a,'INSTITUTION_INACTIVE')]:
            self.db.execute(text(f'UPDATE {table} SET ativo=false WHERE id=:id'),{'id':identity})
            with self.assertRaisesRegex(Error,code):self.s.authorize(self.db,self.target,self.a)
            with self.assertRaisesRegex(Error,code):self.s.activate(self.db,self.target,self.a,actor_id=self.actor)
            self.s.deactivate(self.db,self.target,self.a,actor_id=self.actor)
            self.db.execute(text(f'UPDATE {table} SET ativo=true WHERE id=:id'),{'id':identity})
            self.s.activate(self.db,self.target,self.a,actor_id=self.actor)

    def test_no_inference_or_legacy_mutations(self):
        # Same person, human roles, clinical tenant and module are not grants.
        with self.engine.begin() as c:
            person=c.execute(text("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic') RETURNING id")).scalar()
            clinic=c.execute(text("INSERT INTO clinicas(nome) VALUES ('Synthetic') RETURNING id")).scalar()
            c.execute(text('UPDATE usuarios SET pessoa_id=:p,clinica_id=:c WHERE id=:u'),dict(p=person,c=clinic,u=self.target))
            patient=c.execute(text("INSERT INTO pacientes(nome,pessoa_id,clinica_id) VALUES ('Synthetic',:p,:c) RETURNING id"),dict(p=person,c=clinic)).scalar()
            professional=c.execute(text("INSERT INTO profissionais(nome,pessoa_id,clinica_id) VALUES ('Synthetic',:p,:c) RETURNING id"),dict(p=person,c=clinic)).scalar()
            occupation=c.execute(text("INSERT INTO ocupacoes_profissionais(nome) VALUES ('Synthetic') RETURNING id")).scalar()
            module=c.execute(text("INSERT INTO modulos_clinicos(nome,slug,ativo) VALUES ('Synthetic',:s,true) RETURNING id"),{'s':uuid4().hex}).scalar()
            c.execute(text('INSERT INTO profissional_modulos(profissional_id,modulo_id) VALUES (:p,:m)'),dict(p=professional,m=module))
            c.execute(text('INSERT INTO paciente_modulos(paciente_id,modulo_id,ativo) VALUES (:p,:m,true)'),dict(p=patient,m=module))
            c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'OUTRO','2026-01-01')"),dict(p=patient,i=self.a))
            c.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2026-01-01')"),dict(p=professional,i=self.a,o=occupation))
        with self.assertRaisesRegex(Error,'ACCESS_DENIED'):self.s.authorize(self.db,self.target,self.a)
        before=self.db.execute(text('SELECT to_jsonb(u) FROM usuarios u ORDER BY id')).scalars().all()
        self.create(active=True);self.s.deactivate(self.db,self.target,self.a,actor_id=self.actor)
        self.assertEqual(self.db.execute(text('SELECT to_jsonb(u) FROM usuarios u ORDER BY id')).scalars().all(),before)

    def test_caller_transaction_and_savepoint_failure(self):
        self.create()
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT count(*) FROM usuario_instituicao_acessos')).scalar(),0)
        self.db.rollback();self.assertEqual(self.db.query(Acesso).count(),0)
        original=self.db.flush
        def fail(*a,**k):original(*a,**k);raise RuntimeError('synthetic')
        with patch.object(self.db,'flush',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):self.create()
        self.assertEqual(self.db.query(Acesso).count(),0)

    def test_physical_unique_check_fk_and_restrict(self):
        self.create(active=True)
        bad=[dict(usuario_id=self.target,instituicao_id=self.a,perfil_institucional='SUPORTE'),
             dict(usuario_id=self.target,instituicao_id=self.b,perfil_institucional='ADMIN'),
             dict(usuario_id=999999,instituicao_id=self.b,perfil_institucional='GESTOR')]
        for values in bad:
            with self.assertRaises(IntegrityError):
                with self.db.begin_nested():self.db.add(Acesso(**values));self.db.flush()
        for table,identity in [('usuarios',self.target),('instituicoes',self.a)]:
            with self.assertRaises(IntegrityError):
                with self.db.begin_nested():self.db.execute(text(f'DELETE FROM {table} WHERE id=:id'),{'id':identity})

    def test_unknown_integrity_error_is_not_reuse(self):
        original=self.db.flush
        def fail(*a,**k):
            if any(isinstance(x,Acesso) for x in self.db.new):
                raise IntegrityError('synthetic',{},SimpleNamespace(pgcode='23505',diag=SimpleNamespace(constraint_name='different_unique')))
            return original(*a,**k)
        with patch.object(self.db,'flush',side_effect=fail):
            with self.assertRaises(IntegrityError):self.create()
        self.assertEqual(self.db.query(Acesso).count(),0)

    def test_concurrent_identical_and_conflicting_create(self):
        for institution,profiles in [(self.a,('GESTOR','GESTOR')),(self.b,('GESTOR','SUPORTE'))]:
            barrier=Barrier(2);original=self.s._row
            def coordinated(db,u,i):
                row=original(db,u,i)
                if row is None:barrier.wait(timeout=5)
                return row
            def worker(profile):
                try:
                    with Session(self.engine) as db,db.begin():
                        row=self.create(db=db,profile=profile,institution=institution)
                        return ('ok',row.id)
                except Error as e:return (e.code,None)
            with patch.object(self.s,'_row',side_effect=coordinated),ThreadPoolExecutor(max_workers=2) as pool:
                outcomes=list(pool.map(worker,profiles))
            if profiles[0]==profiles[1]:self.assertEqual(outcomes[0],outcomes[1]);self.assertEqual(outcomes[0][0],'ok')
            else:self.assertCountEqual([x[0] for x in outcomes],['ok','ACCESS_CONFLICT'])
        self.assertEqual(self.db.query(Acesso).count(),2)

    def test_revoke_visible_to_same_session_without_new_token(self):
        self.create(active=True);self.db.commit()
        cached=self.db.get(Acesso,self.db.query(Acesso.id).scalar())
        self.s.authorize(self.db,self.target,self.a)
        with Session(self.engine) as other,other.begin():self.s.deactivate(other,self.target,self.a,actor_id=self.actor)
        self.assertTrue(cached.ativo)  # Prove authorization does not trust cached state.
        with self.assertRaisesRegex(Error,'ACCESS_DENIED'):self.s.authorize(self.db,self.target,self.a)

    def test_not_found_and_read_committed_write_requirement(self):
        with self.assertRaisesRegex(Error,'ACCESS_NOT_FOUND'):self.s.deactivate(self.db,self.target,self.a,actor_id=self.actor)
        with self.assertRaisesRegex(Error,'USER_NOT_FOUND'):self.s.authorize(self.db,999999,self.a)
        self.db.rollback()
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c,c.begin(),Session(c) as db:
            with self.assertRaisesRegex(Error,'READ_COMMITTED_REQUIRED'):self.create(db=db)

    def test_incremental_upgrade_no_backfill_and_conservative_downgrade(self):
        self.db.close()
        with self.engine.begin() as c:
            command.downgrade(config(c),PARENT)
            before=c.execute(text('SELECT to_jsonb(u) FROM usuarios u ORDER BY id')).scalars().all()
            command.upgrade(config(c),HEAD)
            self.assertEqual(c.execute(text('SELECT count(*) FROM usuario_instituicao_acessos')).scalar(),0)
            self.assertEqual(c.execute(text('SELECT to_jsonb(u) FROM usuarios u ORDER BY id')).scalars().all(),before)
        self.create();self.db.commit()
        with self.assertRaisesRegex(RuntimeError,'DOWNGRADE_BLOCKED'):
            with self.engine.begin() as c:command.downgrade(config(c),PARENT)
        with self.engine.connect() as c:self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),HEAD)
