"""E12: real authorization ledger and PostgreSQL; only Meta is simulated."""
import os
import unittest
from uuid import uuid4
from datetime import timedelta
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from contextlib import nullcontext
from sqlalchemy import select, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.schemas.whatsapp_manual import ManualRequest
from app.models.whatsapp_manual import WhatsAppSolicitacaoManual as Manual
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio
from app.services.whatsapp_manual import dispatch_manual, require_prior_authorization
from app.services.checkin_bem_estar import CheckinInvalid, CheckinDenied
import test_whatsapp_convite_persistence as foundation
import test_whatsapp_convite_envio as delivery_fixture


class ContractTests(unittest.TestCase):
    def test_body_whitelist(self):
        for extra in ('telefone','template','autor','synthetic_time','bypass','consentimento'):
            with self.assertRaises(ValidationError):
                ManualRequest(motivo='SOLICITACAO_DA_PESSOA', **{extra: 'invalid'})
        with self.assertRaises(ValidationError): ManualRequest(motivo='FREE_TEXT')

@unittest.skipUnless(foundation.URL, 'Explicit disposable PostgreSQL required')
class ManualTests(unittest.TestCase):
    create_prior_authorization = False
    setUpClass = classmethod(foundation.PersistenceTests.setUpClass.__func__)
    cleanup = classmethod(foundation.PersistenceTests.cleanup.__func__)
    snapshot = foundation.PersistenceTests.snapshot
    command_grant = foundation.PersistenceTests.command_grant
    path = foundation.PersistenceTests.path
    response = delivery_fixture.DeliveryTests.response

    def setUp(self):
        delivery_fixture.DeliveryTests.setUp(self)
        c = self.db.get(Conversation, self.cid)
        c.status = 'CONCLUIDA'
        self.aid = c.acompanhamento_whatsapp_id
        self.follow = self.db.get(Follow, self.aid)
        self.follow.proximo_envio_em = self.now + timedelta(days=7)
        self.db.commit()
        self.original_schedule = self.follow.proximo_envio_em
        self.db.rollback()
        self.key = uuid4().hex
        self.payload = ManualRequest(motivo='ACOMPANHAMENTO_EXTRAORDINARIO')

    def invoke(self, db=None, key=None, payload=None, scope=None):
        return dispatch_manual(db or self.db, scope or self.scope, key or self.key, payload or self.payload)

    def allowed(self):
        from app.services.whatsapp_autorizacao import latest
        if latest(self.db,self.aid) is None:
            from whatsapp_authorization_fixture import authorize_follow
            authorize_follow(self.db,self.scope)
        self.db.rollback()
        return nullcontext()

    def schedule(self):
        with Session(self.engine) as db: return db.get(Follow, self.aid).proximo_envio_em

    def test_future_schedule_and_exact_replay(self):
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post', return_value=self.response()) as post:
            first = self.invoke()
            again = self.invoke()
            self.assertEqual(first, again)
            self.assertEqual(first['estado'], 'ACEITO'); post.assert_called_once()
        self.assertEqual(self.schedule(), self.original_schedule)
        with Session(self.engine) as db:
            m = db.get(Manual, first['solicitacao_id'])
            self.assertEqual((m.usuario_id,m.instituicao_id,m.acompanhamento_id),(self.actor,self.institution,self.aid))
            self.assertEqual(db.get(Envio,m.tentativa_id).conversa_id,m.conversa_id)
            self.assertEqual(m.template_nome, os.environ['WHATSAPP_MENTAL_TEMPLATE_NAME'])
            self.assertEqual(db.get(Follow,self.aid).consentimento_status,'PENDENTE')

    def test_configured_weekly_preferences_unchanged_by_manual_and_replay(self):
        from app.schemas.whatsapp_mental import WhatsAppProgramacao
        from app.services.whatsapp_programacao import configure
        self.allowed()
        configure(self.db, WhatsAppProgramacao(dia_semana=4, horario_local='19:00', programacao_ativa=True), **self.scope)
        self.db.commit()
        fields = ('dia_semana','horario_local','programacao_ativa','proximo_envio_em','configurado_por_usuario_id')
        before = tuple(getattr(self.db.get(Follow,self.aid),field) for field in fields)
        self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post', return_value=self.response()) as post:
            first = self.invoke()
            self.assertEqual(first['estado'], 'ACEITO')
            self.assertEqual(self.invoke(), first)
            post.assert_called_once()
        with Session(self.engine) as db:
            self.assertEqual(tuple(getattr(db.get(Follow,self.aid),field) for field in fields), before)

    def test_null_schedule(self):
        self.follow.proximo_envio_em=None;self.db.commit()
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post', return_value=self.response()):
            self.assertEqual(self.invoke()['estado'],'ACEITO')
        self.assertIsNone(self.schedule())

    def test_automatic_future_and_due_behavior(self):
        self.allowed()
        self.assertIsNone(self.service.prepare(self.db,self.aid));self.db.rollback()
        self.follow=self.db.get(Follow,self.aid)
        self.follow.proximo_envio_em=None;self.db.commit()
        c=self.service.prepare(self.db,self.aid);self.assertIsNotNone(c)
        self.db.commit();self.assertGreater(self.schedule(),self.now)

    def test_production_optin_gate_has_zero_writes(self):
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaisesRegex(CheckinInvalid,'PRIOR_WHATSAPP_AUTHORIZATION_ABSENT'): self.invoke()
            self.db.rollback();post.assert_not_called()
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(Manual.id).where(Manual.acompanhamento_id==self.aid)))
        self.assertEqual(self.schedule(),self.original_schedule)

    def test_changed_content_conflicts(self):
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            self.invoke()
            with self.assertRaisesRegex(CheckinInvalid,'IDEMPOTENCY_CONFLICT'):
                self.invoke(payload=ManualRequest(motivo='SOLICITACAO_DA_PESSOA'))
            self.db.rollback();post.assert_called_once()

    def test_revocation_and_pause(self):
        self.allowed()
        for field,value in (('consentimento_status','REVOGADO'),('status','PAUSADO')):
            f=self.db.get(Follow,self.aid);setattr(f,field,value);self.db.commit()
            with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post') as post:
                with self.assertRaisesRegex(CheckinInvalid,'FOLLOW_UP_NOT_ELIGIBLE'): self.invoke()
                self.db.rollback();post.assert_not_called()
            setattr(self.db.get(Follow,self.aid),field,'PENDENTE' if field=='consentimento_status' else 'ATIVO');self.db.commit()

    def test_denied_write_and_wrong_institution(self):
        self.allowed()
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(CheckinDenied): self.invoke(scope=dict(self.scope,institution=2147483647))
            self.db.rollback()
            self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'), {'i':self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']});self.db.commit()
            with self.assertRaises(CheckinDenied): self.invoke()
            self.db.rollback();post.assert_not_called()

    def test_uncertain_prior_cycle_blocks_manual_and_automatic(self):
        self.db.add(Envio(conversa_id=self.cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id='test',estado='INCERTO'))
        self.db.commit()
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaisesRegex(CheckinInvalid,'INVITATION_NOT_ELIGIBLE'):self.invoke()
            self.db.rollback()
            self.assertIsNone(self.service.prepare(self.db,self.aid));self.db.rollback();post.assert_not_called()

    def test_timeout_replay_never_resends(self):
        import requests
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post',side_effect=requests.Timeout()) as post:
            first=self.invoke();again=self.invoke()
            self.assertEqual(first,again);self.assertEqual(first['estado'],'INCERTO');post.assert_called_once()

    def test_concurrent_manual_same_key_and_automatic(self):
        entered,release=Event(),Event()
        def remote(*args,**kwargs):
            entered.set()
            if not release.wait(10):raise AssertionError('timeout')
            return self.response()
        def run():
            with Session(self.engine) as db:return self.invoke(db)
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post',side_effect=remote) as post, ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(run)
            try:
                self.assertTrue(entered.wait(10))
                duplicate=pool.submit(run).result(timeout=10)
                self.assertEqual(duplicate['estado'],'EM_EXECUCAO')
                with Session(self.engine) as db:
                    self.assertIsNone(self.service.prepare(db,self.aid));db.rollback()
            finally:release.set()
            self.assertEqual(first.result(timeout=10)['estado'],'ACEITO');post.assert_called_once()

    def test_concurrent_different_keys(self):
        entered,release=Event(),Event()
        def remote(*a,**kw):
            entered.set();self.assertTrue(release.wait(10));return self.response()
        def run(key):
            with Session(self.engine) as db:
                try:return self.invoke(db,key=key)
                finally:db.rollback()
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post',side_effect=remote) as post, ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(run,self.key)
            try:
                self.assertTrue(entered.wait(10))
                with self.assertRaises(CheckinInvalid):pool.submit(run,uuid4().hex).result(timeout=10)
            finally:release.set()
            self.assertEqual(first.result(timeout=10)['estado'],'ACEITO');post.assert_called_once()

    def test_prepared_request_survives_interruption(self):
        with self.allowed(), patch.object(type(self.service),'deliver_invitation',side_effect=RuntimeError('interrupted')):
            first=self.invoke()
        self.assertEqual(first['estado'],'PREPARADO')
        with self.allowed(),patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertEqual(first,self.invoke());post.assert_not_called()
        with Session(self.engine) as db:
            c=db.get(Conversation,first['conversa_id']);c.status='EXPIRADA';db.commit()
            self.assertIsNone(self.service.prepare(db,self.aid));db.rollback()

    def test_schema_matches_and_rejects_missing_parent(self):
        columns={c['name'] for c in inspect(self.engine).get_columns(Manual.__tablename__)}
        self.assertEqual(columns,set(Manual.__table__.c.keys()))
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.add(Manual(instituicao_id=2147483647,acompanhamento_id=self.aid,usuario_id=self.actor,
                chave=self.key,motivo=self.payload.motivo,conversa_id=self.cid,template_nome='test',template_idioma='pt_BR'))
            self.db.flush()

    def test_failed_131049_and_delayed_duplicate_preserve_care(self):
        from app.services.whatsapp_convite_status import parse_statuses, persist_statuses
        from app.models.whatsapp_convite import WhatsAppConviteStatusEvento as Evento
        with self.allowed(), patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()):
            out=self.invoke()
        failed=dict(id=self.wamid,status='failed',timestamp=str(int(self.now.timestamp())),errors=[{'code':131049}])
        events=parse_statuses({'statuses':[failed]},os.environ['WHATSAPP_PHONE_NUMBER_ID'])
        persist_statuses(self.db,events);persist_statuses(self.db,events)
        sent=dict(id=self.wamid,status='sent',timestamp=str(int(self.now.timestamp())-10))
        persist_statuses(self.db,parse_statuses({'statuses':[sent]},os.environ['WHATSAPP_PHONE_NUMBER_ID']))
        with Session(self.engine) as db:
            self.assertEqual(db.get(Envio,out['tentativa_id']).estado,'ACEITO')
            rows=list(db.scalars(select(Evento).where(Evento.envio_id==out['tentativa_id'])))
            self.assertEqual(len(rows),2)
            self.assertEqual([x.meta_error_code for x in rows if x.status=='failed'],[131049])
            self.assertEqual(db.get(Conversation,out['conversa_id']).status,'AGUARDANDO_ACEITE')
            self.assertEqual(db.get(Follow,self.aid).consentimento_status,'PENDENTE')
        self.assertEqual(self.schedule(),self.original_schedule)

    def test_request_commit_ack_lost_no_external_call_or_replay(self):
        commit=self.db.commit
        def lost():commit();raise RuntimeError('ack lost')
        with self.allowed(),patch.object(self.db,'commit',side_effect=lost),patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(RuntimeError):self.invoke()
            post.assert_not_called()
        self.db.rollback()
        with self.allowed(),patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertEqual(self.invoke()['estado'],'PREPARADO');post.assert_not_called()

    def test_http_contract_and_optin_denial(self):
        import json
        from app.routers.whatsapp_mental import router
        self.app.include_router(router)
        path=f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp/disparar-manual'
        def call(body,headers=None):
            return self.client.request('POST',path,body=json.dumps(body).encode(),params={'instituicao_id':self.institution},
                headers={'Content-Type':'application/json',**(headers or {})})
        self.assertEqual(call(self.payload.model_dump()).status_code,422)
        headers={'Idempotency-Key':self.key}
        self.assertEqual(call(dict(self.payload.model_dump(),telefone='forbidden'),headers).status_code,422)
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            denied=call(self.payload.model_dump(),headers)
            self.assertEqual(denied.status_code,409)
            self.assertEqual(denied.json()['detail']['code'],'PRIOR_WHATSAPP_AUTHORIZATION_ABSENT');post.assert_not_called()
        with self.allowed(),patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            self.assertEqual(call(self.payload.model_dump(),headers).status_code,200)
            self.assertEqual(call(self.payload.model_dump(),headers).status_code,200);post.assert_called_once()

    def test_automatic_conversation_blocks_manual(self):
        self.allowed()
        self.follow=self.db.get(Follow,self.aid);self.follow.proximo_envio_em=None;self.db.commit()
        self.assertIsNotNone(self.service.prepare(self.db,self.aid));self.db.commit()
        with self.allowed(),patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaisesRegex(CheckinInvalid,'INVITATION_NOT_ELIGIBLE'):self.invoke()
            self.db.rollback();post.assert_not_called()

    def test_changed_phone_cannot_bypass_uncertain_followup(self):
        self.db.add(Envio(conversa_id=self.cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id='test',estado='INCERTO'))
        self.db.get(Follow,self.aid).telefone='5599'+str(self.cid).zfill(9)
        self.db.commit()
        with self.allowed(),patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaisesRegex(CheckinInvalid,'INVITATION_NOT_ELIGIBLE'):self.invoke()
            self.db.rollback();post.assert_not_called()

    def test_http_authentication_required(self):
        from fastapi import FastAPI
        from app.routers.whatsapp_mental import router
        from test_whatsapp_security import LocalClient
        app=FastAPI();app.include_router(router)
        r=LocalClient(app).request('POST',f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp/disparar-manual',
            params={'instituicao_id':self.institution},body=b'{"motivo":"SOLICITACAO_DA_PESSOA"}',
            headers={'Content-Type':'application/json','Idempotency-Key':self.key})
        self.assertIn(r.status_code,(401,403))
