"""Authorized contextual diagnosis HTTP, on real disposable PostgreSQL."""
import json
import os
import unittest
from urllib.parse import urlsplit, parse_qsl
from unittest.mock import patch
from sqlalchemy import text
import test_checkin_bem_estar as foundation


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class DiagnosisTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.CheckinTests.tearDownClass.__func__)
    command_grant = foundation.CheckinTests.command_grant
    setUp = foundation.CheckinTests.setUp
    tearDown = foundation.CheckinTests.tearDown
    path = foundation.CheckinTests.path

    def post(self, changes=None, **scope):
        u = urlsplit(self.path(**scope))
        payload = dict(descricao_clinica='Synthetic clinical diagnosis', medico_nome='Synthetic physician', data_diagnostico='2026-01-01', cid='F00')
        payload.update(changes or {})
        return self.client.request('POST', u.path + '/diagnosticos', params=dict(parse_qsl(u.query)),
                                   body=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})

    def test_create_read_authorship_and_legacy_isolation(self):
        r = self.post()
        self.assertEqual(r.status_code,201,r.text)
        d = r.json()
        self.assertEqual((d['pessoa_id'],d['contexto_assistencial_id'],d['modulo_id'],d['registrador_usuario_id']),
                         (self.person,self.open,3,self.actor))
        self.assertIsNotNone(d['registrador_profissional_id'])
        self.assertEqual(self.client.get(self.path()).json()['diagnosticos']['itens'],[d])
        from app.services.diagnostico_service import DiagnosticoService
        patient=self.db.execute(text('SELECT paciente_id FROM contextos_assistenciais WHERE id=:c'),dict(c=self.open)).scalar_one()
        self.assertEqual(DiagnosticoService.listar_por_paciente(self.db,patient),[])

    def test_scope_denied(self):
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
        self.db.execute(text('UPDATE diagnosticos SET modulo_id=:m WHERE contexto_assistencial_id=:c'),dict(c=self.open,m=module))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).json()['diagnosticos']['itens'],[])
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def test_invalid_payload_no_identity_injection(self):
        for values in ({'pessoa_id':self.person},{'registrador_usuario_id':self.actor},{'paciente_id':1},
                       {'modulo_id':1},{'descricao_clinica':'  '},{'medico_nome':'  '},{'tipo':'INVALID'}):
            self.assertEqual(self.post(values).status_code,422)

    def test_rollback_after_creation(self):
        from app.services.diagnostico_mental import DiagnosticoMentalService
        with patch.object(DiagnosticoMentalService,'output',side_effect=RuntimeError('synthetic')):
            self.assertEqual(self.post().status_code,500)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM diagnosticos WHERE contexto_assistencial_id=:c'),dict(c=self.open)).scalar(),0)

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
        from app.schemas.diagnostico_mental import DiagnosticoMentalCreate
        from app.services.diagnostico_mental import DiagnosticoMentalService, DiagnosisDenied
        payload = DiagnosticoMentalCreate(descricao_clinica='Synthetic diagnosis', medico_nome='Synthetic physician', data_diagnostico='2026-01-01')
        self.db.rollback()
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR'],motivo='Synthetic race'),actor_id=self.target)
        started = Event()
        def worker():
            with Session(self.engine) as db:
                started.set()
                try:
                    DiagnosticoMentalService().create(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open)
                except DiagnosisDenied:
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
        with self.assertRaisesRegex(RuntimeError,'DIAGNOSIS_AUTHORSHIP_PRESENT'):
            with self.engine.begin() as c:
                command.downgrade(config(c),'capacidade_reconciliacao_v1')
        self.assertEqual(len(self.client.get(self.path()).json()['diagnosticos']['itens']),1)
        columns = self.db.execute(text("SELECT column_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='diagnosticos' AND column_name LIKE 'registrador_%'")).all()
        self.assertEqual({(r.column_name,r.is_nullable,r.column_default) for r in columns},
                         {('registrador_usuario_id','YES',None),('registrador_profissional_id','YES',None)})

    def test_empty_downgrade_upgrade(self):
        from alembic import command
        from sqlalchemy import create_engine, inspect
        from uuid import uuid4
        from test_m0_baseline import config
        name = 'diagnosis_migration_' + uuid4().hex
        with self.admin.connect() as c:
            c.exec_driver_sql('CREATE DATABASE ' + name)
        engine = create_engine(self.engine.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'w3_diagnostico_autoria_v1')
                self.assertEqual(c.execute(text('SELECT count(*) FROM diagnosticos')).scalar(),0)
                fks=c.execute(text("SELECT confdeltype,convalidated FROM pg_constraint WHERE conrelid='diagnosticos'::regclass AND conname IN ('fk_diagnosticos_registrador_usuario_id','fk_diagnosticos_registrador_profissional_id')")).all()
                self.assertEqual([tuple(r) for r in fks],[('r',True),('r',True)])
                command.downgrade(config(c),'capacidade_reconciliacao_v1')
                self.assertNotIn('registrador_usuario_id',{x['name'] for x in inspect(c).get_columns('diagnosticos')})
                command.upgrade(config(c),'w3_diagnostico_autoria_v1')
                self.assertIn('registrador_usuario_id',{x['name'] for x in inspect(c).get_columns('diagnosticos')})
        finally:
            engine.dispose()
            with self.admin.connect() as c:
                c.exec_driver_sql('DROP DATABASE ' + name)
