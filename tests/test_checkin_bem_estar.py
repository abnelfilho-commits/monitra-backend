"""Real canonical persistence and lifecycle races on disposable PostgreSQL 18."""
import os
import unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.schemas.checkin_bem_estar import CheckinCreate
from app.services.checkin_bem_estar import CheckinBemEstarService, CheckinDenied
from app.services.checkin_contract import FIELDS
import test_saude_mental as foundation


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL 18 required')
class CheckinTests(unittest.TestCase):
    schema_revision='head'  # Current HTTP service uses the current schema; historical migration checks remain explicit.
    setUpClass=classmethod(foundation.JourneyTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.JourneyTests.tearDownClass.__func__)
    command_grant=foundation.JourneyTests.command_grant
    setUp=foundation.JourneyTests.setUp
    tearDown=foundation.JourneyTests.tearDown
    path=foundation.JourneyTests.path

    def payload(self):
        f=self.db.execute(text("SELECT id FROM formularios_modulo WHERE codigo='BEM_ESTAR_V1'")).scalar_one()
        p=self.db.execute(text('SELECT paciente_id FROM contextos_assistenciais WHERE id=:c'),dict(c=self.open)).scalar_one()
        return dict(paciente_id=p,modulo_id=3,formulario_id=f,respostas={n:o[0][0] for n,_,o in FIELDS if o})

    def post(self,payload=None,**changes):
        from urllib.parse import urlsplit,parse_qsl
        url=urlsplit(self.path(**changes))
        import json
        return self.client.request('POST',url.path+'/check-ins',params=dict(parse_qsl(url.query)),body=json.dumps(payload or self.payload()).encode(),headers={'Content-Type':'application/json'})

    def counts(self):
        return tuple(self.db.execute(text(sql),dict(c=self.open)).scalar_one() for sql in (
            'SELECT count(*) FROM registros_longitudinais WHERE contexto_assistencial_id=:c',
            'SELECT count(*) FROM respostas_registro WHERE registro_id IN (SELECT id FROM registros_longitudinais WHERE contexto_assistencial_id=:c)',
            'SELECT count(*) FROM registro_proveniencias WHERE registro_id IN (SELECT id FROM registros_longitudinais WHERE contexto_assistencial_id=:c)'))

    def test_real_persistence_provenance_and_journey(self):
        payload=self.payload();payload['respostas'].update(evento_relevante='SIM',evento_descricao='Synthetic event')
        response=self.post(payload);self.assertEqual(response.status_code,201,response.text)
        d=response.json();self.assertTrue(d['baseline']);self.assertEqual(d['respondente_pessoa_id'],self.person)
        r=self.db.execute(text('SELECT paciente_id,modulo_id,contexto_assistencial_id,criado_por_usuario_id,criado_por_responsavel_id FROM registros_longitudinais WHERE id=:i'),dict(i=d['id'])).one()
        self.assertEqual(tuple(r),(payload['paciente_id'],3,self.open,self.actor,None))
        p=self.db.execute(text('SELECT registrador_profissional_id,canal,modalidade FROM registro_proveniencias WHERE registro_id=:i'),dict(i=d['id'])).one()
        self.assertEqual(p.canal,'PORTAL_PROFISSIONAL');self.assertEqual(p.modalidade,'ASSISTIDO')
        self.assertEqual(p.registrador_profissional_id,self.db.execute(text('SELECT id FROM profissionais WHERE pessoa_id=(SELECT pessoa_id FROM usuarios WHERE id=:u)'),dict(u=self.actor)).scalar_one())
        self.assertEqual(self.counts(),(1,10,1))
        journey=self.client.get(self.path()).json()['bem_estar']
        self.assertTrue(journey['pode_registrar']);self.assertEqual(journey['checkins'][0]['respostas'],payload['respostas'])
        self.assertNotIn('score',str(journey))

    def test_second_allowed_baseline_is_first(self):
        a=self.post();b=self.post()
        self.assertEqual(b.status_code,201,b.text);self.assertTrue(a.json()['baseline']);self.assertFalse(b.json()['baseline'])
        self.assertEqual([x['baseline'] for x in self.client.get(self.path()).json()['bem_estar']['checkins']],[True,False])

    def test_denials(self):
        cases=[('DELETE FROM concessoes_assistenciais WHERE id=:i',self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']),
               ('UPDATE contextos_assistenciais SET ativo=false WHERE id=:i',self.open),
               ("UPDATE contextos_assistenciais SET data_fim=CURRENT_DATE WHERE id=:i",self.open),
               ('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:i',self.open),
               ('DELETE FROM contexto_assistencial_linhas WHERE contexto_assistencial_id=:i',self.open),
               ('UPDATE usuarios SET ativo=false WHERE id=:i',self.actor),
               ('UPDATE pessoas SET ativo=false WHERE id=:i',self.person),
               ('DELETE FROM contexto_profissionais WHERE id=:i',self.participations[self.open]),
               ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i',self.links[0])]
        for sql,i in cases:
            with self.subTest(sql=sql):
                # Command's rollback reverts this synthetic precondition too.
                self.db.execute(text(sql),dict(i=i));r=self.post();self.assertEqual(r.status_code,403,r.text)
                self.assertEqual(self.counts(),(0,0,0));self.db.rollback()

    def test_wrong_scope_and_patient(self):
        for change in (dict(person=self.person+100000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.post(**change).status_code,403)
        p=self.payload();p['paciente_id']+=100000;self.assertEqual(self.post(p).status_code,403)
        self.assertEqual(self.counts(),(0,0,0))

    def test_admin_no_bypass(self):
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']))
        self.assertEqual(self.post().status_code,403)

    def test_validation_no_partial_writes(self):
        for mutation in ('missing','unknown','invalid','description','actor'):
            p=self.payload()
            if mutation=='missing':del p['respostas']['humor']
            elif mutation=='unknown':p['respostas']['score']='10'
            elif mutation=='invalid':p['respostas']['humor']='10'
            elif mutation=='description':p['respostas'].update(evento_relevante='NAO',evento_descricao='Not allowed')
            else:p['ator_usuario_id']=self.actor
            self.assertEqual(self.post(p).status_code,422)
            self.assertEqual(self.counts(),(0,0,0));self.db.rollback()

    def test_rollback_after_root_answers_and_provenance(self):
        from app.services import checkin_bem_estar as module
        original=module.criar_registro_longitudinal
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            self.assertEqual(self.counts()[:2],(1,9))
            raise RuntimeError('private synthetic failure')
        with patch.object(module,'criar_registro_longitudinal',side_effect=fail):
            r=self.post();self.assertEqual(r.status_code,500);self.assertNotIn('private',r.text)
        self.assertEqual(self.counts(),(0,0,0))
        from app.routers import saude_mental
        with patch.object(saude_mental.CheckinOut,'model_validate',side_effect=RuntimeError('response failure')):
            self.assertEqual(self.post().status_code,500)
        self.assertEqual(self.counts(),(0,0,0))

    def test_caller_owned_no_commit(self):
        p=CheckinCreate(**self.payload())
        with patch.object(self.db,'commit',side_effect=AssertionError('internal commit')):
            CheckinBemEstarService().create(self.db,p,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
        self.db.rollback();self.assertEqual(self.counts(),(0,0,0))

    def test_read_deny_and_legacy_isolation(self):
        r=self.post().json()
        from app.services.registros_longitudinais import obter_registro_longitudinal
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):obter_registro_longitudinal(self.db,r['id'])
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_LER']));self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)
        self.assertEqual(CheckinBemEstarService().read(self.db,actor=self.actor,institution=self.institution,person=self.person,context=self.open),[])

    def test_preexisting_revocation_wins_after_lock_wait(self):
        payload=CheckinCreate(**self.payload());self.db.rollback()
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR'],motivo='Synthetic race'),actor_id=self.target)
        started=Event()
        def worker():
            with Session(self.engine) as db:
                started.set()
                try:CheckinBemEstarService().create(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                except CheckinDenied:db.rollback();return 'DENIED'
                db.rollback();return 'UNEXPECTED'
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(worker);self.assertTrue(started.wait(2));self.db.commit()
            self.assertEqual(future.result(timeout=8),'DENIED')
        self.assertEqual(self.counts(),(0,0,0))

    def test_context_close_wins_after_row_wait(self):
        p=CheckinCreate(**self.payload());self.db.rollback()
        self.db.execute(text('UPDATE contextos_assistenciais SET data_fim=CURRENT_DATE WHERE id=:c'),dict(c=self.open))
        started=Event()
        def worker():
            with Session(self.engine) as db:
                started.set()
                try:CheckinBemEstarService().create(db,p,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                except CheckinDenied:db.rollback();return 'DENIED'
                db.rollback();return 'UNEXPECTED'
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(worker);self.assertTrue(started.wait(2));self.db.commit()
            self.assertEqual(future.result(timeout=8),'DENIED')
        self.assertEqual(self.counts(),(0,0,0))

    def test_provenance_constraint_refuses_fake_recorder(self):
        from sqlalchemy.exc import IntegrityError
        saved=self.post().json()
        with self.assertRaises(IntegrityError):
            self.db.execute(text('UPDATE registro_proveniencias SET registrador_profissional_id=NULL WHERE registro_id=:r'),dict(r=saved['id']))
        self.db.rollback()
        self.assertEqual(self.counts(),(1,9,1))

    def test_write_locks_line_until_caller_finishes(self):
        from sqlalchemy.exc import OperationalError
        payload=CheckinCreate(**self.payload())
        CheckinBemEstarService().create(self.db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
        def competing_close():
            with Session(self.engine) as other:
                other.execute(text("SET LOCAL lock_timeout='150ms'"))
                try:other.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open))
                except OperationalError as e:
                    code=e.orig.pgcode;other.rollback();return code
                other.rollback();return 'UNEXPECTED'
        with ThreadPoolExecutor(1) as pool:self.assertEqual(pool.submit(competing_close).result(timeout=5),'55P03')
        self.db.rollback();self.assertEqual(self.counts(),(0,0,0))

    def test_parallel_checkins_one_chronological_baseline(self):
        payload=CheckinCreate(**self.payload());self.db.rollback()
        def write():
            with Session(self.engine) as db:
                result=CheckinBemEstarService().create(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                db.commit();return result.baseline
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(write) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=8) for f in futures),[False,True])
        self.assertEqual([x['baseline'] for x in self.client.get(self.path()).json()['bem_estar']['checkins']],[True,False])


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL 18 required')
class CheckinMigrationTests(unittest.TestCase):
    setUp=foundation.CatalogueMigrationTests.setUp
    tearDown=foundation.CatalogueMigrationTests.tearDown

    def test_empty_incremental_and_safe_downgrade(self):
        from alembic import command
        from test_m0_baseline import config
        with self.engine.begin() as c:
            command.upgrade(config(c),'w2b_checkin_v1')
            self.assertEqual(c.exec_driver_sql("SELECT count(*) FROM campos_formulario WHERE formulario_id=(SELECT id FROM formularios_modulo WHERE codigo='BEM_ESTAR_V1')").scalar(),10)
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM registros_longitudinais').scalar(),0)
            command.downgrade(config(c),'w2a_saude_mental_v1')
            command.upgrade(config(c),'w2b_checkin_v1')
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM registro_proveniencias').scalar(),0)

    def test_provenance_exact_physical_contract(self):
        from alembic import command
        from sqlalchemy import inspect
        from test_m0_baseline import config
        from app.models.registro_proveniencia import RegistroProveniencia
        with self.engine.begin() as c:
            command.upgrade(config(c),'head')
            inspector=inspect(c);table=RegistroProveniencia.__table__
            columns=inspector.get_columns(table.name)
            self.assertEqual([(x['name'],str(x['type']),x['nullable'],x['default']) for x in columns],
                [(x.name,str(x.type),x.nullable,None) for x in table.columns])
            self.assertEqual(inspector.get_pk_constraint(table.name)['constrained_columns'],['registro_id'])
            actual={(tuple(f['constrained_columns']),f['referred_table'],tuple(f['referred_columns']),f['options']['ondelete']) for f in inspector.get_foreign_keys(table.name)}
            expected={(tuple(x.name for x in f.columns),f.elements[0].column.table.name,tuple(e.column.name for e in f.elements),f.ondelete) for f in table.foreign_key_constraints}
            self.assertEqual(actual,expected)
            self.assertEqual([x['name'] for x in inspector.get_check_constraints(table.name)],['ck_registro_proveniencia_modalidade'])
            self.assertEqual(inspector.get_indexes(table.name),[])
            self.assertEqual(inspector.get_unique_constraints(table.name),[])

    def test_collision_refuses_without_overwrite(self):
        from alembic import command
        from test_m0_baseline import config
        with self.engine.begin() as c:
            command.upgrade(config(c),'w2a_saude_mental_v1')
            c.exec_driver_sql("INSERT INTO formularios_modulo(modulo_id,nome,tipo,codigo) VALUES (3,'Existing','OTHER','BEM_ESTAR_V1')")
        with self.assertRaisesRegex(RuntimeError,'CHECKIN_FORM_CONFLICT'):
            with self.engine.begin() as c:command.upgrade(config(c),'head')
        with self.engine.connect() as c:self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'w2a_saude_mental_v1')


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class HistoricalCheckinDowngradeTests(unittest.TestCase):
    schema_revision = 'w2b_checkin_v1'
    setUpClass = classmethod(CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(CheckinTests.tearDownClass.__func__)
    command_grant = CheckinTests.command_grant
    setUp = CheckinTests.setUp
    tearDown = CheckinTests.tearDown
    path = CheckinTests.path
    payload = CheckinTests.payload
    post = CheckinTests.post
    counts = CheckinTests.counts

    def test_downgrade_refuses_clinical_history(self):
        from alembic import command
        from test_m0_baseline import config
        saved=self.post().json()
        with self.assertRaisesRegex(RuntimeError,'CHECKIN_HISTORY_PRESENT'):
            with self.engine.begin() as c:command.downgrade(config(c),'w2a_saude_mental_v1')
        self.assertEqual(self.counts(),(1,9,1))
        self.assertEqual(self.db.execute(text('SELECT registro_id FROM registro_proveniencias')).scalar_one(), saved['id'])
