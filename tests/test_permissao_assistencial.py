"""W1B physical and command/lifecycle contracts on disposable PostgreSQL 18."""
import os
import unittest
from datetime import date, datetime, timezone
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import dialect
from pydantic import ValidationError
from app.models.permissao_assistencial import ContextoProfissional, ConcessaoAssistencial, AutoridadeDelegacao
from app.schemas.permissao_assistencial import ContextoProfissionalRecord, ConcessaoAssistencialRecord, AutoridadeDelegacaoRecord
from test_m0_baseline import config

MODELS = (ContextoProfissional, AutoridadeDelegacao, ConcessaoAssistencial)
URL = os.getenv('M0_TEST_POSTGRES_URL')


class StructuralTests(unittest.TestCase):
    def test_head(self):
        scripts = ScriptDirectory.from_config(config())
        self.assertEqual(scripts.get_heads(), ['capacidade_reconciliacao_v1'])
        self.assertEqual(scripts.get_revision('w1b_permissoes_v1').down_revision, 'w1a_contexto_v1')

    def test_no_legacy_or_operational_fields(self):
        for model in MODELS:
            self.assertTrue({'clinica_id', 'ativo', 'pessoa_id'}.isdisjoint(model.__table__.c.keys()))
        self.assertNotIn('permissao_operacoes', ContextoProfissional.metadata.tables)

    def test_schema_scope_and_revocation(self):
        data=dict(id=1,usuario_instituicao_acesso_id=1,instituicao_id=1,contexto_assistencial_id=1,
                  concedido_por_usuario_id=1,concedido_em=datetime.now(timezone.utc),motivo_concessao='Synthetic',
                  capacidade='ASSISTENCIAL_LER',escopo_tipo='CONTEXTO')
        self.assertEqual(ConcessaoAssistencialRecord(**data).capacidade,'ASSISTENCIAL_LER')
        for change in (dict(capacidade='PERMISSAO_DELEGAR'),dict(escopo_tipo='INSTITUICAO'),
                       dict(revogado_em=datetime.now(timezone.utc)),dict(motivo_concessao=' '),dict(id=True),dict(clinica_id=1)):
            with self.subTest(change=change),self.assertRaises(ValidationError):ConcessaoAssistencialRecord(**{**data,**change})
        authority={k:v for k,v in data.items() if k not in ('capacidade','escopo_tipo')}
        authority.update(capacidade_delegavel='ASSISTENCIAL_LER',envelope_tipo='CONTEXTO',origem='RECOVERY',operacao_id=uuid4())
        self.assertEqual(AutoridadeDelegacaoRecord(**authority).origem,'RECOVERY')
        for change in (dict(origem='SYSTEM'),dict(capacidade_delegavel='PERMISSAO_DELEGAR'),dict(operacao_id='bad')):
            with self.subTest(change=change),self.assertRaises(ValidationError):AutoridadeDelegacaoRecord(**{**authority,**change})

    def test_schema_participation(self):
        data=dict(id=1,instituicao_id=1,contexto_assistencial_id=1,profissional_instituicao_id=1,
                  data_inicio=date(2026,1,1),criado_por_usuario_id=1,criado_em=datetime.now(timezone.utc),motivo_criacao='Synthetic')
        ContextoProfissionalRecord(**data)
        for change in (dict(data_fim=date(2025,1,1)),dict(encerrado_por_usuario_id=1),dict(invalidado_em=datetime.now(timezone.utc)),dict(motivo_criacao=' ')):
            with self.subTest(change=change),self.assertRaises(ValidationError):ContextoProfissionalRecord(**{**data,**change})


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL 18')
class PhysicalTests(unittest.TestCase):
    schema_revision = 'w1b_permissoes_v1'  # Historical physical contract.
    @classmethod
    def setUpClass(cls):
        cls.url=make_url(URL)
        if cls.url.host!='127.0.0.1' or cls.url.database!='m0_baseline':raise RuntimeError('Disposable local database required')
        cls.admin=create_engine(cls.url,isolation_level='AUTOCOMMIT');cls.name='w1b_'+uuid4().hex
        with cls.admin.connect() as c:
            if int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000!=18:raise RuntimeError('PG18 required')
            c.exec_driver_sql('CREATE DATABASE '+cls.name)
        cls.engine=create_engine(cls.url.set(database=cls.name),connect_args={'options':'-c lock_timeout=5000 -c statement_timeout=15000'})
        with cls.engine.begin() as c:command.upgrade(config(c), getattr(cls, 'schema_revision', 'head'))

    @classmethod
    def tearDownClass(cls):
        cls.engine.dispose()
        with cls.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+cls.name)
        cls.admin.dispose()

    def setUp(self):
        with self.engine.begin() as c:
            self.actor=c.execute(text("INSERT INTO usuarios(nome,email,senha_hash,ativo) VALUES ('Synthetic',:e,'test',true) RETURNING id"),dict(e=uuid4().hex+'@example.invalid')).scalar()
            patient=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar()
            professional=c.exec_driver_sql("INSERT INTO profissionais(nome) VALUES ('Synthetic') RETURNING id").scalar()
            occupation=c.execute(text("INSERT INTO ocupacoes_profissionais(nome) VALUES (:n) RETURNING id"),dict(n=uuid4().hex)).scalar()
            self.institutions=[];self.contexts=[];self.roots=[];self.links=[]
            for _ in range(2):
                institution=c.exec_driver_sql("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Synthetic','OUTRO') RETURNING id").scalar()
                link=c.execute(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'OUTRO','2020-01-01') RETURNING id"),dict(p=patient,i=institution)).scalar()
                context=c.execute(text("INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,data_fim,criado_por_usuario_id) VALUES (:l,:p,:i,'2020-01-01','2020-12-31',:u) RETURNING id"),dict(l=link,p=patient,i=institution,u=self.actor)).scalar()
                root=c.execute(text("INSERT INTO usuario_instituicao_acessos(usuario_id,instituicao_id,perfil_institucional) VALUES (:u,:i,'PROFISSIONAL') RETURNING id"),dict(u=self.actor,i=institution)).scalar()
                professional_link=c.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2020-01-01') RETURNING id"),dict(p=professional,i=institution,o=occupation)).scalar()
                self.institutions.append(institution);self.contexts.append(context);self.roots.append(root);self.links.append(professional_link)

    def values(self, model, **changes):
        if model is ContextoProfissional:
            data=dict(instituicao_id=self.institutions[0],contexto_assistencial_id=self.contexts[0],profissional_instituicao_id=self.links[0],data_inicio=date(2026,1,1),criado_por_usuario_id=self.actor,motivo_criacao='Synthetic')
        else:
            data=dict(instituicao_id=self.institutions[0],usuario_instituicao_acesso_id=self.roots[0],contexto_assistencial_id=self.contexts[0],concedido_por_usuario_id=self.actor,motivo_concessao='Synthetic')
            if model is AutoridadeDelegacao:data.update(capacidade_delegavel='ASSISTENCIAL_LER',envelope_tipo='CONTEXTO',origem='BOOTSTRAP',operacao_id=uuid4())
            else:data.update(capacidade='ASSISTENCIAL_LER',escopo_tipo='CONTEXTO')
        return {**data,**changes}

    def insert(self,c,model,**changes):
        return c.execute(model.__table__.insert().values(**self.values(model,**changes)).returning(model.id)).scalar()

    def reject(self,model,code,**changes):
        with self.assertRaises(IntegrityError) as raised:
            with self.engine.begin() as c:self.insert(c,model,**changes)
        self.assertEqual(raised.exception.orig.pgcode,code)

    def test_exact_model_catalogue(self):
        i=inspect(self.engine)
        for model in MODELS:
            table=model.__table__;cols=i.get_columns(table.name)
            self.assertEqual({c['name'] for c in cols},set(table.c.keys()))
            for col in cols:
                self.assertEqual(col['nullable'],table.c[col['name']].nullable)
                self.assertEqual(str(col['type'].compile(dialect=dialect())),str(table.c[col['name']].type.compile(dialect=dialect())))
                if col['name']=='id':self.assertIn('identity',col)
                elif col['name'] in ('criado_em','concedido_em'):self.assertEqual(col['default'],'now()')
                else:self.assertIsNone(col['default'])
            self.assertEqual(i.get_pk_constraint(table.name)['constrained_columns'],['id'])
            expected={(tuple(c.parent.name for c in fk.elements),tuple(c.target_fullname for c in fk.elements)) for fk in table.foreign_key_constraints}
            actual={(tuple(fk['constrained_columns']),tuple(fk['referred_table']+'.'+col for col in fk['referred_columns'])) for fk in i.get_foreign_keys(table.name)}
            self.assertEqual(actual,expected)
            self.assertTrue(all(fk['options']['ondelete']=='RESTRICT' for fk in i.get_foreign_keys(table.name)))
            self.assertEqual({c['name'] for c in i.get_check_constraints(table.name)}, {c.name for c in table.constraints if c.__class__.__name__=='CheckConstraint'})
            physical={x['name']:x for x in i.get_indexes(table.name)}
            for idx in table.indexes:
                self.assertIn(idx.name,physical)
                self.assertEqual(physical[idx.name]['unique'],bool(idx.unique))
                self.assertEqual(physical[idx.name]['column_names'],[col.name for col in idx.columns])
                if idx.unique:self.assertIn('revogado_em IS NULL',str(physical[idx.name]['dialect_options']['postgresql_where']))
        with self.engine.connect() as c:
            d=c.exec_driver_sql("SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='ex_participacao_vigencia'").scalar()
            self.assertIn('&&',d);self.assertIn('invalidado_em IS NULL',d)

    def test_support_uniques(self):
        i=inspect(self.engine)
        for name in ('usuario_instituicao_acessos','contextos_assistenciais','profissional_instituicoes'):
            self.assertIn(('id','instituicao_id'),{tuple(x['column_names']) for x in i.get_unique_constraints(name)})

    def test_participation_valid_historical_context(self):
        with self.engine.begin() as c:
            self.insert(c,ContextoProfissional)
            self.assertEqual(c.execute(text('SELECT data_fim FROM contextos_assistenciais WHERE id=:id'),dict(id=self.contexts[0])).scalar(),date(2020,12,31))

    def test_participation_institution_fks(self):
        for changes in (dict(contexto_assistencial_id=self.contexts[1]),dict(profissional_instituicao_id=self.links[1]),dict(instituicao_id=self.institutions[1])):
            with self.subTest(changes=changes):self.reject(ContextoProfissional,'23503',**changes)

    def test_participation_period_and_events(self):
        for changes in (dict(data_fim=date(2025,1,1)),dict(encerrado_por_usuario_id=self.actor),dict(invalidado_em=datetime.now(timezone.utc)),dict(motivo_criacao=' '),dict(criado_por_usuario_id=2147483647)):
            with self.subTest(changes=changes):self.reject(ContextoProfissional,'23503' if 'criado_por_usuario_id' in changes else '23514',**changes)
        now=datetime.now(timezone.utc)
        with self.engine.begin() as c:
            self.insert(c,ContextoProfissional,data_fim=date(2026,1,31),encerrado_por_usuario_id=self.actor,encerrado_em=now,motivo_encerramento='Synthetic')
            self.insert(c,ContextoProfissional,data_inicio=date(2026,2,1),invalidado_por_usuario_id=self.actor,invalidado_em=now,motivo_invalidacao='Synthetic')
            self.insert(c,ContextoProfissional,data_inicio=date(2026,2,1))

    def test_participation_inclusive_overlap(self):
        with self.engine.begin() as c:self.insert(c,ContextoProfissional,data_fim=date(2026,1,31))
        self.reject(ContextoProfissional,'23P01',data_inicio=date(2026,1,31))
        with self.engine.begin() as c:self.insert(c,ContextoProfissional,data_inicio=date(2026,2,1))

    def test_grant_scopes(self):
        for changes in (dict(capacidade='UNKNOWN'),dict(capacidade='PERMISSAO_DELEGAR'),dict(escopo_tipo='UNKNOWN'),dict(contexto_assistencial_id=None),dict(motivo_concessao=' ')):
            with self.subTest(changes=changes):self.reject(ConcessaoAssistencial,'23514',**changes)
        for capability in ('ASSISTENCIAL_LER','ASSISTENCIAL_REGISTRAR'):
            self.reject(ConcessaoAssistencial,'23514',capacidade=capability,escopo_tipo='INSTITUICAO',contexto_assistencial_id=None)
        with self.engine.begin() as c:
            for capability in ('ASSISTENCIAL_LER','ASSISTENCIAL_REGISTRAR','CONTEXTO_ADMINISTRAR'):self.insert(c,ConcessaoAssistencial,capacidade=capability)
            self.insert(c,ConcessaoAssistencial,capacidade='CONTEXTO_ADMINISTRAR',escopo_tipo='INSTITUICAO',contexto_assistencial_id=None)

    def test_permission_cross_institution(self):
        for model in (ConcessaoAssistencial,AutoridadeDelegacao):
            for changes in (dict(contexto_assistencial_id=self.contexts[1]),dict(usuario_instituicao_acesso_id=self.roots[1]),dict(instituicao_id=self.institutions[1]),dict(usuario_instituicao_acesso_id=2147483647)):
                with self.subTest(model=model,changes=changes):self.reject(model,'23503',**changes)
        with self.engine.begin() as c:
            authority=self.insert(c,AutoridadeDelegacao,instituicao_id=self.institutions[1],usuario_instituicao_acesso_id=self.roots[1],contexto_assistencial_id=self.contexts[1])
        self.reject(ConcessaoAssistencial,'23503',autoridade_delegacao_id=authority)

    def test_authority_origins_and_capabilities(self):
        for changes in (dict(origem='SYSTEM'),dict(capacidade_delegavel='PERMISSAO_DELEGAR'),dict(envelope_tipo='UNKNOWN'),dict(envelope_tipo='INSTITUICAO')):
            with self.subTest(changes=changes):self.reject(AutoridadeDelegacao,'23514',**changes)
        self.reject(AutoridadeDelegacao,'23502',operacao_id=None)
        with self.engine.begin() as c:
            self.insert(c,AutoridadeDelegacao,origem='BOOTSTRAP')
            self.insert(c,AutoridadeDelegacao,origem='RECOVERY',envelope_tipo='INSTITUICAO',contexto_assistencial_id=None)

    def test_revocation_atomicity_and_new_cycles(self):
        for model in (ConcessaoAssistencial,AutoridadeDelegacao):
            for changes in (dict(revogado_em=datetime.now(timezone.utc)),dict(revogado_por_usuario_id=self.actor),dict(motivo_revogacao=' '),dict(revogacao_origem='RAIZ_DESATIVADA')):
                with self.subTest(model=model,changes=changes):self.reject(model,'23514',**changes)
            with self.engine.begin() as c:identity=self.insert(c,model)
            self.reject(model,'23505')
            with self.engine.begin() as c:
                c.execute(model.__table__.update().where(model.id==identity).values(revogado_por_usuario_id=self.actor,revogado_em=datetime.now(timezone.utc),motivo_revogacao='Synthetic',revogacao_origem='RAIZ_DESATIVADA'))
                self.assertNotEqual(self.insert(c,model),identity)

    def test_institutional_partial_unique(self):
        for model,kwargs in ((AutoridadeDelegacao,dict(envelope_tipo='INSTITUICAO',contexto_assistencial_id=None)),(ConcessaoAssistencial,dict(capacidade='CONTEXTO_ADMINISTRAR',escopo_tipo='INSTITUICAO',contexto_assistencial_id=None))):
            with self.engine.begin() as c:self.insert(c,model,**kwargs)
            self.reject(model,'23505',**kwargs)

    def test_restrict_and_rollback(self):
        with self.engine.begin() as c:
            authority=self.insert(c,AutoridadeDelegacao)
            self.insert(c,ConcessaoAssistencial,autoridade_delegacao_id=authority)
            self.insert(c,ContextoProfissional)
        for table,identity in (('usuario_instituicao_acessos',self.roots[0]),('contextos_assistenciais',self.contexts[0]),('profissional_instituicoes',self.links[0]),('autoridades_delegacao',authority)):
            with self.subTest(table=table),self.assertRaises(IntegrityError):
                with self.engine.begin() as c:c.execute(text('DELETE FROM '+table+' WHERE id=:id'),dict(id=identity))
        with self.engine.connect() as c:
            tx=c.begin();identity=self.insert(c,AutoridadeDelegacao,capacidade_delegavel='CONTEXTO_ADMINISTRAR');tx.rollback()
            self.assertEqual(c.execute(text('SELECT count(*) FROM autoridades_delegacao WHERE id=:id'),dict(id=identity)).scalar(),0)

    def race(self,model,sqlstate):
        # Keep both transactions live, but insert the first tuple before the
        # contender. Simultaneous GiST insertion can deadlock before PostgreSQL
        # reports the exclusion violation this physical test is meant to prove.
        inserted=Event();attempting=Event();contender=[]
        def first():
            with self.engine.begin() as c:
                self.insert(c,model);inserted.set()
                if not attempting.wait(10):raise RuntimeError('Missing contender')
                import time
                until=time.monotonic()+4
                blocked=False
                while time.monotonic()<until:
                    blocked=c.execute(text('SELECT EXISTS(SELECT FROM pg_locks WHERE pid=:pid AND NOT granted)'),dict(pid=contender[0])).scalar()
                    if blocked:break
                    time.sleep(.01)
                self.assertTrue(blocked)
            return 'persisted'
        def second():
            if not inserted.wait(10):raise RuntimeError('Missing first insert')
            try:
                with self.engine.begin() as c:
                    contender.append(c.exec_driver_sql('SELECT pg_backend_pid()').scalar())
                    attempting.set();self.insert(c,model)
                return 'persisted'
            except IntegrityError as exc:return exc.orig.pgcode
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(first);b=pool.submit(second)
            results=[a.result(timeout=15),b.result(timeout=15)]
        self.assertCountEqual(results,['persisted',sqlstate])

    def test_concurrent_participation(self):self.race(ContextoProfissional,'23P01')
    def test_concurrent_grant(self):self.race(ConcessaoAssistencial,'23505')
    def test_concurrent_authority(self):self.race(AutoridadeDelegacao,'23505')

    def test_incremental_roundtrip_no_backfill(self):
        name='w1b_roundtrip_'+uuid4().hex
        with self.admin.connect() as c:c.exec_driver_sql('CREATE DATABASE '+name)
        engine=create_engine(self.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'w1a_contexto_v1')
                patient=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic legacy') RETURNING id").scalar()
                before=c.exec_driver_sql('SELECT row_to_json(p) FROM pacientes p').all()
                command.upgrade(config(c),'w1b_permissoes_v1')
                self.assertEqual(c.exec_driver_sql('SELECT row_to_json(p) FROM pacientes p').all(),before)
                for model in MODELS:self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM '+model.__tablename__).scalar(),0)
                self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM pessoas').scalar(),0)
                command.downgrade(config(c),'w1a_contexto_v1')
                for model in MODELS:self.assertNotIn(model.__tablename__,inspect(c).get_table_names())
                self.assertTrue(c.exec_driver_sql("SELECT EXISTS(SELECT FROM pg_extension WHERE extname='btree_gist')").scalar())
                command.upgrade(config(c),'head')
                self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'capacidade_reconciliacao_v1')
        finally:
            engine.dispose()
            with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+name)

    def test_history_blocks_downgrade_for_each_table(self):
        for model in MODELS:
            with self.subTest(model=model),self.engine.connect() as c:
                tx=c.begin()
                try:
                    self.insert(c,model)
                    with self.assertRaisesRegex(RuntimeError,'W1B_DOWNGRADE_BLOCKED_HISTORY'):command.downgrade(config(c),'w1a_contexto_v1')
                finally:tx.rollback()

    def test_downgrade_requires_read_committed(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c,c.begin():
            with self.assertRaisesRegex(RuntimeError,'W1B_READ_COMMITTED_REQUIRED'):command.downgrade(config(c),'w1a_contexto_v1')


# W1B-C exercises commands against the current schema, without changing the
# isolated physical/migration contract tests above.
from sqlalchemy.orm import Session
from unittest.mock import patch
from threading import Event
from app.models.usuario import Usuario
from app.models.pessoa import Pessoa
from app.models.autorizacao_institucional import UsuarioInstituicaoAcesso as Root
from app.services.permissao_assistencial import PermissaoAssistencialService as Commands, PermissaoAssistencialErro as CommandError
from app.services.autorizacao_institucional import AutorizacaoInstitucionalService as Roots


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL 18')
class CommandTests(unittest.TestCase):
    schema_revision = 'head'  # Current service uses the current schema.
    setUpClass = classmethod(PhysicalTests.setUpClass.__func__)
    tearDownClass = classmethod(PhysicalTests.tearDownClass.__func__)

    def setUp(self):
        PhysicalTests.setUp(self)
        self.institution = self.institutions[0]
        self.context = self.contexts[0]
        self.s = Commands()
        with self.engine.begin() as c:
            person = c.exec_driver_sql("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic') RETURNING id").scalar()
            c.execute(text('UPDATE usuarios SET pessoa_id=:p WHERE id=:u'), dict(p=person,u=self.actor))
            c.execute(text('UPDATE profissionais SET pessoa_id=:p WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:l)'),dict(p=person,l=self.links[0]))
            c.execute(text('UPDATE usuario_instituicao_acessos SET ativo=true WHERE usuario_id=:u'),dict(u=self.actor))
            self.platform_admin = c.execute(text("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo) VALUES ('Synthetic',:e,'test','ADMIN',true) RETURNING id"),dict(e=uuid4().hex+'@example.invalid')).scalar()
            person = c.exec_driver_sql("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic target') RETURNING id").scalar()
            self.target = c.execute(text("INSERT INTO usuarios(nome,email,senha_hash,perfil,ativo,pessoa_id) VALUES ('Synthetic',:e,'test','SUPORTE',true,:p) RETURNING id"),dict(e=uuid4().hex+'@example.invalid',p=person)).scalar()
            self.target_root = c.execute(text("INSERT INTO usuario_instituicao_acessos(usuario_id,instituicao_id,perfil_institucional,ativo) VALUES (:u,:i,'SUPORTE',true) RETURNING id"),dict(u=self.target,i=self.institution)).scalar()
        self.db = Session(self.engine)

    def tearDown(self):
        self.db.rollback()
        self.db.close()

    def nomination(self, **changes):
        return {**dict(instituicao_id=self.institution,usuario_instituicao_acesso_id=self.roots[0],
                      envelopes=[dict(capacidade_delegavel='ASSISTENCIAL_LER',envelope_tipo='CONTEXTO',contexto_assistencial_id=self.context)],
                      motivo='Synthetic nomination'),**changes}

    def grant_data(self, **changes):
        return {**dict(instituicao_id=self.institution,usuario_instituicao_acesso_id=self.target_root,
                      capacidade='ASSISTENCIAL_LER',escopo_tipo='CONTEXTO',contexto_assistencial_id=self.context,
                      motivo='Synthetic grant'),**changes}

    def revoke_data(self, identity, **changes):
        return {**dict(instituicao_id=self.institution,id=identity,motivo='Synthetic revocation'),**changes}

    def bootstrap(self, **changes):
        return self.s.bootstrap(self.db,self.nomination(**changes),actor_id=self.platform_admin)

    def grant(self, **changes):
        return self.s.grant(self.db,self.grant_data(**changes),actor_id=self.actor)

    def authorities(self):
        return self.db.query(AutoridadeDelegacao).filter_by(instituicao_id=self.institution)

    def grants(self):
        return self.db.query(ConcessaoAssistencial).filter_by(instituicao_id=self.institution)

    def participation_data(self, **changes):
        return {**dict(instituicao_id=self.institution,contexto_assistencial_id=self.context,
                      profissional_instituicao_id=self.links[0],data_inicio=date.today(),motivo='Synthetic participation'),**changes}

    def allow_participation(self):
        self.db.add(ConcessaoAssistencial(instituicao_id=self.institution,usuario_instituicao_acesso_id=self.roots[0],
            capacidade='CONTEXTO_ADMINISTRAR',escopo_tipo='CONTEXTO',contexto_assistencial_id=self.context,
            concedido_por_usuario_id=self.platform_admin,motivo_concessao='Existing explicit grant'))
        self.db.flush()

    def event(self, row):
        return (row.revogado_por_usuario_id,row.revogado_em,row.motivo_revogacao,row.revogacao_origem)

    def test_participation_historical_context_close_and_invalidate(self):
        self.allow_participation()
        before = self.db.execute(text('SELECT row_to_json(c) FROM contextos_assistenciais c WHERE id=:i'),dict(i=self.context)).scalar()
        row = self.s.create_participation(self.db,self.participation_data(),actor_id=self.actor)
        self.assertEqual(self.grants().count(),1)  # Only the explicit administration grant.
        self.assertEqual(self.db.execute(text('SELECT row_to_json(c) FROM contextos_assistenciais c WHERE id=:i'),dict(i=self.context)).scalar(),before)
        end = self.revoke_data(row.id,data_fim=date.today())
        self.s.close_participation(self.db,end,actor_id=self.actor)
        original = (row.encerrado_em,row.encerrado_por_usuario_id,row.motivo_encerramento)
        self.s.close_participation(self.db,{**end,'motivo':'Other'},actor_id=self.actor)
        self.assertEqual((row.encerrado_em,row.encerrado_por_usuario_id,row.motivo_encerramento),original)
        with self.assertRaisesRegex(CommandError,'ALREADY_CLOSED'):
            self.s.close_participation(self.db,{**end,'data_fim':date(2099,1,1)},actor_id=self.actor)
        self.s.invalidate_participation(self.db,self.revoke_data(row.id),actor_id=self.actor)
        event = (row.invalidado_em,row.motivo_invalidacao)
        self.s.invalidate_participation(self.db,self.revoke_data(row.id,motivo='Other'),actor_id=self.actor)
        self.assertEqual((row.invalidado_em,row.motivo_invalidacao),event)
        with self.assertRaisesRegex(CommandError,'INVALIDATED'):
            self.s.close_participation(self.db,end,actor_id=self.actor)
        new = self.s.create_participation(self.db,self.participation_data(),actor_id=self.actor)
        self.assertNotEqual(new.id,row.id)

    def test_participation_no_profile_bypass_or_cross_institution(self):
        for actor in (self.actor,self.platform_admin):
            with self.assertRaises(CommandError):
                self.s.create_participation(self.db,self.participation_data(),actor_id=actor)
        self.allow_participation()
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):
            self.s.create_participation(self.db,self.participation_data(profissional_instituicao_id=self.links[1]),actor_id=self.actor)
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):
            self.s.create_participation(self.db,self.participation_data(contexto_assistencial_id=self.contexts[1]),actor_id=self.actor)

    def test_participation_person_link_and_period_validation(self):
        self.allow_participation()
        for sql,code in [
            ('UPDATE profissionais SET pessoa_id=NULL WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:i)','VALID_PERSON_REQUIRED'),
            ('UPDATE profissionais SET ativo=false WHERE id=(SELECT profissional_id FROM profissional_instituicoes WHERE id=:i)','PROFESSIONAL_INACTIVE'),
            ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i','PROFESSIONAL_LINK_INELIGIBLE'),
            ("UPDATE profissional_instituicoes SET data_fim='2020-12-31' WHERE id=:i",'PROFESSIONAL_LINK_INELIGIBLE')]:
            with self.subTest(code=code):
                nested=self.db.begin_nested()
                self.db.execute(text(sql),dict(i=self.links[0]))
                with self.assertRaisesRegex(CommandError,code):
                    self.s.create_participation(self.db,self.participation_data(),actor_id=self.actor)
                nested.rollback()
        with self.assertRaises(ValidationError):
            self.s.create_participation(self.db,self.participation_data(data_fim=date(2000,1,1)),actor_id=self.actor)
        self.s.create_participation(self.db,self.participation_data(),actor_id=self.actor)
        with self.assertRaisesRegex(CommandError,'PARTICIPATION_PERIOD_CONFLICT'):
            self.s.create_participation(self.db,self.participation_data(),actor_id=self.actor)

    def test_grant_lifecycle_idempotence_and_no_participation(self):
        authority=self.bootstrap()[0]
        row=self.grant()
        first=(row.id,row.concedido_por_usuario_id,row.concedido_em,row.motivo_concessao,row.autoridade_delegacao_id)
        again=self.grant(motivo='Other')
        self.assertEqual((again.id,again.concedido_por_usuario_id,again.concedido_em,again.motivo_concessao,again.autoridade_delegacao_id),first)
        self.assertEqual(row.autoridade_delegacao_id,authority.id)
        self.assertEqual(self.db.query(ContextoProfissional).filter_by(instituicao_id=self.institution).count(),0)
        self.s.revoke(self.db,self.revoke_data(row.id),actor_id=self.actor)
        event=self.event(row)
        self.s.revoke(self.db,self.revoke_data(row.id,motivo='Other'),actor_id=self.actor)
        self.assertEqual(self.event(row),event)
        new=self.grant()
        self.assertNotEqual(new.id,row.id)
        self.assertEqual(self.grants().filter_by(revogado_em=None).count(),1)

    def test_grant_authority_envelope_and_self_denials(self):
        with self.assertRaisesRegex(CommandError,'AUTHORITY_DENIED'):self.grant()
        self.bootstrap()
        with self.assertRaisesRegex(CommandError,'AUTHORITY_DENIED'):self.grant(capacidade='ASSISTENCIAL_REGISTRAR')
        with self.assertRaisesRegex(CommandError,'SELF_GRANT_DENIED'):self.grant(usuario_instituicao_acesso_id=self.roots[0])
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):self.grant(contexto_assistencial_id=self.contexts[1])
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):self.grant(usuario_instituicao_acesso_id=self.roots[1])
        with self.assertRaises(ValidationError):self.grant(escopo_tipo='INSTITUICAO',contexto_assistencial_id=None)
        with self.assertRaises(CommandError):self.s.grant(self.db,self.grant_data(),actor_id=self.platform_admin)

    def test_grant_target_and_issuer_eligibility(self):
        self.bootstrap()
        cases=[('UPDATE usuario_instituicao_acessos SET ativo=false WHERE id=:i',self.target_root,'ROOT_INACTIVE'),
               ('UPDATE usuarios SET ativo=false WHERE id=:i',self.target,'USER_INACTIVE'),
               ('UPDATE usuarios SET pessoa_id=NULL WHERE id=:i',self.target,'VALID_PERSON_REQUIRED'),
               ('UPDATE pessoas SET ativo=false WHERE id=(SELECT pessoa_id FROM usuarios WHERE id=:i)',self.target,'VALID_PERSON_REQUIRED'),
               ('UPDATE usuario_instituicao_acessos SET ativo=false WHERE id=:i',self.roots[0],'AUTHORITY_DENIED'),
               ('UPDATE instituicoes SET ativo=false WHERE id=:i',self.institution,'INSTITUTION_INACTIVE'),
               ('UPDATE contextos_assistenciais SET ativo=false WHERE id=:i',self.context,'CONTEXT_INVALIDATED')]
        for sql,identity,code in cases:
            with self.subTest(code=code):
                nested=self.db.begin_nested();self.db.execute(text(sql),dict(i=identity))
                with self.assertRaisesRegex(CommandError,code):self.grant()
                nested.rollback()
        self.assertEqual(self.grants().count(),0)

    def test_bootstrap_atomic_envelopes_and_no_clinical_grant(self):
        envelopes=[dict(capacidade_delegavel=c,envelope_tipo='INSTITUICAO') for c in ('ASSISTENCIAL_LER','CONTEXTO_ADMINISTRAR')]
        rows=self.bootstrap(envelopes=envelopes)
        self.assertEqual(len(rows),2)
        self.assertEqual(len({r.operacao_id for r in rows}),1)
        self.assertTrue(all(r.origem=='BOOTSTRAP' and r.concedido_por_usuario_id==self.platform_admin for r in rows))
        self.assertEqual(self.grants().count(),0)
        with self.assertRaisesRegex(CommandError,'BOOTSTRAP_ALREADY_PERFORMED'):self.bootstrap()
        for row in rows:self.s.revoke_authority(self.db,self.revoke_data(row.id),actor_id=self.platform_admin)
        with self.assertRaisesRegex(CommandError,'BOOTSTRAP_ALREADY_PERFORMED'):self.bootstrap()
        self.assertEqual(self.authorities().count(),2)

    def test_bootstrap_admin_only_and_no_subdelegation(self):
        for method in (self.s.bootstrap,self.s.recovery):
            with self.assertRaisesRegex(CommandError,'ADMIN_REQUIRED'):
                method(self.db,self.nomination(),actor_id=self.actor)
        with self.assertRaisesRegex(CommandError,'INITIAL_BOOTSTRAP_REQUIRED'):
            self.s.recovery(self.db,self.nomination(),actor_id=self.platform_admin)
        self.db.execute(text('UPDATE usuarios SET ativo=false WHERE id=:i'),dict(i=self.platform_admin))
        with self.assertRaisesRegex(CommandError,'ADMIN_REQUIRED'):self.bootstrap()

    def test_bootstrap_injected_mid_flush_rolls_back_every_envelope(self):
        original=self.db.flush
        seen=[]
        def fail(*a,**kw):
            if any(isinstance(r,AutoridadeDelegacao) for r in self.db.new):
                seen.append(1)
                if len(seen)==2:raise RuntimeError('synthetic mid-operation')
            return original(*a,**kw)
        envelopes=[dict(capacidade_delegavel=c,envelope_tipo='INSTITUICAO') for c in ('ASSISTENCIAL_LER','CONTEXTO_ADMINISTRAR')]
        with patch.object(self.db,'flush',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):self.bootstrap(envelopes=envelopes)
        self.assertEqual(len(seen),2)
        self.assertEqual(self.authorities().count(),0)
        self.assertEqual(self.grants().count(),0)

    def test_recovery_composite_any_eligible_part_denies_all(self):
        self.bootstrap()
        envelopes=[dict(capacidade_delegavel=c,envelope_tipo='CONTEXTO',contexto_assistencial_id=self.context)
                   for c in ('ASSISTENCIAL_REGISTRAR','ASSISTENCIAL_LER')]
        with self.assertRaisesRegex(CommandError,'ELIGIBLE_AUTHORITY_EXISTS'):
            self.s.recovery(self.db,self.nomination(envelopes=envelopes),actor_id=self.platform_admin)
        self.assertEqual(self.authorities().count(),1)
        with self.assertRaisesRegex(CommandError,'ELIGIBLE_AUTHORITY_EXISTS'):
            self.s.recovery(self.db,self.nomination(envelopes=[dict(capacidade_delegavel='ASSISTENCIAL_LER',envelope_tipo='INSTITUICAO')]),actor_id=self.platform_admin)

    def test_recovery_after_terminal_revocation_preserves_old_events(self):
        old=self.bootstrap()[0];grant=self.grant()
        self.s.revoke(self.db,self.revoke_data(grant.id),actor_id=self.actor)
        self.s.revoke_authority(self.db,self.revoke_data(old.id),actor_id=self.platform_admin)
        events=(self.event(old),self.event(grant))
        rows=self.s.recovery(self.db,self.nomination(),actor_id=self.platform_admin)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0].origem,'RECOVERY')
        self.assertNotEqual(rows[0].id,old.id)
        self.assertEqual((self.event(old),self.event(grant)),events)
        self.assertEqual(self.grants().count(),1)
        self.assertIsNotNone(grant.revogado_em)

    def test_recovery_ignores_ineligible_root_and_remains_atomic(self):
        old=self.bootstrap()[0]
        Roots().deactivate(self.db,self.actor,self.institution,actor_id=self.platform_admin)
        rows=self.s.recovery(self.db,self.nomination(usuario_instituicao_acesso_id=self.target_root),actor_id=self.platform_admin)
        self.assertEqual(rows[0].origem,'RECOVERY')
        self.assertIsNotNone(old.revogado_em)
        self.assertEqual(self.grants().count(),0)

    def test_authority_revoke_admin_only_terminal_no_cascade(self):
        authority=self.bootstrap()[0];grant=self.grant()
        for actor in (self.actor,self.target):
            with self.assertRaisesRegex(CommandError,'ADMIN_REQUIRED'):
                self.s.revoke_authority(self.db,self.revoke_data(authority.id),actor_id=actor)
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):
            self.s.revoke_authority(self.db,self.revoke_data(authority.id,instituicao_id=self.institutions[1]),actor_id=self.platform_admin)
        with self.assertRaises(ValidationError):
            self.s.revoke_authority(self.db,self.revoke_data(authority.id,motivo=' '),actor_id=self.platform_admin)
        self.s.revoke_authority(self.db,self.revoke_data(authority.id),actor_id=self.platform_admin)
        event=self.event(authority)
        self.s.revoke_authority(self.db,self.revoke_data(authority.id,motivo='Other'),actor_id=self.platform_admin)
        self.assertEqual(self.event(authority),event)
        self.assertIsNone(grant.revogado_em)
        self.assertTrue(self.db.get(Root,self.roots[0]).ativo)
        self.assertEqual(self.authorities().count(),1)
        self.assertEqual(self.grants().count(),1)
        with self.assertRaisesRegex(CommandError,'AUTHORITY_DENIED'):self.grant()

    def test_authority_revoke_inactive_admin_and_self_owner_denied(self):
        authority=self.bootstrap()[0]
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:i"),dict(i=self.actor))
        with self.assertRaisesRegex(CommandError,'SELF_AUTHORITY_REVOCATION_DENIED'):
            self.s.revoke_authority(self.db,self.revoke_data(authority.id),actor_id=self.actor)
        self.db.execute(text('UPDATE usuarios SET ativo=false WHERE id=:i'),dict(i=self.platform_admin))
        with self.assertRaisesRegex(CommandError,'ADMIN_REQUIRED'):
            self.s.revoke_authority(self.db,self.revoke_data(authority.id),actor_id=self.platform_admin)
        self.assertIsNone(authority.revogado_em)

    def test_root_deactivation_revokes_only_recipient_and_reactivate_never_resurrects(self):
        authority=self.bootstrap()[0];third_party=self.grant()
        # Existing independent grant received by the authority's root.
        own=ConcessaoAssistencial(instituicao_id=self.institution,usuario_instituicao_acesso_id=self.roots[0],
            capacidade='CONTEXTO_ADMINISTRAR',escopo_tipo='INSTITUICAO',concedido_por_usuario_id=self.platform_admin,
            motivo_concessao='Synthetic existing')
        self.db.add(own);self.db.flush()
        roots=Roots()
        roots.deactivate(self.db,self.actor,self.institution,actor_id=self.platform_admin)
        self.assertEqual(self.event(own),self.event(authority))
        self.assertEqual(own.revogacao_origem,'RAIZ_DESATIVADA')
        self.assertEqual(own.revogado_por_usuario_id,self.platform_admin)
        self.assertIsNone(third_party.revogado_em)
        event=self.event(authority)
        roots.activate(self.db,self.actor,self.institution,actor_id=self.platform_admin)
        self.assertTrue(self.db.get(Root,self.roots[0]).ativo)
        self.assertEqual(self.event(authority),event);self.assertEqual(self.event(own),event)
        with self.assertRaisesRegex(CommandError,'AUTHORITY_DENIED'):self.grant()
        self.assertEqual(self.authorities().count(),1)

    def test_root_failure_rolls_back_grants_authorities_and_root(self):
        authority=self.bootstrap()[0];grant=self.grant()
        # Put another eligible authority on the recipient with a different capability.
        recipient=self.s.recovery(self.db,self.nomination(usuario_instituicao_acesso_id=self.target_root,
            envelopes=[dict(capacidade_delegavel='CONTEXTO_ADMINISTRAR',envelope_tipo='INSTITUICAO')]),actor_id=self.platform_admin)[0]
        original=self.db.flush
        def fail(*a,**kw):
            if any(isinstance(r,AutoridadeDelegacao) and r.revogado_em is not None for r in self.db.dirty):
                raise RuntimeError('synthetic authority failure')
            return original(*a,**kw)
        with patch.object(self.db,'flush',side_effect=fail):
            with self.assertRaisesRegex(RuntimeError,'synthetic'):
                Roots().deactivate(self.db,self.target,self.institution,actor_id=self.platform_admin)
        self.db.expire_all()
        self.assertTrue(self.db.get(Root,self.target_root).ativo)
        self.assertIsNone(grant.revogado_em);self.assertIsNone(recipient.revogado_em)
        self.assertIsNone(authority.revogado_em)

    def test_caller_owns_transaction_clean_session_and_no_unknown_integrity_reuse(self):
        self.bootstrap()
        with patch.object(self.db,'commit',side_effect=AssertionError('Service must not commit')):
            self.grant()
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM concessoes_assistenciais WHERE instituicao_id=:i'),dict(i=self.institution)).scalar(),0)
        self.db.rollback()
        self.assertEqual(self.grants().count(),0);self.assertEqual(self.authorities().count(),0)
        self.bootstrap()
        original=self.db.flush
        def fail(*a,**kw):
            if any(isinstance(r,ConcessaoAssistencial) for r in self.db.new):
                raise IntegrityError('synthetic',{},RuntimeError('unknown constraint'))
            return original(*a,**kw)
        with patch.object(self.db,'flush',side_effect=fail),self.assertRaises(IntegrityError):self.grant()
        self.assertEqual(self.grants().count(),0)
        self.db.get(Usuario,self.actor).nome='Dirty'
        with self.assertRaisesRegex(CommandError,'CLEAN_SESSION_REQUIRED'):self.grant()

    def test_read_committed_and_actor_payload_rejection(self):
        with self.engine.connect().execution_options(isolation_level='REPEATABLE READ') as c,c.begin(),Session(c) as db:
            with self.assertRaisesRegex(CommandError,'READ_COMMITTED_REQUIRED'):
                self.s.bootstrap(db,self.nomination(),actor_id=self.platform_admin)
        for key in ('actor_id','ator_usuario_id','clinica_id'):
            with self.assertRaises(ValidationError):self.bootstrap(**{key:self.platform_admin})
        with self.assertRaises(ValidationError):self.grant(capacidade='PERMISSAO_DELEGAR')

    def race(self, functions):
        self.db.commit()
        barrier=Barrier(2)
        def worker(fn):
            try:
                with Session(self.engine) as db,db.begin():
                    barrier.wait(timeout=10)
                    result=fn(db)
                    return ('ok',result.id if hasattr(result,'id') else result[0].id)
            except CommandError as exc:return (exc.code,None)
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(worker,functions))

    def test_concurrent_bootstrap_only_first(self):
        fn=lambda db:self.s.bootstrap(db,self.nomination(),actor_id=self.platform_admin)
        results=self.race([fn,fn])
        self.assertCountEqual([r[0] for r in results],['ok','BOOTSTRAP_ALREADY_PERFORMED'])
        self.assertEqual(self.authorities().count(),1)

    def test_concurrent_recovery_only_first(self):
        row=self.bootstrap()[0]
        self.s.revoke_authority(self.db,self.revoke_data(row.id),actor_id=self.platform_admin)
        fn=lambda db:self.s.recovery(db,self.nomination(),actor_id=self.platform_admin)
        results=self.race([fn,fn])
        self.assertCountEqual([r[0] for r in results],['ok','ELIGIBLE_AUTHORITY_EXISTS'])
        self.assertEqual(self.authorities().filter_by(revogado_em=None).count(),1)

    def test_concurrent_grant_idempotent(self):
        self.bootstrap()
        fn=lambda db:self.s.grant(db,self.grant_data(),actor_id=self.actor)
        results=self.race([fn,fn])
        self.assertEqual(results[0],results[1]);self.assertEqual(results[0][0],'ok')
        self.assertEqual(self.grants().filter_by(revogado_em=None).count(),1)

    def test_concurrent_revoke_and_grant(self):
        self.bootstrap();row=self.grant();identity=row.id
        results=self.race([lambda db:self.s.revoke(db,self.revoke_data(identity),actor_id=self.actor),
                           lambda db:self.s.grant(db,self.grant_data(),actor_id=self.actor)])
        self.assertTrue(all(r[0]=='ok' for r in results))
        self.db.expire_all()
        self.assertIsNotNone(self.db.get(ConcessaoAssistencial,identity).revogado_em)
        self.assertLessEqual(self.grants().filter_by(revogado_em=None).count(),1)

    def ordered_root_race(self, grant_first):
        self.bootstrap();self.db.commit()
        first_done=Event();second_attempt=Event()
        def action(db, grant):
            if grant:return self.s.grant(db,self.grant_data(),actor_id=self.actor)
            return Roots().deactivate(db,self.target,self.institution,actor_id=self.platform_admin)
        def first():
            with Session(self.engine) as db,db.begin():
                action(db,grant_first)
                first_done.set()
                if not second_attempt.wait(10):raise RuntimeError('second never started')
                # Confirm a real concurrent waiter, rather than a sequential simulation.
                import time
                until=time.monotonic()+5
                while time.monotonic()<until:
                    blocked=db.execute(text("SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted AND classid=572002 AND objid=:i"),dict(i=self.institution)).scalar()
                    if blocked:break
                    time.sleep(.01)
                self.assertGreater(blocked,0)
            return 'ok'
        def second():
            if not first_done.wait(10):raise RuntimeError('first never started')
            with Session(self.engine) as db:
                try:
                    with db.begin():
                        second_attempt.set();action(db,not grant_first)
                    return 'ok'
                except CommandError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(first);b=pool.submit(second)
            self.assertEqual(a.result(timeout=15),'ok')
            self.assertEqual(b.result(timeout=15),'ok' if grant_first else 'ROOT_INACTIVE')
        self.db.expire_all()
        self.assertFalse(self.db.get(Root,self.target_root).ativo)
        self.assertEqual(self.grants().filter_by(revogado_em=None).count(),0)
        if grant_first:self.assertEqual(self.grants().one().revogacao_origem,'RAIZ_DESATIVADA')
        else:self.assertEqual(self.grants().count(),0)

    def test_concurrent_grant_before_root_deactivation(self):self.ordered_root_race(True)
    def test_concurrent_root_deactivation_before_grant(self):self.ordered_root_race(False)

    def test_recovery_mid_flush_is_all_or_nothing(self):
        old=self.bootstrap()[0]
        self.s.revoke_authority(self.db,self.revoke_data(old.id),actor_id=self.platform_admin)
        original=self.db.flush;seen=[]
        def fail(*a,**kw):
            if any(isinstance(r,AutoridadeDelegacao) for r in self.db.new):
                seen.append(1)
                if len(seen)==2:raise RuntimeError('synthetic recovery failure')
            return original(*a,**kw)
        envelopes=[dict(capacidade_delegavel=c,envelope_tipo='INSTITUICAO') for c in ('ASSISTENCIAL_LER','CONTEXTO_ADMINISTRAR')]
        with patch.object(self.db,'flush',side_effect=fail),self.assertRaisesRegex(RuntimeError,'synthetic'):
            self.s.recovery(self.db,self.nomination(envelopes=envelopes),actor_id=self.platform_admin)
        self.assertEqual(len(seen),2)
        self.assertEqual(self.authorities().count(),1)
        self.assertIsNotNone(old.revogado_em)
        self.assertEqual(self.grants().count(),0)

    def test_institutional_envelope_grants_and_contextual_boundary(self):
        # A second historical context in the same institution is not covered by
        # an authority whose envelope names the first context only.
        second=self.db.execute(text("""INSERT INTO contextos_assistenciais
            (paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,data_fim,criado_por_usuario_id)
            SELECT paciente_instituicao_id,paciente_id,instituicao_id,'2021-01-01','2021-12-31',criado_por_usuario_id
            FROM contextos_assistenciais WHERE id=:i RETURNING id"""),dict(i=self.context)).scalar()
        row=self.bootstrap()[0]
        with self.assertRaisesRegex(CommandError,'AUTHORITY_DENIED'):self.grant(contexto_assistencial_id=second)
        self.s.revoke_authority(self.db,self.revoke_data(row.id),actor_id=self.platform_admin)
        envelopes=[dict(capacidade_delegavel=c,envelope_tipo='INSTITUICAO') for c in ('ASSISTENCIAL_LER','CONTEXTO_ADMINISTRAR')]
        self.s.recovery(self.db,self.nomination(envelopes=envelopes),actor_id=self.platform_admin)
        self.assertEqual(self.grant(contexto_assistencial_id=second).contexto_assistencial_id,second)
        self.assertIsNone(self.grant(capacidade='CONTEXTO_ADMINISTRAR',escopo_tipo='INSTITUICAO',contexto_assistencial_id=None).contexto_assistencial_id)

    def test_another_delegant_cannot_revoke_authority_or_subdelegate(self):
        old=self.bootstrap()[0]
        self.s.recovery(self.db,self.nomination(usuario_instituicao_acesso_id=self.target_root,
            envelopes=[dict(capacidade_delegavel='CONTEXTO_ADMINISTRAR',envelope_tipo='INSTITUICAO')]),actor_id=self.platform_admin)
        for fn,payload in ((self.s.revoke_authority,self.revoke_data(old.id)),
                           (self.s.bootstrap,self.nomination()),(self.s.recovery,self.nomination())):
            with self.assertRaisesRegex(CommandError,'ADMIN_REQUIRED'):fn(self.db,payload,actor_id=self.target)
        self.assertIsNone(old.revogado_em)

    def test_revocation_authority_required_and_missing_resource(self):
        self.bootstrap();row=self.grant()
        with self.assertRaisesRegex(CommandError,'AUTHORITY_DENIED'):
            self.s.revoke(self.db,self.revoke_data(row.id),actor_id=self.target)
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):
            self.s.revoke(self.db,self.revoke_data(row.id,instituicao_id=self.institutions[1]),actor_id=self.actor)
        with self.assertRaisesRegex(CommandError,'RESOURCE_NOT_FOUND'):
            self.s.revoke_authority(self.db,self.revoke_data(2147483647),actor_id=self.platform_admin)
        self.assertIsNone(row.revogado_em)

    def test_bootstrap_target_explicit_and_valid_no_self_delegation(self):
        with self.assertRaisesRegex(CommandError,'INSTITUTION_MISMATCH'):
            self.bootstrap(usuario_instituicao_acesso_id=self.roots[1])
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:i"),dict(i=self.actor))
        with self.assertRaisesRegex(CommandError,'SELF_DELEGATION_DENIED'):
            self.s.bootstrap(self.db,self.nomination(),actor_id=self.actor)
        self.db.execute(text('UPDATE usuario_instituicao_acessos SET ativo=false WHERE id=:i'),dict(i=self.roots[0]))
        with self.assertRaisesRegex(CommandError,'ROOT_INACTIVE'):self.bootstrap()
        self.assertEqual(self.authorities().count(),0)
