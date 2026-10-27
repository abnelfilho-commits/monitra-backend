"""E14B.1 stage 1: evidence only, no contextual routing activation."""
import hashlib
import json
import os
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic import command
import test_whatsapp_convite_envio as delivery
import test_whatsapp_security as security
from test_m0_baseline import config
from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel as Message
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.services.whatsapp_transporte import capture, contact_evidence
from app.services.whatsapp_ingress import authenticated_events, process_message, deliver_reply


class ContractTests(unittest.TestCase):
    def test_optional_contacts(self):
        for result in ({}, {'contacts':None}):
            self.assertEqual(contact_evidence(result, '5511000000000'), ('AUSENTE',None))

    def test_verified_transport_difference(self):
        self.assertEqual(contact_evidence({'contacts':[{'input':'5565900000000','wa_id':'556500000000'}]}, '5565900000000'), ('VALIDA','556500000000'))

    def test_ambiguous_invalid_contacts(self):
        for contacts in ([], [1], {}, [{'input':'other','wa_id':'5511000000000'}],
                         [{'input':'5511000000000','wa_id':'invalid'}],
                         [{'input':'5511000000000'}], [{},{}]):
            self.assertEqual(contact_evidence({'contacts':contacts},'5511000000000'), ('INVALIDA',None))

    def test_authenticated_context_is_optional_and_preserved(self):
        for context in (None, {'id':'wamid.original'}):
            payload=security.envelope('SIM')
            if context: payload['entry'][0]['changes'][0]['value']['messages'][0]['context']=context
            body=security.encoded(payload)
            with patch.dict(os.environ,security.ENV):
                messages,_=authenticated_events(body,security.signature(body))
            self.assertEqual(len(messages[0]),5 if context else 4)
            if context:self.assertEqual(messages[0][-1],'wamid.original')

    def test_forwarded_context_without_reference(self):
        payload=security.envelope();payload['entry'][0]['changes'][0]['value']['messages'][0]['context']={'forwarded':True}
        body=security.encoded(payload)
        with patch.dict(os.environ,security.ENV):
            messages,_=authenticated_events(body,security.signature(body))
        self.assertIsNone(messages[0][-1])

    def test_invalid_context_rejected(self):
        from fastapi import HTTPException
        for value in ({'id':'bad'}, 'bad'):
            payload=security.envelope();payload['entry'][0]['changes'][0]['value']['messages'][0]['context']=value
            body=security.encoded(payload)
            with patch.dict(os.environ,security.ENV), self.assertRaises(HTTPException) as err:
                authenticated_events(body,security.signature(body))
            self.assertEqual(err.exception.status_code,400)


@unittest.skipUnless(delivery.foundation.URL, 'Exclusive disposable PostgreSQL required')
class TransportPostgresTests(unittest.TestCase):
    setUpClass=classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup=classmethod(delivery.DeliveryTests.cleanup.__func__)
    snapshot=delivery.DeliveryTests.snapshot
    command_grant=delivery.DeliveryTests.command_grant
    path=delivery.DeliveryTests.path
    setUp=delivery.DeliveryTests.setUp
    send=delivery.DeliveryTests.send
    response=delivery.DeliveryTests.response

    def evidence(self, db=None, **changes):
        values=dict(emitter='12345',requested='5511000000000',contextual=self.cid,origin='META_CONVITE')
        values.update(changes)
        return capture(db or self.db, {'messages':[{'id':self.wamid}], 'contacts':[{'input':values['requested'],'wa_id':'551100000000'}]}, **values)

    def test_invitation_capture_valid_and_independent_connection(self):
        phone=self.db.execute(text('select telefone from whatsapp_conversas_contextuais where id=:i'),{'i':self.cid}).scalar_one()
        body={'messages':[{'id':self.wamid}], 'contacts':[{'input':phone,'wa_id':'551100000000'}]}
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response(body=body)):
            self.assertTrue(self.send())
        with Session(self.engine) as db:
            m=db.scalar(select(Message).where(Message.wamid==self.wamid))
            self.assertEqual((m.evidencia_estado,m.wa_id,m.conversa_contextual_id),('VALIDA','551100000000',self.cid))
            self.assertEqual(m.destinatario_solicitado,phone)
            self.assertIsNotNone(m.observado_em)

    def test_invitation_old_response_preserved(self):
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()):self.assertTrue(self.send())
        with Session(self.engine) as db:
            m=db.scalar(select(Message).where(Message.wamid==self.wamid))
            self.assertEqual((m.evidencia_estado,m.wa_id),('AUSENTE',None))

    def test_invalid_optional_evidence_does_not_reject_acceptance(self):
        body={'messages':[{'id':self.wamid}],'contacts':[{'input':'wrong','wa_id':'551100000000'}]}
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response(body=body)):self.assertTrue(self.send())
        self.assertEqual(self.db.scalar(select(Message).where(Message.wamid==self.wamid)).evidencia_estado,'INVALIDA')

    def test_capture_idempotent_and_conflicting_replay(self):
        first=self.evidence();self.db.commit();identity=first.id
        self.assertEqual(self.evidence().id,identity);self.db.commit()
        with self.assertRaisesRegex(ValueError,'Transport evidence conflict'):
            self.evidence(origin='META_RESPOSTA')
        self.db.rollback()
        self.assertEqual(self.db.scalar(select(Message).where(Message.id==identity)).origem,'META_CONVITE')

    def test_concurrent_capture_single_row(self):
        self.db.rollback()
        def work(_):
            with Session(self.engine) as db:
                row=self.evidence(db);identity=row.id;db.commit();return identity
        with ThreadPoolExecutor(max_workers=2) as pool: ids=list(pool.map(work,range(2)))
        self.assertEqual(ids[0],ids[1])

    def test_foreign_key_and_exclusive_conversation(self):
        for change in ({'contextual':2147483647},{'contextual':None},{'legacy':2147483647}):
            with self.assertRaises(IntegrityError): self.evidence(**change)
            self.db.rollback()

    def test_receipt_without_context_and_replay(self):
        phone=self.db.execute(text('select telefone from whatsapp_conversas_contextuais where id=:i'),{'i':self.cid}).scalar_one()
        mid='receipt-'+uuid4().hex
        response=process_message(self.db,mid,'12345',phone,'SIM')
        row=self.db.get(Receipt,mid)
        self.assertEqual((row.context_wamid,row.fingerprint_versao,row.resolucao,row.conversa_contextual_id),(None,2,'CONTEXTUAL_ATUAL',self.cid))
        self.assertEqual(process_message(self.db,mid,'12345',phone,'SIM'),response)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):process_message(self.db,mid,'12345',phone,'SIM','wamid.changed')
        self.assertEqual(self.db.execute(text('select status from whatsapp_conversas_contextuais where id=:i'),{'i':self.cid}).scalar_one(),'EM_ANDAMENTO')

    def test_v1_receipt_preserved(self):
        mid='old-'+uuid4().hex
        f=hashlib.sha256(json.dumps(['12345','5511000000000','SIM'],ensure_ascii=False).encode()).hexdigest()
        self.db.add(Receipt(message_id=mid,phone_number_id='12345',fingerprint=f,resposta='old',fingerprint_versao=1));self.db.commit()
        with patch('app.services.whatsapp_mental.dispatch',side_effect=AssertionError('must not reroute')):
            self.assertEqual(process_message(self.db,mid,'12345','5511000000000','SIM','wamid.old'),'old')
        self.assertEqual(self.db.get(Receipt,mid).resolucao,'HISTORICO')

    def test_text_response_evidence(self):
        phone=self.db.execute(text('select telefone from whatsapp_conversas_contextuais where id=:i'),{'i':self.cid}).scalar_one()
        mid='reply-'+uuid4().hex;process_message(self.db,mid,'12345',phone,'SIM')
        result={'messages':[{'id':self.wamid}],'contacts':[{'input':phone,'wa_id':'551100000000'}]}
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',return_value=result) as send:
            deliver_reply(self.db,mid,phone);deliver_reply(self.db,mid,phone)
            send.assert_called_once()
        self.assertEqual(self.db.scalar(select(Message).where(Message.wamid==self.wamid)).origem,'META_RESPOSTA')

    def test_text_capture_failure_never_resends(self):
        phone=self.db.execute(text('select telefone from whatsapp_conversas_contextuais where id=:i'),{'i':self.cid}).scalar_one()
        mid='reply-'+uuid4().hex;process_message(self.db,mid,'12345',phone,'SIM')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',return_value={'messages':[{'id':self.wamid}]}) as send:
            with patch('app.services.whatsapp_transporte.capture',side_effect=RuntimeError('synthetic')),self.assertRaises(RuntimeError):deliver_reply(self.db,mid,phone)
            deliver_reply(self.db,mid,phone);send.assert_called_once()

    def test_rollback_evidence(self):
        self.evidence();self.db.rollback()
        with Session(self.engine) as db:self.assertIsNone(db.scalar(select(Message).where(Message.wamid==self.wamid)))

    def test_model_and_index_preserved(self):
        inspector=inspect(self.engine)
        self.assertEqual({x['name'] for x in inspector.get_columns(Message.__tablename__)},set(Message.__table__.c.keys()))
        self.assertTrue(any(x['name']=='ix_wcc_aberta_telefone' and not x['unique'] for x in inspector.get_indexes('whatsapp_conversas_contextuais')))


@unittest.skipUnless(delivery.foundation.URL, 'Exclusive disposable PostgreSQL required')
class MigrationTests(unittest.TestCase):
    setUpClass=classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup=classmethod(delivery.DeliveryTests.cleanup.__func__)

    def test_existing_receipts_preserved(self):
        with self.engine.begin() as c:
            command.upgrade(config(c),'d92e12c_autorizacao_whatsapp')
            c.execute(text("INSERT INTO whatsapp_mensagens(message_id,phone_number_id,fingerprint,resposta) VALUES ('synthetic-history','12345',:f,'synthetic reply')"),{'f':'a'*64})
            before=dict(c.execute(text("SELECT * FROM whatsapp_mensagens WHERE message_id='synthetic-history'")).mappings().one())
            command.upgrade(config(c),'e14b1_transporte')
        with self.engine.connect() as c:
            after=dict(c.execute(text("SELECT * FROM whatsapp_mensagens WHERE message_id='synthetic-history'")).mappings().one())
            self.assertEqual({k:after[k] for k in before},before)
            self.assertEqual((after['fingerprint_versao'],after['resolucao'],after['context_wamid']),(1,'HISTORICO',None))
            self.assertEqual(c.execute(text('SELECT count(*) FROM whatsapp_mensagens_roteaveis')).scalar(),0)
