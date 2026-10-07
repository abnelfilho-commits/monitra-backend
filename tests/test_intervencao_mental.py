"""Authorized contextual intervention HTTP, on real disposable PostgreSQL."""
import json
import os
import unittest
from urllib.parse import urlsplit, parse_qsl
from unittest.mock import patch
from sqlalchemy import text
import test_checkin_bem_estar as foundation


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class InterventionTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.CheckinTests.tearDownClass.__func__)
    command_grant = foundation.CheckinTests.command_grant
    setUp = foundation.CheckinTests.setUp
    tearDown = foundation.CheckinTests.tearDown
    path = foundation.CheckinTests.path

    def post(self, changes=None, **scope):
        u = urlsplit(self.path(**scope))
        payload = dict(tipo='Acolhimento', descricao='Synthetic clinical intervention', data_intervencao='2026-01-01T09:30:00-04:00')
        payload.update(changes or {})
        return self.client.request('POST', u.path + '/intervencoes', params=dict(parse_qsl(u.query)),
                                   body=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})

    def test_create_read_authorship_and_legacy_isolation(self):
        r = self.post()
        self.assertEqual(r.status_code,201,r.text)
        d = r.json()
        self.assertEqual((d['pessoa_id'],d['contexto_assistencial_id'],d['modulo_id'],d['registrador_usuario_id']),
                         (self.person,self.open,3,self.actor))
        self.assertIsNotNone(d['registrador_profissional_id'])
        self.assertEqual(self.client.get(self.path()).json()['intervencoes']['itens'],[d])
        from app.models.intervencao import Intervencao
        from sqlalchemy import select
        self.assertEqual(d['data_intervencao'], '2026-01-01T13:30:00Z')
        self.assertEqual(self.db.execute(select(Intervencao).where(Intervencao.contexto_assistencial_id.is_(None))).scalars().all(), [])
        self.assertEqual(self.client.get(self.path()).json()['intervencoes']['total'], 1)
        from app.services.interventions.adapters import GenericAdapter
        patient = self.db.execute(text('SELECT paciente_id FROM contextos_assistenciais WHERE id=:c'), dict(c=self.open)).scalar_one()
        self.assertEqual(GenericAdapter().list_for_patient(self.db, patient), [])
        self.assertIsNone(GenericAdapter().get(self.db, d['id']))

    def test_scope_denied(self):
        other_person = self.db.execute(text("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic other person') RETURNING id")).scalar_one()
        self.db.commit()
        self.assertEqual(self.post(person=other_person).status_code, 403)
        for change in (dict(person=self.person+100000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.post(**change).status_code,403)

    def test_admin_no_bypass_and_no_grant(self):
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']))
        self.assertEqual(self.post().status_code,403)

    def test_read_permission_and_line_isolation(self):
        self.assertEqual(self.post().status_code,201)
        module=self.db.execute(text("INSERT INTO modulos_clinicos(nome,slug,ativo) VALUES ('Synthetic other','synthetic-other',true) RETURNING id")).scalar_one()
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,:m,true)'),dict(c=self.open,m=module))
        self.db.execute(text('UPDATE intervencoes SET modulo_id=:m WHERE contexto_assistencial_id=:c'),dict(c=self.open,m=module))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).json()['intervencoes']['itens'],[])
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def test_invalid_payload_no_identity_injection(self):
        for values in ({'pessoa_id':self.person},{'registrador_usuario_id':self.actor},{'paciente_id':1},
                       {'modulo_id':1},{'descricao':'  '},{'tipo':'  '},{'tipo':'x'*101},{'descricao':'x'*4001},{'data_intervencao':'2026-01-01T10:00:00'},{'data_intervencao':'invalid'}):
            self.assertEqual(self.post(values).status_code,422)

    def test_rollback_after_creation(self):
        from app.services.intervencao_mental import IntervencaoMentalService
        with patch.object(IntervencaoMentalService,'output',side_effect=RuntimeError('synthetic')):
            self.assertEqual(self.post().status_code,500)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM intervencoes WHERE contexto_assistencial_id=:c'),dict(c=self.open)).scalar(),0)

    def test_get_never_commits(self):
        self.assertEqual(self.post().status_code,201)
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'flush',wraps=self.db.flush) as flush:
            self.assertEqual(self.client.get(self.path()).status_code,200)
            commit.assert_not_called()
            flush.assert_not_called()

    def test_concurrent_revocation_prevents_write(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from sqlalchemy.orm import Session
        from app.schemas.intervencao_mental import IntervencaoMentalCreate
        from app.services.intervencao_mental import IntervencaoMentalService, InterventionDenied
        payload = IntervencaoMentalCreate(tipo='Acolhimento', descricao='Synthetic intervention', data_intervencao='2026-01-01T10:00:00Z')
        self.db.rollback()
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR'],motivo='Synthetic race'),actor_id=self.target)
        started = Event()
        def worker():
            with Session(self.engine) as db:
                started.set()
                try:
                    IntervencaoMentalService().create(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                except InterventionDenied:
                    db.rollback()
                    return 'DENIED'
                db.rollback()
                return 'UNEXPECTED'
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(worker)
            self.assertTrue(started.wait(2))
            self.db.commit()
            self.assertEqual(future.result(timeout=8),'DENIED')

    def test_migration_preserves_history_and_conservative_downgrade(self):
        from alembic import command
        from test_m0_baseline import config
        self.assertEqual(self.post().status_code,201)
        with self.assertRaisesRegex(RuntimeError,'INTERVENTION_AUTHORSHIP_PRESENT'):
            with self.engine.begin() as c:
                command.downgrade(config(c),'w3_diagnostico_autoria_v1')
        self.assertEqual(len(self.client.get(self.path()).json()['intervencoes']['itens']),1)
        columns = self.db.execute(text("SELECT column_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='intervencoes' AND column_name LIKE 'registrador_%'")).all()
        self.assertEqual({(r.column_name,r.is_nullable,r.column_default) for r in columns},
                         {('registrador_profissional_id','YES',None)})

    def test_history_preserved_through_upgrade_and_empty_authorship_downgrade(self):
        from alembic import command
        from sqlalchemy import create_engine, inspect
        from uuid import uuid4
        from test_m0_baseline import config
        name = 'intervention_migration_' + uuid4().hex
        with self.admin.connect() as c:
            c.exec_driver_sql('CREATE DATABASE ' + name)
        engine = create_engine(self.engine.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'w3_diagnostico_autoria_v1')
                module = c.execute(text("INSERT INTO modulos_clinicos(nome,slug,ativo) VALUES ('Synthetic historical', 'synthetic-intervention-history', true) RETURNING id")).scalar_one()
                identity = c.execute(text("INSERT INTO intervencoes(modulo_id,tipo,descricao,data_intervencao) VALUES (:m,'Historical type','Historical description','2025-01-01 08:30:00') RETURNING id"),dict(m=module)).scalar_one()
                before = c.execute(text('SELECT to_jsonb(i) FROM intervencoes i WHERE id=:i'),dict(i=identity)).scalar_one()
                command.upgrade(config(c),'w3_intervencao_autoria_v1')
                after = c.execute(text('SELECT to_jsonb(i) FROM intervencoes i WHERE id=:i'),dict(i=identity)).scalar_one()
                self.assertIsNone(after.pop('registrador_profissional_id'))
                self.assertEqual(after, before)
                self.assertEqual(c.execute(text('SELECT count(*) FROM intervencoes')).scalar(),1)
                fks=c.execute(text("SELECT confdeltype,convalidated FROM pg_constraint WHERE conrelid='intervencoes'::regclass AND conname IN ('fk_intervencoes_registrador_profissional_id')")).all()
                self.assertEqual([tuple(r) for r in fks],[('r',True)])
                command.downgrade(config(c),'w3_diagnostico_autoria_v1')
                self.assertNotIn('registrador_profissional_id',{x['name'] for x in inspect(c).get_columns('intervencoes')})
                command.upgrade(config(c),'w3_intervencao_autoria_v1')
                self.assertIn('registrador_profissional_id',{x['name'] for x in inspect(c).get_columns('intervencoes')})
        finally:
            engine.dispose()
            with self.admin.connect() as c:
                c.exec_driver_sql('DROP DATABASE ' + name)

    def test_inactive_line_blocks_write(self):
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c AND modulo_id=3'), dict(c=self.open))
        self.db.commit()
        self.assertEqual(self.post().status_code, 403)

    def test_closed_context_blocks_write(self):
        self.db.execute(text("UPDATE contextos_assistenciais SET data_fim=CURRENT_DATE-1 WHERE id=:c"), dict(c=self.open))
        self.db.commit()
        self.assertEqual(self.post().status_code, 403)

    def test_intervention_does_not_change_reading_or_other_events(self):
        before = self.client.get(self.path()).json()
        self.assertEqual(self.post().status_code, 201)
        after = self.client.get(self.path()).json()
        for key in ('clinical_reading', 'bem_estar', 'diagnosticos'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after['intervencoes']['total'], 1)

    def test_context_and_author_dependencies_rechecked(self):
        cases = [('UPDATE usuarios SET ativo=false WHERE id=:i', self.actor),
                 ('UPDATE pessoas SET ativo=false WHERE id=:i', self.person),
                 ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i', self.links[0]),
                 ('DELETE FROM contexto_profissionais WHERE id=:i', self.participations[self.open])]
        for sql, identity in cases:
            with self.subTest(sql=sql):
                self.db.execute(text(sql), dict(i=identity))
                self.assertEqual(self.post().status_code, 403)
                self.db.rollback()
