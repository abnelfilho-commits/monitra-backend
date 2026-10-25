"""D9.2-B: actual disposable PostgreSQL; Meta HTTP is always simulated."""
import os
import unittest
from uuid import uuid4
from threading import Event
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
import requests
from sqlalchemy import select, text
from sqlalchemy.orm import Session
import test_whatsapp_convite_persistence as foundation
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio, WhatsAppConviteStatusEvento as Evento
from app.services.whatsapp_mental import WhatsAppMentalService
from app.services.whatsapp_convite_envio import capture_wamid
from app.services.whatsapp_sender_service import MetaInvitationRejected
from test_whatsapp_invitation_diagnostics import ENV


class ResponseContractTests(unittest.TestCase):
    def test_individual_identifier(self):
        self.assertEqual(capture_wamid({'messages':[{'id':'wamid.abc=='}]}), 'wamid.abc==')
        for data in (None, {}, {'messages':[]}, {'messages':[{'id':'wamid.a'},{'id':'wamid.b'}]},
                     {'messages':[{'id':'not-a-wamid'}]}, {'messages':[{'id':'wamid.a\n'}]},
                     {'messages':[{'id':1}]}, {'messages':[{'id':'wamid.'+'a'*507}]}):
            with self.subTest(data=data), self.assertRaises(ValueError): capture_wamid(data)


@unittest.skipUnless(foundation.URL, 'Disposable PostgreSQL required')
class DeliveryTests(unittest.TestCase):
    setUpClass = classmethod(foundation.PersistenceTests.setUpClass.__func__)
    cleanup = classmethod(foundation.PersistenceTests.cleanup.__func__)
    snapshot = foundation.PersistenceTests.snapshot
    command_grant = foundation.PersistenceTests.command_grant
    path = foundation.PersistenceTests.path

    def setUp(self):
        foundation.PersistenceTests.setUp(self)
        phone = '5511'+str(self.cid).zfill(9)
        self.db.execute(text('UPDATE acompanhamentos_whatsapp SET telefone=:p WHERE contexto_assistencial_id=:c'), {'p':phone,'c':self.open})
        self.db.execute(text("UPDATE whatsapp_conversas_contextuais SET status='AGUARDANDO_ACEITE', telefone=:p WHERE id=:i"), {'i':self.cid,'p':phone})
        self.db.commit()
        self.scope = dict(actor=self.actor, institution=self.institution, person=self.person, context=self.open)
        self.wamid = 'wamid.'+uuid4().hex
        self.env = patch.dict(os.environ, ENV); self.env.start(); self.addCleanup(self.env.stop)
        self.service = WhatsAppMentalService()
        if getattr(self, 'create_prior_authorization', True):
            from whatsapp_authorization_fixture import authorize_follow
            authorize_follow(self.db, self.scope)

    def send(self, db=None, retry=False):
        return self.service.deliver_invitation(db or self.db,self.cid,context=self.scope,explicit_retry=retry)

    def response(self, status=200, body=None):
        r=Mock(ok=status<400, status_code=status)
        r.json.return_value=body if body is not None else {'messages':[{'id':self.wamid}]}
        return r

    def states(self):
        with Session(self.engine) as db:
            return [(e.estado,e.wamid,e.graph_http_status) for e in db.scalars(select(Envio).where(Envio.conversa_id==self.cid).order_by(Envio.tentativa))]

    def test_acceptance_durable_no_http_transaction_and_repeat_blocked(self):
        commits=[]
        from sqlalchemy import event
        def observed(session):
            with self.engine.connect() as c:
                commits.append(c.execute(text('SELECT estado FROM whatsapp_convite_envios WHERE conversa_id=:i ORDER BY tentativa DESC LIMIT 1'), {'i':self.cid}).scalar())
        event.listen(self.db,'after_commit',observed); self.addCleanup(event.remove,self.db,'after_commit',observed)
        def remote(*a,**kw):
            self.assertFalse(self.db.in_transaction())
            self.assertEqual(self.states()[0][0],'EM_EXECUCAO')
            return self.response()
        with patch('app.services.whatsapp_sender_service.requests.post',side_effect=remote) as post:
            self.assertTrue(self.send())
            self.assertFalse(self.send(retry=True)); post.assert_called_once()
        self.assertEqual(commits,['PREPARADO','EM_EXECUCAO','ACEITO'])
        self.assertEqual(self.states(),[('ACEITO',self.wamid,200)])
        with self.engine.connect() as c:
            row=c.execute(text('SELECT c.status, c.convite_enviado_em=e.confirmado_em AS same_time FROM whatsapp_conversas_contextuais c JOIN whatsapp_convite_envios e ON e.conversa_id=c.id WHERE c.id=:i'), {'i':self.cid}).one()
            self.assertEqual(row.status, 'AGUARDANDO_ACEITE')
            self.assertTrue(row.same_time)

    def test_explicit_rejection_and_manual_retry(self):
        r=self.response(400,{'error':{'code':132001,'error_subcode':1,'message':'DO NOT STORE'}})
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=r):
            with self.assertRaises(MetaInvitationRejected): self.send()
        self.assertEqual(self.states()[0][0],'REJEITADO')
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            self.assertFalse(self.send()); post.assert_not_called()
            self.assertTrue(self.send(retry=True)); post.assert_called_once()
        self.assertEqual([r[0] for r in self.states()],['REJEITADO','ACEITO'])

    def test_timeout_uncertain_blocks_retries(self):
        with patch('app.services.whatsapp_sender_service.requests.post',side_effect=requests.Timeout('private')):
            with self.assertRaises(requests.Timeout): self.send()
        self.assertEqual(self.states()[0][0],'INCERTO')
        with Session(self.engine) as db, patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertFalse(self.send(db,retry=True)); post.assert_not_called()

    def test_success_without_identifier_uncertain(self):
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response(body={'messages':[]})):
            with self.assertRaises(ValueError): self.send()
        self.assertEqual(self.states()[0][0],'INCERTO')

    def test_server_error_is_not_proven_rejection(self):
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response(500,{'error':{'code':1}})):
            with self.assertRaises(RuntimeError): self.send()
        self.assertEqual(self.states()[0][0],'INCERTO')

    def test_commit_failure_after_acceptance(self):
        original=self.db.commit; count=0
        def commit():
            nonlocal count
            count+=1
            if count>=3: raise RuntimeError('database unavailable')
            return original()
        with patch.object(self.db,'commit',side_effect=commit), patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            with self.assertRaises(RuntimeError): self.send()
            post.assert_called_once()
        self.assertEqual(self.states()[0][0],'EM_EXECUCAO')
        with Session(self.engine) as db, patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertFalse(self.send(db,retry=True)); post.assert_not_called()

    def test_failed_acceptance_commit_marks_uncertain_when_database_recovers(self):
        original=self.db.commit; count=0
        def commit():
            nonlocal count
            count+=1
            if count==3: raise RuntimeError('commit failed before persistence')
            return original()
        with patch.object(self.db,'commit',side_effect=commit), patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()):
            with self.assertRaises(RuntimeError): self.send()
        self.assertEqual(self.states()[0][0],'INCERTO')
        with self.engine.connect() as c:
            self.assertIsNone(c.execute(text('SELECT convite_enviado_em FROM whatsapp_conversas_contextuais WHERE id=:i'), {'i':self.cid}).scalar())

    def test_running_commit_failure_does_not_call_meta(self):
        original=self.db.commit; count=0
        def commit():
            nonlocal count
            count+=1
            if count==2: raise RuntimeError('cannot persist running state')
            return original()
        with patch.object(self.db,'commit',side_effect=commit), patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(RuntimeError): self.send()
            post.assert_not_called()
        self.db.rollback()
        self.assertEqual(self.states()[0][0],'PREPARADO')

    def test_authorization_revoked_after_preparation(self):
        from app.services.checkin_bem_estar import CheckinDenied
        original=self.db.commit; count=0
        def commit():
            nonlocal count
            count+=1; original()
            if count==1:
                with self.engine.begin() as c:
                    c.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'), {'i':self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']})
        with patch.object(self.db,'commit',side_effect=commit), patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(CheckinDenied): self.send()
            post.assert_not_called()
        self.db.rollback(); self.assertEqual(self.states()[0][0],'PREPARADO')

    def test_lost_commit_ack_keeps_acceptance(self):
        original=self.db.commit; count=0
        def commit():
            nonlocal count
            count+=1; original()
            if count==3: raise RuntimeError('ack lost')
        with patch.object(self.db,'commit',side_effect=commit), patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()):
            with self.assertRaises(RuntimeError): self.send()
        self.assertEqual(self.states()[0][0],'ACEITO')

    def test_restart_with_prepared_or_running_attempt(self):
        for state in ('PREPARADO','EM_EXECUCAO'):
            with self.subTest(state=state):
                with Session(self.engine) as db:
                    previous=db.scalar(select(Envio).where(Envio.conversa_id==self.cid))
                    if previous: previous.estado=state
                    else: db.add(Envio(conversa_id=self.cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id=ENV['WHATSAPP_PHONE_NUMBER_ID'],estado=state))
                    db.commit()
                with Session(self.engine) as db, patch('app.services.whatsapp_sender_service.requests.post') as post:
                    self.assertFalse(self.send(db,retry=True));post.assert_not_called()

    def test_concurrent_requests_one_external_call(self):
        entered=Event(); release=Event()
        def remote(*a,**kw):
            entered.set()
            if not release.wait(10): raise AssertionError('concurrency timeout')
            return self.response()
        def run():
            with Session(self.engine) as db: return self.send(db,retry=True)
        with patch('app.services.whatsapp_sender_service.requests.post',side_effect=remote) as post, ThreadPoolExecutor(max_workers=2) as pool:
            first=pool.submit(run)
            try:
                self.assertTrue(entered.wait(10))
                self.assertFalse(pool.submit(run).result(timeout=10))
            finally: release.set()
            self.assertTrue(first.result(timeout=10));post.assert_called_once()

    def test_early_event_exact_pair_only(self):
        def remote(*a,**kw):
            with Session(self.engine) as db:
                for emitter in (ENV['WHATSAPP_PHONE_NUMBER_ID'],'other'):
                    db.add(Evento(phone_number_id=emitter,wamid=self.wamid,status='sent',evento_em=self.now,deduplicacao_chave=uuid4().hex+uuid4().hex))
                db.commit()
            return self.response()
        with patch('app.services.whatsapp_sender_service.requests.post',side_effect=remote): self.assertTrue(self.send())
        with Session(self.engine) as db:
            rows=list(db.scalars(select(Evento).where(Evento.wamid==self.wamid)))
            self.assertEqual([e.envio_id is not None for e in sorted(rows,key=lambda e:e.phone_number_id)], [True,False])

    def test_authorization_rechecked_before_external_call(self):
        from app.services.checkin_bem_estar import CheckinDenied
        self.db.execute(text("DELETE FROM concessoes_assistenciais WHERE id=:i"), {'i':self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']}); self.db.commit()
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(CheckinDenied): self.send()
            post.assert_not_called()
        self.db.rollback(); self.assertEqual(self.states(),[])
