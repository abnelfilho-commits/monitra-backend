"""D9.2-C: signed HTTP callbacks with real disposable PostgreSQL persistence."""
import os
import json
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from sqlalchemy import select, text, event
from sqlalchemy.orm import Session
from fastapi import FastAPI
import test_whatsapp_convite_envio as foundation
import test_whatsapp_security as http
from app.database import get_db
from app.routers import whatsapp
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Envio, WhatsAppConviteStatusEvento as Evento
from app.services.whatsapp_convite_status import parse_statuses, persist_statuses
from app.services.whatsapp_sender_service import WhatsAppSenderService


@unittest.skipUnless(foundation.foundation.URL, 'Disposable PostgreSQL required')
class StatusTests(unittest.TestCase):
    setUpClass = classmethod(foundation.DeliveryTests.setUpClass.__func__)
    cleanup = classmethod(foundation.DeliveryTests.cleanup.__func__)
    snapshot = foundation.DeliveryTests.snapshot
    command_grant = foundation.DeliveryTests.command_grant
    path = foundation.DeliveryTests.path
    response = foundation.DeliveryTests.response
    send = foundation.DeliveryTests.send

    def setUp(self):
        foundation.DeliveryTests.setUp(self)
        env = patch.dict(os.environ, {'WHATSAPP_APP_SECRET':http.ENV['WHATSAPP_APP_SECRET']})
        env.start(); self.addCleanup(env.stop)
        self.app = FastAPI(); self.app.include_router(whatsapp.router)
        def session():
            with Session(self.engine) as db: yield db
        self.app.dependency_overrides[get_db] = session
        self.client = http.LocalClient(self.app)

    def status(self, state='sent', **changes):
        data = dict(id=self.wamid,status=state,timestamp='1792706700',recipient_id='PRIVATE_RECIPIENT')
        data.update(changes); return data

    def payload(self, statuses, messages=None, emitter='12345'):
        value={'metadata':{'phone_number_id':emitter},'statuses':statuses}
        if messages is not None: value['messages']=messages
        return {'object':'whatsapp_business_account','entry':[{'changes':[{'field':'messages','value':value}]}]}

    def post(self, statuses, **kwargs):
        body=http.encoded(self.payload(statuses, **kwargs))
        return self.client.post('/whatsapp/webhook',content=body,headers={'X-Hub-Signature-256':http.signature(body)})

    def bind(self, emitter='12345'):
        e=Envio(conversa_id=self.cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id=emitter,
                wamid=self.wamid,estado='ACEITO',confirmado_em=self.now)
        self.db.add(e);self.db.commit(); identity=e.id;self.db.rollback();return identity

    def rows(self):
        with self.engine.connect() as c:
            return [dict(r) for r in c.execute(text('SELECT * FROM whatsapp_convite_status_eventos WHERE wamid=:w ORDER BY id'),{'w':self.wamid}).mappings()]

    def test_sent_delivered_read_failed_and_no_clinical_changes(self):
        identity=self.bind();before=self.snapshot()
        with patch.object(WhatsAppSenderService,'enviar_texto') as reply, patch.object(WhatsAppSenderService,'enviar_template') as invitation:
            for state in ('sent','delivered','read','failed'):
                data=self.status(state)
                if state=='failed':data['errors']=[{'code':131000,'error_subcode':7,'message':'PRIVATE_CONTENT','error_data':{'details':'SECRET_TOKEN'}}]
                r=self.post([data]);self.assertEqual(r.status_code,200,r.text)
                self.assertEqual(r.json(),{'status':'processed'})
            reply.assert_not_called(); invitation.assert_not_called()
        rows=self.rows();self.assertEqual(len(rows),4)
        self.assertTrue(all(r['envio_id']==identity for r in rows))
        self.assertEqual(rows[-1]['meta_error_code'],131000)
        self.assertEqual(rows[-1]['motivo_sanitizado'],'META_ERROR_131000')
        self.assertNotIn('PRIVATE',str(rows));self.assertNotIn('SECRET',str(rows))
        self.assertEqual({k:v[1] for k,v in before.items()},{k:v[1] for k,v in self.snapshot().items()})
        with Session(self.engine) as db: self.assertEqual(db.get(Envio,identity).estado,'ACEITO')

    def test_duplicate_and_error_order_deduplicated(self):
        data=self.status('failed',errors=[{'code':2},{'code':1},{'code':2}])
        self.assertEqual(self.post([data,data]).status_code,200)
        data['errors'].reverse()
        self.assertEqual(self.post([data]).status_code,200)
        rows=self.rows();self.assertEqual(len(rows),2)
        self.assertEqual({r['meta_error_code'] for r in rows},{1,2})

    def test_out_of_order_and_contradiction_retained(self):
        for state,stamp in (('read','1792706900'),('delivered','1792706800'),('sent','1792706700'),('failed','1792706800')):
            self.assertEqual(self.post([self.status(state,timestamp=stamp)]).status_code,200)
        self.assertEqual({r['status'] for r in self.rows()},{'sent','delivered','read','failed'})
        self.assertTrue(all(r['evento_em'].tzinfo is not None and r['recebido_em'].tzinfo is not None for r in self.rows()))

    def test_unknown_wamid_and_wrong_emitter_never_guessed(self):
        self.bind(emitter='other-emitter')
        self.assertEqual(self.post([self.status()]).status_code,200)
        self.assertIsNone(self.rows()[0]['envio_id'])

    def test_early_callback_correlated_by_real_acceptance(self):
        self.assertEqual(self.post([self.status()]).status_code,200)
        self.assertIsNone(self.rows()[0]['envio_id'])
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()):
            self.assertTrue(self.send())
        self.assertIsNotNone(self.rows()[0]['envio_id'])
        self.assertEqual(self.post([self.status()]).status_code,200)
        self.assertEqual(len(self.rows()),1)

    def test_multiple_entries_statuses_and_mixed_real_message(self):
        message={'id':'incoming-'+uuid4().hex,'from':'5511999999999','type':'text','text':{'body':'oi'}}
        payload=self.payload([self.status('sent')],messages=[message])
        payload['entry'].extend(self.payload([self.status('delivered')])['entry'])
        body=http.encoded(payload)
        with patch.object(WhatsAppSenderService,'enviar_texto',return_value={'messages':[{'id':'wamid.synthetic-reply'}]}) as reply, patch.object(WhatsAppSenderService,'enviar_template') as invite:
            for _ in range(2):
                r=self.client.post('/whatsapp/webhook',content=body,headers={'X-Hub-Signature-256':http.signature(body)})
                self.assertEqual(r.status_code,200,r.text)
            reply.assert_called_once();invite.assert_not_called()
        self.assertEqual(len(self.rows()),2)
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM whatsapp_mensagens WHERE message_id=:i'),{'i':message['id']}).scalar(),1)

    def test_batch_failure_rollback_and_retry_before_messages(self):
        message={'id':'incoming-'+uuid4().hex,'from':'5511999999999','type':'text','text':{'body':'oi'}}
        inserts=0
        def fail(conn,cursor,statement,params,context,many):
            nonlocal inserts
            if statement.startswith('INSERT INTO whatsapp_convite_status_eventos'):
                inserts+=1
                if inserts==2:raise RuntimeError('PRIVATE_DATABASE_ERROR')
        event.listen(self.engine,'before_cursor_execute',fail)
        try:
            with self.assertLogs(whatsapp.logger,level='ERROR') as logs, patch.object(whatsapp,'process_message') as incoming:
                r=self.post([self.status('sent'),self.status('delivered')],messages=[message])
                self.assertEqual(r.status_code,503);incoming.assert_not_called()
                self.assertNotIn('PRIVATE_DATABASE_ERROR',str(logs.output))
        finally:event.remove(self.engine,'before_cursor_execute',fail)
        self.assertEqual(self.rows(),[])
        self.assertEqual(self.post([self.status('sent'),self.status('delivered')]).status_code,200)
        self.assertEqual(len(self.rows()),2)

    def test_commit_ack_lost_retry_deduplicates(self):
        with self.engine.connect() as c: pass
        original=Session.commit
        def lost(db):
            original(db)
            raise RuntimeError('lost acknowledgement')
        with patch.object(Session,'commit',lost):
            self.assertEqual(self.post([self.status()]).status_code,503)
        self.assertEqual(len(self.rows()),1)
        self.assertEqual(self.post([self.status()]).status_code,200)
        self.assertEqual(len(self.rows()),1)

    def test_concurrent_callback_deduplication(self):
        self.bind()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.post([self.status()]).status_code,range(2)))
        self.assertEqual(results,[200,200]);self.assertEqual(len(self.rows()),1)

    def test_signature_and_recipient_rejected_without_persistence(self):
        body=http.encoded(self.payload([self.status()]))
        self.assertEqual(self.client.post('/whatsapp/webhook',content=body,headers={'X-Hub-Signature-256':'sha256=invalid'}).status_code,403)
        self.assertEqual(self.post([self.status()],emitter='wrong').status_code,403)
        self.assertEqual(self.rows(),[])

    def test_invalid_batch_rejects_before_any_processing(self):
        for mutation in ({'id':'bad'}, {'timestamp':'NaN'}, {'timestamp':'999999999999'},
                         {'errors':[{'code':True}]}, {'errors':None}):
            with self.subTest(mutation=mutation), patch.object(whatsapp,'process_message') as incoming:
                r=self.post([self.status(),self.status(**mutation)])
                self.assertEqual(r.status_code,400,r.text);incoming.assert_not_called()
        self.assertEqual(self.rows(),[])

    def test_acceptance_racing_callback_uses_same_key_lock(self):
        held=Event();release=Event()
        def pause(conn,cursor,statement,params,context,many):
            if statement.startswith('SELECT pg_advisory_xact_lock') and not held.is_set():
                held.set()
                if not release.wait(10):raise AssertionError('timeout')
        event.listen(self.engine,'after_cursor_execute',pause)
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                callback=pool.submit(lambda:self.post([self.status()]))
                self.assertTrue(held.wait(10))
                def sender():
                    with Session(self.engine) as db, patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()):
                        return self.send(db)
                send=pool.submit(sender)
                release.set()
                self.assertEqual(callback.result(timeout=15).status_code,200)
                self.assertTrue(send.result(timeout=15))
        finally:
            release.set();event.remove(self.engine,'after_cursor_execute',pause)
        self.assertIsNotNone(self.rows()[0]['envio_id'])
