"""Explicit-reference decisions against canonical disposable PostgreSQL; no external calls."""
import unittest
from uuid import uuid4
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select, text
from sqlalchemy.orm import Session
import test_whatsapp_convite_envio as delivery
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Conversation
from app.services.whatsapp_ingress import process_message
from app.services.whatsapp_transporte import capture
from app.services.whatsapp_referencia import UNAVAILABLE


@unittest.skipUnless(delivery.foundation.URL, 'Exclusive disposable PostgreSQL required')
class ReferenceTests(unittest.TestCase):
    setUpClass=classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup=classmethod(delivery.DeliveryTests.cleanup.__func__)
    snapshot=delivery.DeliveryTests.snapshot
    command_grant=delivery.DeliveryTests.command_grant
    path=delivery.DeliveryTests.path

    def setUp(self):
        delivery.DeliveryTests.setUp(self)
        self.phone=self.db.get(Conversation,self.cid).telefone
        self.wa='556500000000'
        self.ref='wamid.'+uuid4().hex
        self.mid='inbound-'+uuid4().hex
        capture(self.db,{'messages':[{'id':self.ref}], 'contacts':[{'input':self.phone,'wa_id':self.wa}]},
                emitter='12345',requested=self.phone,contextual=self.cid,origin='META_CONVITE')
        self.db.commit()

    def receive(self, **changes):
        args=dict(identity=self.mid,recipient='12345',sender=self.wa,content='SIM',context_wamid=self.ref)
        args.update(changes)
        with patch('app.services.whatsapp_ingress.processar_mensagem',side_effect=AssertionError('NO FALLBACK')):
            return process_message(self.db,**args)

    def refused(self,reason,**changes):
        before=self.db.get(Conversation,self.cid).status
        self.assertEqual(self.receive(**changes),UNAVAILABLE)
        row=self.db.get(Receipt,self.mid)
        self.assertEqual((row.resolucao,row.resolucao_motivo),('REFERENCIA_RECUSADA',reason))
        self.assertIsNone(row.conversa_contextual_id)
        self.assertIsNone(row.conversa_legada_id)
        self.assertEqual(self.db.get(Conversation,self.cid).status,before)

    def test_mental_reference_with_meta_identity(self):
        answer=self.receive()
        self.assertNotEqual(answer,UNAVAILABLE)
        with Session(self.engine) as db:
            self.assertEqual(db.get(Conversation,self.cid).status,'EM_ANDAMENTO')
            row=db.get(Receipt,self.mid)
            self.assertEqual((row.resolucao,row.conversa_contextual_id,row.context_wamid),('REFERENCIA_CONTEXTUAL',self.cid,self.ref))

    def test_incompatible_sender(self):
        self.refused('IDENTIDADE_INCOMPATIVEL',sender='5511999999999')

    def test_different_emitter(self):
        self.refused('REFERENCIA_DESCONHECIDA',recipient='99999')

    def test_unknown_reference_never_falls_back(self):
        self.refused('REFERENCIA_DESCONHECIDA',context_wamid='wamid.unknown')

    def test_expired_reference(self):
        self.db.execute(text("UPDATE whatsapp_conversas_contextuais SET created_at=clock_timestamp()-interval '2 days',expires_at=clock_timestamp()-interval '1 day' WHERE id=:i"),{'i':self.cid});self.db.commit();self.db.expire_all()
        self.refused('CONVERSA_INDISPONIVEL')

    def test_closed_reference(self):
        self.db.get(Conversation,self.cid).status='CONCLUIDA';self.db.commit()
        self.refused('CONVERSA_INDISPONIVEL')

    def test_paused_follow(self):
        self.db.execute(text("UPDATE acompanhamentos_whatsapp SET status='PAUSADO' WHERE id=(SELECT acompanhamento_whatsapp_id FROM whatsapp_conversas_contextuais WHERE id=:i)"),{'i':self.cid});self.db.commit()
        self.refused('ACOMPANHAMENTO_INDISPONIVEL')

    def test_changed_follow_destination(self):
        self.db.execute(text("UPDATE acompanhamentos_whatsapp SET telefone='5511999999999' WHERE id=(SELECT acompanhamento_whatsapp_id FROM whatsapp_conversas_contextuais WHERE id=:i)"),{'i':self.cid});self.db.commit()
        self.refused('VINCULO_INCOMPATIVEL')

    def test_no_phone_equivalence_without_evidence(self):
        from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel
        row=self.db.scalar(select(WhatsAppMensagemRoteavel).where(WhatsAppMensagemRoteavel.wamid==self.ref))
        row.evidencia_estado='AUSENTE';row.wa_id=None;self.db.commit()
        self.refused('IDENTIDADE_INCOMPATIVEL')

    def test_absent_contacts_exact_destination(self):
        from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel
        row=self.db.scalar(select(WhatsAppMensagemRoteavel).where(WhatsAppMensagemRoteavel.wamid==self.ref))
        row.evidencia_estado='AUSENTE';row.wa_id=None;self.db.commit()
        self.assertNotEqual(self.receive(sender=self.phone),UNAVAILABLE)

    def test_replay_and_conflicting_context(self):
        answer=self.receive();self.assertEqual(self.receive(),answer)
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as err:self.receive(context_wamid='wamid.other')
        self.assertEqual(err.exception.status_code,409)
        self.assertEqual(self.db.get(Conversation,self.cid).etapa_atual,'humor')

    def test_concurrent_replay(self):
        self.db.rollback()
        def call(_):
            with Session(self.engine) as db:
                return process_message(db,self.mid,'12345',self.wa,'SIM',self.ref)
        with ThreadPoolExecutor(max_workers=2) as pool:answers=list(pool.map(call,range(2)))
        self.assertEqual(answers[0],answers[1])
        self.db.expire_all()
        self.assertEqual(self.db.query(Receipt).filter_by(message_id=self.mid).count(),1)

    def test_without_reference_keeps_dispatch(self):
        self.assertNotEqual(process_message(self.db,self.mid,'12345',self.phone,'SIM'),UNAVAILABLE)
        self.assertEqual(self.db.get(Receipt,self.mid).resolucao,'CONTEXTUAL_ATUAL')

    def test_parar_delegates_unchanged(self):
        self.receive(content='PARAR')
        self.assertEqual(self.db.get(Conversation,self.cid).status,'AGUARDANDO_ACEITE')
        self.assertEqual(self.db.execute(text('SELECT consentimento_status FROM acompanhamentos_whatsapp WHERE id=(SELECT acompanhamento_whatsapp_id FROM whatsapp_conversas_contextuais WHERE id=:i)'),{'i':self.cid}).scalar(),'PENDENTE')

    def test_parar_preserves_canonical_revocation_after_temporal_expiry(self):
        self.db.execute(text("UPDATE whatsapp_conversas_contextuais SET created_at=clock_timestamp()-interval '2 days',expires_at=clock_timestamp()-interval '1 day' WHERE id=:i"),{'i':self.cid});self.db.commit();self.db.expire_all()
        self.receive(content='PARAR')
        self.assertEqual(self.db.get(Conversation,self.cid).status,'AGUARDANDO_ACEITE')
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_contextual_id,self.cid)

    def test_receipt_and_clinical_atomic_rollback(self):
        with patch('app.services.whatsapp_mental.WhatsAppMentalService.receive',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):self.receive()
        self.assertIsNone(self.db.get(Receipt,self.mid))
        self.assertEqual(self.db.get(Conversation,self.cid).status,'AGUARDANDO_ACEITE')

    def test_reply_reference_uses_existing_transport_bridge(self):
        ref='wamid.'+uuid4().hex
        capture(self.db,{'messages':[{'id':ref}],'contacts':[{'input':self.wa,'wa_id':self.wa}]},emitter='12345',requested=self.wa,contextual=self.cid,origin='META_RESPOSTA');self.db.commit()
        self.assertNotEqual(self.receive(context_wamid=ref),UNAVAILABLE)

    def test_invalid_evidence_refused_even_for_exact_number(self):
        from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel
        row=self.db.scalar(select(WhatsAppMensagemRoteavel).where(WhatsAppMensagemRoteavel.wamid==self.ref))
        row.evidencia_estado='INVALIDA';row.wa_id=None;self.db.commit()
        self.refused('IDENTIDADE_INCOMPATIVEL',sender=self.phone)

    def test_evidence_for_different_destination_cannot_select_patient(self):
        from app.models.whatsapp_transporte import WhatsAppMensagemRoteavel
        row=self.db.scalar(select(WhatsAppMensagemRoteavel).where(WhatsAppMensagemRoteavel.wamid==self.ref))
        row.destinatario_solicitado='5511999999999';self.db.commit()
        self.refused('IDENTIDADE_INCOMPATIVEL')

    def test_signed_webhook_reference(self):
        import os
        import test_whatsapp_security as security
        from fastapi import FastAPI
        from app.routers import whatsapp
        from app.database import get_db
        app=FastAPI();app.include_router(whatsapp.router)
        def session():
            with Session(self.engine) as db:yield db
        app.dependency_overrides[get_db]=session
        payload=security.envelope('SIM',self.wa,self.mid)
        payload['entry'][0]['changes'][0]['value']['messages'][0]['context']={'id':self.ref}
        body=security.encoded(payload)
        with patch.dict(os.environ,dict(security.ENV,WHATSAPP_ACCESS_TOKEN='')):
            response=security.LocalClient(app).post('/whatsapp/webhook',content=body,headers={'X-Hub-Signature-256':security.signature(body)})
        self.assertEqual(response.status_code,200)
        self.db.expire_all()
        self.assertEqual(self.db.get(Receipt,self.mid).resolucao,'REFERENCIA_CONTEXTUAL')


@unittest.skipUnless(delivery.foundation.URL, 'Exclusive disposable PostgreSQL required')
class ReferenceMigrationTests(unittest.TestCase):
    setUpClass=classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup=classmethod(delivery.DeliveryTests.cleanup.__func__)

    def test_stage_one_receipt_preserved_and_new_decisions_constrained(self):
        from alembic import command
        from test_m0_baseline import config
        from sqlalchemy.exc import IntegrityError
        with self.engine.begin() as c:
            command.upgrade(config(c),'e14b1_transporte')
            c.execute(text("INSERT INTO whatsapp_mensagens(message_id,phone_number_id,fingerprint,fingerprint_versao,context_wamid,resolucao,resposta) VALUES ('stage-one','12345',:f,2,'wamid.old','LEGADO_SEM_CONVERSA','synthetic')"),{'f':'a'*64})
            before=dict(c.execute(text("SELECT * FROM whatsapp_mensagens WHERE message_id='stage-one'")).mappings().one())
            command.upgrade(config(c),'e14b2_referencia')
        with self.engine.connect() as c:
            after=dict(c.execute(text("SELECT * FROM whatsapp_mensagens WHERE message_id='stage-one'")).mappings().one())
            self.assertEqual({k:after[k] for k in before},before)
            self.assertIsNone(after['resolucao_motivo'])
            self.assertEqual(c.execute(text('SELECT version_num FROM alembic_version')).scalar(),'e14b2_referencia')
        with self.assertRaises(IntegrityError),self.engine.begin() as c:
            c.execute(text("UPDATE whatsapp_mensagens SET resolucao='REFERENCIA_CONTEXTUAL' WHERE message_id='stage-one'"))
