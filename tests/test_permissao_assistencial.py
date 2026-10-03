"""W1B-B physical contract only, on disposable PostgreSQL 18; no command services."""
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
        self.assertEqual(scripts.get_heads(), ['w1b_permissoes_v1'])
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
    @classmethod
    def setUpClass(cls):
        cls.url=make_url(URL)
        if cls.url.host!='127.0.0.1' or cls.url.database!='m0_baseline':raise RuntimeError('Disposable local database required')
        cls.admin=create_engine(cls.url,isolation_level='AUTOCOMMIT');cls.name='w1b_'+uuid4().hex
        with cls.admin.connect() as c:
            if int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000!=18:raise RuntimeError('PG18 required')
            c.exec_driver_sql('CREATE DATABASE '+cls.name)
        cls.engine=create_engine(cls.url.set(database=cls.name),connect_args={'options':'-c lock_timeout=5000 -c statement_timeout=15000'})
        with cls.engine.begin() as c:command.upgrade(config(c),'head')

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
        barrier=Barrier(2)
        def worker(_):
            try:
                with self.engine.begin() as c:
                    barrier.wait(timeout=10);self.insert(c,model)
                return 'persisted'
            except IntegrityError as exc:return exc.orig.pgcode
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(worker,range(2)))
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
                self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'w1b_permissoes_v1')
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
