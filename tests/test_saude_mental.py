"""W2-A contextual read boundary on disposable PostgreSQL 18; no operational DB."""
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from test_whatsapp_security import LocalClient
from urllib.parse import urlsplit, parse_qsl


class TestClient(LocalClient):
    def get(self, path, params=None, headers=None):
        url=urlsplit(path)
        return self.request("GET", url.path, headers=headers, params=params or dict(parse_qsl(url.query)))

from sqlalchemy import event, text
from app.core.deps import get_usuario_atual
from app.database import get_db
from app.routers.saude_mental import router
from app.services.saude_mental import SaudeMentalService, MentalHealthUnavailable
from app.services.care_lines.registry import MENTAL_HEALTH, care_line_registry
import test_autorizacao_contextual as foundation


class RegistryTests(unittest.TestCase):
    def test_transversal_registry_and_no_fake_capabilities(self):
        self.assertIs(care_line_registry.get('saude_mental'), MENTAL_HEALTH)
        self.assertEqual(MENTAL_HEALTH.module_id, 3)
        self.assertTrue(MENTAL_HEALTH.supports('contextual_journey'))
        for cap in ('daily_record','clinical_engine','timeline','report','whatsapp','cockpit'):
            self.assertFalse(MENTAL_HEALTH.supports(cap))

    def test_registered_routes(self):
        from app.main import app
        self.assertEqual({r.path for r in app.routes if r.path.startswith("/saude-mental")},
                         {"/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/diagnosticos", "/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}/check-ins", "/saude-mental/instituicoes", "/saude-mental/pessoas", "/saude-mental/pessoas/{pessoa_id}/contextos/{contexto_id}"})

    def test_no_legacy_acl_or_write_api(self):
        for file in ('app/services/saude_mental.py','app/routers/saude_mental.py'):
            source=Path(file).read_text()
            self.assertNotIn('clinica_id',source)
            self.assertNotIn('ADMIN',source)
            if '/services/' in file:self.assertNotIn('.commit(',source)
        self.assertTrue(all(route.methods == {'GET'} for route in router.routes if not route.path.endswith(('/check-ins', '/diagnosticos'))))
        self.assertEqual(sum(route.methods == {'POST'} for route in router.routes),2)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Requires disposable PostgreSQL 18')
class JourneyTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.EvaluatorTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.EvaluatorTests.tearDownClass.__func__)
    command_grant = foundation.EvaluatorTests.command_grant

    def setUp(self):
        foundation.EvaluatorTests.setUp(self)
        self.person=self.db.execute(text("INSERT INTO pessoas(nome_completo,nome_social) VALUES ('Synthetic Patient','Synthetic Social') RETURNING id")).scalar_one()
        self.db.execute(text('UPDATE pacientes SET pessoa_id=:p WHERE id=(SELECT paciente_id FROM contextos_assistenciais WHERE id=:c)'),dict(p=self.person,c=self.open))
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.open))
        self.db.commit()
        self.mental=SaudeMentalService()
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor)
        self.app=app;self.client=TestClient(app)

    def tearDown(self):
        self.db.rollback();self.db.close()

    def path(self, **changes):
        p=dict(person=self.person,context=self.open,institution=self.institution);p.update(changes)
        return f"/saude-mental/pessoas/{p['person']}/contextos/{p['context']}?instituicao_id={p['institution']}"

    def test_exact_journey_and_canonical_person(self):
        r=self.client.get(self.path());self.assertEqual(r.status_code,200,r.text)
        d=r.json();self.assertEqual(d['pessoa_id'],self.person);self.assertEqual(d['nome_social'],'Synthetic Social')
        self.assertEqual(d['contexto_assistencial_id'],self.open);self.assertEqual(d['linha_estado'],'ATIVA')
        self.assertEqual(d['modulo_id'],3);self.assertNotIn('cpf',d);self.assertNotIn('email',d)

    def test_people_filtered_before_pagination(self):
        r=self.client.get('/saude-mental/pessoas',params=dict(instituicao_id=self.institution))
        self.assertEqual(r.status_code,200)
        self.assertEqual({x['contexto_assistencial_id'] for x in r.json()['itens']},{self.open,self.closed})
        r=self.client.get('/saude-mental/pessoas',params=dict(instituicao_id=self.institutions[1]))
        self.assertEqual(r.json(),dict(itens=[],tem_mais=False))
        self.assertEqual(self.client.get('/saude-mental/pessoas').status_code,422)

    def test_wrong_context_institution_person_and_absent_indistinguishable(self):
        for change in (dict(context=self.contexts[1]),dict(institution=self.institutions[1]),dict(person=self.person+900000),dict(context=2147483647)):
            r=self.client.get(self.path(**change));self.assertEqual(r.status_code,404);self.assertEqual(r.json()['detail']['code'],'JOURNEY_UNAVAILABLE')

    def test_absent_and_inactive_line_are_metadata_only(self):
        r=self.client.get(self.path(context=self.closed));self.assertEqual(r.json()['linha_estado'],'AUSENTE')
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open));self.db.commit()
        r=self.client.get(self.path());self.assertEqual(r.json()['linha_estado'],'INATIVA')
        self.assertNotIn('eventos',r.json())

    def test_grant_revocation_no_cached_access(self):
        self.assertEqual(self.client.get(self.path()).status_code,200)
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_LER'],motivo='Synthetic revoke'),actor_id=self.target)
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def test_admin_without_clinical_grant_denied(self):
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE usuario_instituicao_acesso_id=:r'),dict(r=self.roots[0]));self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)
        self.assertEqual(self.client.get('/saude-mental/pessoas',params=dict(instituicao_id=self.institution)).json()['itens'],[])

    def test_participation_required_even_with_grant(self):
        self.db.execute(text('DELETE FROM contexto_profissionais WHERE contexto_assistencial_id=:c'),dict(c=self.open));self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def test_catalog_inactive_fail_closed(self):
        self.db.execute(text('UPDATE modulos_clinicos SET ativo=false WHERE id=3'))
        try:
            self.assertEqual(self.client.get(self.path()).status_code,503)
        finally:self.db.rollback()

    def test_institution_choices_no_global_admin_fallback(self):
        rows=self.client.get('/saude-mental/instituicoes').json()
        self.assertEqual({r['id'] for r in rows},set(self.institutions))
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.platform_admin)
        self.assertEqual(self.client.get('/saude-mental/instituicoes').json(),[])

    def test_authentication_and_invalid_ids(self):
        del self.app.dependency_overrides[get_usuario_atual]
        self.assertEqual(self.client.get(self.path()).status_code,401)
        self.assertEqual(self.client.get(self.path(),headers={'Authorization':'Bearer invalid'}).status_code,401)

    def test_read_only_no_commit_or_flush(self):
        statements=[]
        def capture(c,cursor,statement,*args):statements.append(statement.strip().split()[0].upper())
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            with patch.object(self.db,'commit',side_effect=AssertionError('commit')),patch.object(self.db,'flush',side_effect=AssertionError('flush')):
                self.assertEqual(self.client.get(self.path()).status_code,200)
                self.assertEqual(self.client.get('/saude-mental/pessoas',params=dict(instituicao_id=self.institution)).status_code,200)
            self.assertTrue(statements);self.assertTrue(all(x=='SELECT' for x in statements),statements)
        finally:event.remove(self.engine,'before_cursor_execute',capture)

    def test_seed_exact_no_clinical_backfill(self):
        row=self.db.execute(text('SELECT nome,slug,ativo FROM modulos_clinicos WHERE id=3')).one()
        self.assertEqual(tuple(row),('Saúde Mental','saude_mental',True))
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM paciente_modulos WHERE modulo_id=3')).scalar(),0)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Requires disposable PostgreSQL 18')
class CatalogueMigrationTests(unittest.TestCase):
    """Test the additive seed over an existing predecessor, including collisions."""
    def setUp(self):
        from uuid import uuid4
        from sqlalchemy import create_engine
        from sqlalchemy.engine import make_url
        from alembic import command
        from test_m0_baseline import config
        url=make_url(os.environ['M0_TEST_POSTGRES_URL'])
        if url.host!='127.0.0.1' or url.database!='m0_baseline':raise RuntimeError('Disposable database required')
        self.admin=create_engine(url,isolation_level='AUTOCOMMIT');self.name='w2a_catalog_'+uuid4().hex
        with self.admin.connect() as c:
            self.assertEqual(int(c.exec_driver_sql('SHOW server_version_num').scalar())//10000,18)
            c.exec_driver_sql('CREATE DATABASE '+self.name)
        self.engine=create_engine(url.set(database=self.name))
        with self.engine.begin() as c:
            command.upgrade(config(c),'w1c_isolamento_legado_v1')
            c.exec_driver_sql("INSERT INTO modulos_clinicos(id,nome,slug) VALUES (1,'Neuro','neurodesenvolvimento'),(2,'Cardio','cardiometabolico')")

    def tearDown(self):
        self.engine.dispose()
        with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+self.name)
        self.admin.dispose()

    def test_additive_seed_preserves_previous_lines_and_generates_safe_ids(self):
        from alembic import command
        from test_m0_baseline import config
        with self.engine.begin() as c:
            before=c.exec_driver_sql('SELECT row_to_json(m) FROM modulos_clinicos m ORDER BY id').all()
            command.upgrade(config(c),'w2a_saude_mental_v1')
            self.assertEqual(c.exec_driver_sql('SELECT row_to_json(m) FROM modulos_clinicos m WHERE id IN (1,2) ORDER BY id').all(),before)
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM contexto_assistencial_linhas').scalar(),0)
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM paciente_modulos').scalar(),0)
            generated=c.exec_driver_sql("INSERT INTO modulos_clinicos(nome,slug) VALUES ('Synthetic future','synthetic-future') RETURNING id").scalar()
            self.assertGreater(generated,3)

    def test_existing_id_fails_closed_without_overwrite(self):
        from alembic import command
        from test_m0_baseline import config
        with self.engine.begin() as c:c.exec_driver_sql("INSERT INTO modulos_clinicos(id,nome,slug) VALUES (3,'Existing','existing')")
        with self.assertRaisesRegex(RuntimeError,'MENTAL_HEALTH_CATALOG_CONFLICT'):
            with self.engine.begin() as c:command.upgrade(config(c),'w2a_saude_mental_v1')
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT slug FROM modulos_clinicos WHERE id=3').scalar(),'existing')
            self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'w1c_isolamento_legado_v1')

    def test_downgrade_empty_only_and_preserves_other_lines(self):
        from alembic import command
        from test_m0_baseline import config
        with self.engine.begin() as c:
            command.upgrade(config(c),'w2a_saude_mental_v1')
            command.downgrade(config(c),'w1c_isolamento_legado_v1')
            self.assertEqual(c.exec_driver_sql('SELECT id FROM modulos_clinicos ORDER BY id').scalars().all(),[1,2])
            command.upgrade(config(c),'w2a_saude_mental_v1')
            patient=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar_one()
            c.execute(text('INSERT INTO paciente_modulos(paciente_id,modulo_id) VALUES (:p,3)'),dict(p=patient))
        with self.assertRaisesRegex(RuntimeError,'MENTAL_HEALTH_HAS_DEPENDENCIES'):
            with self.engine.begin() as c:command.downgrade(config(c),'w1c_isolamento_legado_v1')
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT count(*) FROM paciente_modulos WHERE modulo_id=3').scalar(),1)
            self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'w2a_saude_mental_v1')
