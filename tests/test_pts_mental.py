"""Canonical PTS with contextual W1B authorization, actual PostgreSQL and HTTP."""
import json
import os
import unittest
from urllib.parse import urlsplit,parse_qsl
from unittest.mock import patch
from sqlalchemy import text
import test_checkin_bem_estar as foundation


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL required')
class PTSMentalTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.CheckinTests.tearDownClass.__func__)
    setUp=foundation.CheckinTests.setUp
    tearDown=foundation.CheckinTests.tearDown
    command_grant=foundation.CheckinTests.command_grant
    path=foundation.CheckinTests.path

    def request(self,method='GET',suffix='',payload=None,**scope):
        u=urlsplit(self.path(**scope))
        return self.client.request(method,u.path+'/pts'+suffix,params=dict(parse_qsl(u.query)),body=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})

    def create(self):
        r=self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Cuidado contextual',observacoes='Condutas profissionais'))
        self.assertEqual(r.status_code,201,r.text)
        return r.json()

    def test_complete_lifecycle_objectives_and_no_clinical_reading_change(self):
        before=self.client.get(self.path()).json()['clinical_reading']
        patients=self.db.execute(text('SELECT count(*) FROM pacientes')).scalar()
        plan=self.create();identity=plan['id']
        self.assertEqual((plan['contexto_assistencial_id'],plan['pessoa_id'],plan['modulo_id'],plan['status'],plan['criado_por_usuario_id']),(self.open,self.person,3,'ATIVO',self.actor))
        r=self.request('POST',f'/{identity}/objetivos',dict(descricao='Objetivo profissional',prioridade='ALTA'))
        self.assertEqual(r.status_code,201,r.text);objective=r.json()['objetivos'][0]['id']
        r=self.request('PUT',f'/{identity}/objetivos/{objective}',dict(status='CONCLUIDO',descricao='Objetivo acompanhado'))
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['objetivos'][0]['status'],'CONCLUIDO')
        r=self.request('PUT',f'/{identity}',dict(objetivo_geral='Objetivo atualizado',observacoes='Condutas atualizadas'))
        self.assertEqual(r.status_code,200,r.text)
        for action,status in [('encerrar','ENCERRADO'),('encerrar','ENCERRADO'),('reabrir','ATIVO'),('reabrir','ATIVO')]:
            r=self.request('PUT',f'/{identity}/{action}');self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],status)
            self.assertEqual(r.json()['data_fim'] is None,status=='ATIVO')
        with patch.object(self.db,'commit',side_effect=AssertionError('GET commit')),patch.object(self.db,'flush',side_effect=AssertionError('GET flush')):
            r=self.request();self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['itens'][0]['objetivos'][0]['status'],'CONCLUIDO')
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM pacientes')).scalar(),patients)
        self.assertEqual(self.client.get(self.path()).json()['clinical_reading'],before)
        self.assertEqual(self.db.execute(text('SELECT count(*) FROM agenda_cuidados')).scalar(),0)

    def test_one_active_and_reopen_conflict(self):
        first=self.create()
        self.assertEqual(self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Duplicate')).status_code,409)
        self.request('PUT',f"/{first['id']}/encerrar")
        second=self.create()
        self.assertEqual(self.request('PUT',f"/{first['id']}/reabrir").status_code,409)
        self.assertEqual(self.request().json()['itens'][0]['id'],second['id'])

    def test_wrong_scope_and_manipulated_ids(self):
        plan=self.create()
        for scope in (dict(person=self.person+9999),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.request(**scope).status_code,404)
            self.assertEqual(self.request('PUT',f"/{plan['id']}/encerrar",**scope).status_code,403)
        self.assertEqual(self.request('PUT','/999999/encerrar').status_code,403)
        self.assertEqual(self.request('PUT',f"/{plan['id']}/objetivos/999999",dict(status='CONCLUIDO')).status_code,403)
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed));self.db.commit()
        self.assertEqual(self.request(context=self.closed).json()['itens'],[])
        self.assertEqual(self.request('PUT',f"/{plan['id']}/encerrar",context=self.closed).status_code,403)

    def test_admin_no_bypass_and_read_only(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']));self.db.commit()
        self.assertFalse(self.request().json()['pode_registrar'])
        self.assertEqual(self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Denied')).status_code,403)
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_LER']));self.db.commit()
        self.assertEqual(self.request().status_code,404)
        self.assertEqual(self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Denied')).status_code,403)

    def test_inactive_line_and_rollback(self):
        with patch('app.services.pts_mental.PTSMentalService.output',side_effect=RuntimeError('synthetic')):
            self.assertEqual(self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Rollback')).status_code,500)
        self.assertEqual(self.request().json()['itens'],[])
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open));self.db.commit()
        self.assertEqual(self.request().status_code,404)
        self.assertEqual(self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Denied')).status_code,403)

    def test_client_cannot_supply_patient_line_author_or_context(self):
        for extra in ('paciente_id','modulo_id','contexto_assistencial_id','criado_por_usuario_id'):
            self.assertEqual(self.request('POST',payload=dict(data_inicio='2026-01-01',objetivo_geral='Forged',**{extra:999})).status_code,422)

    def test_legacy_reads_exclude_contextual_plan_and_objective_ids_cannot_cross(self):
        from app.services.pts_service import PTSService
        plan=self.create();first=self.request('POST',f"/{plan['id']}/objetivos",dict(descricao='Historical goal')).json()['objetivos'][0]['id']
        self.request('PUT',f"/{plan['id']}/encerrar")
        second=self.create()
        self.assertEqual(self.request('PUT',f"/{second['id']}/objetivos/{first}",dict(descricao='Cross plan')).status_code,403)
        self.assertEqual(PTSService.get_patient_pts(self.db,plan['paciente_id']),[])

    def test_context_closure_and_identity_changes_block_write(self):
        plan=self.create()
        cases=[('UPDATE usuarios SET ativo=false WHERE id=:i',self.actor),
               ('UPDATE pessoas SET ativo=false WHERE id=:i',self.person),
               ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i',self.links[0]),
               ('DELETE FROM contexto_profissionais WHERE id=:i',self.participations[self.open]),
               ('UPDATE contextos_assistenciais SET data_fim=CURRENT_DATE WHERE id=:i',self.open)]
        for sql,identity in cases:
            with self.subTest(sql=sql):
                self.db.execute(text(sql),dict(i=identity))
                self.assertEqual(self.request('PUT',f"/{plan['id']}/encerrar").status_code,403)

    def test_concurrent_creation_and_revocation(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event,Barrier
        from sqlalchemy.orm import Session
        from app.services.pts_mental import PTSMentalService,PTSDenied,PTSConflict
        from app.schemas.pts_mental import PTSMentalCreate
        payload=PTSMentalCreate(data_inicio='2026-01-01',objetivo_geral='Concurrent care')
        self.db.rollback()
        barrier=Barrier(2)
        def create():
            with Session(self.engine) as db:
                barrier.wait(timeout=5)
                try:
                    PTSMentalService().mutate(db,payload,actor=self.actor,institution=self.institution,person=self.person,context=self.open,action='create')
                    db.commit();return 'CREATED'
                except PTSConflict:db.rollback();return 'CONFLICT'
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(create) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=12) for f in futures),['CONFLICT','CREATED'])
        plan=self.request().json()['itens'][0]['id'];self.db.rollback()
        self.commands.revoke(self.db,dict(instituicao_id=self.institution,id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR'],motivo='Synthetic race'),actor_id=self.target)
        started=Event()
        def close():
            with Session(self.engine) as db:
                started.set()
                try:PTSMentalService().mutate(db,actor=self.actor,institution=self.institution,person=self.person,context=self.open,action='close',pts_id=plan)
                except PTSDenied:db.rollback();return 'DENIED'
                db.rollback();return 'UNEXPECTED'
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(close);self.assertTrue(started.wait(2));self.db.commit()
            self.assertEqual(future.result(timeout=12),'DENIED')
