"""3B.3A: canonical preparation and shared transport coordination; no real IO."""
import os
import unittest
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import select, text
from sqlalchemy.orm import Session
import test_whatsapp_convite_envio as fixture
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Attempt
from app.services.whatsapp_mental import WhatsAppMentalService
from app.services.whatsapp_comunicacao import coordinate, coordinate_configured
from app.services.whatsapp_manual import blocking_attempt
from app.services.checkin_bem_estar import CheckinInvalid

@unittest.skipUnless(fixture.foundation.URL, 'Owned disposable PostgreSQL required')
class PreparationLockTests(unittest.TestCase):
    setUpClass=classmethod(fixture.DeliveryTests.setUpClass.__func__)
    cleanup=classmethod(fixture.DeliveryTests.cleanup.__func__)
    snapshot=fixture.DeliveryTests.snapshot
    command_grant=fixture.DeliveryTests.command_grant
    path=fixture.DeliveryTests.path
    def setUp(self):
        fixture.DeliveryTests.setUp(self)
        c=self.db.get(Conversation,self.cid)
        self.aid=c.acompanhamento_whatsapp_id;self.phone=c.telefone
        self.emitter=os.environ['WHATSAPP_PHONE_NUMBER_ID']
        c.status='CONCLUIDA'
        self.db.get(Follow,self.aid).proximo_envio_em=None
        self.db.commit()
    def prepare(self,manual=False):
        c=self.service.prepare(self.db,self.aid,manual=manual)
        identity=c.id if c else None
        self.db.commit();return identity
    def other(self,expired=True):
        # Independent followup on an existing context; no changes to its eligibility.
        a=self.db.get(Follow,self.aid)
        f=Follow(contexto_assistencial_id=self.closed,paciente_id=a.paciente_id,
                 telefone=self.phone,criado_por_usuario_id=self.actor)
        self.db.add(f);self.db.flush()
        now=self.db.scalar(text('SELECT clock_timestamp()'))
        c=Conversation(acompanhamento_whatsapp_id=f.id,contexto_assistencial_id=self.closed,
          paciente_id=a.paciente_id,telefone=self.phone,data_referencia=now.date(),
          created_at=now-timedelta(days=2),expires_at=now+timedelta(days=-1 if expired else 1),status='AGUARDANDO_ACEITE')
        self.db.add(c);self.db.commit();return c.id,f.id
    def test_expired_other_followup_is_preserved_and_blocks_index(self):
        cid,aid=self.other()
        self.assertIsNone(self.prepare())
        self.assertEqual(self.db.get(Conversation,cid).status,'AGUARDANDO_ACEITE')
        self.assertIsNone(self.db.get(Follow,self.aid).proximo_envio_em)
        self.assertIsNone(self.db.get(Follow,aid).proximo_envio_em)
    def test_live_other_followup_is_preserved(self):
        cid,_=self.other(False)
        self.assertIsNone(self.prepare(True))
        self.assertEqual(self.db.get(Conversation,cid).status,'AGUARDANDO_ACEITE')
    def test_own_expiry_then_prepare(self):
        c=self.db.get(Conversation,self.cid);c.status='AGUARDANDO_ACEITE'
        now=self.db.scalar(text('SELECT clock_timestamp()'))
        c.created_at=now-timedelta(days=2);c.expires_at=now-timedelta(seconds=1)
        self.db.commit()
        self.assertIsNotNone(self.prepare())
        self.assertEqual(self.db.get(Conversation,self.cid).status,'EXPIRADA')
    def test_manual_future_preserves_schedule(self):
        a=self.db.get(Follow,self.aid);a.proximo_envio_em=self.now+timedelta(days=7)
        old=a.proximo_envio_em;self.db.commit()
        self.assertIsNone(self.prepare())
        self.assertIsNotNone(self.prepare(True))
        self.assertEqual(self.db.get(Follow,self.aid).proximo_envio_em,old)
    def test_automatic_advances_once(self):
        self.assertIsNotNone(self.prepare());old=self.db.get(Follow,self.aid).proximo_envio_em
        self.assertIsNone(self.prepare());self.assertEqual(self.db.get(Follow,self.aid).proximo_envio_em,old)
    def test_concurrent_prepare_one_conversation(self):
        self.db.rollback()
        def run(_):
            with Session(self.engine) as db:
                c=self.service.prepare(db,self.aid);identity=c.id if c else None;db.commit();return identity
        with ThreadPoolExecutor(2) as pool:values=list(pool.map(run,range(2)))
        self.assertEqual(sum(x is not None for x in values),1)
    def test_uncertain_same_followup_survives_emitter_change(self):
        self.db.add(Attempt(conversa_id=self.cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id='old-emitter',estado='INCERTO'))
        self.db.commit();self.assertIsNone(self.prepare(True))
    def test_uncertain_other_followup_exact_emitter(self):
        cid,_=self.other();self.db.get(Conversation,cid).status='EXPIRADA'
        self.db.add(Attempt(conversa_id=cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id=self.emitter,estado='INCERTO'))
        self.db.commit();self.assertIsNone(self.prepare(True))
    def test_other_emitter_not_identity(self):
        cid,_=self.other();self.db.get(Conversation,cid).status='EXPIRADA'
        self.db.add(Attempt(conversa_id=cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id='other',estado='INCERTO'))
        self.db.commit();self.assertIsNotNone(self.prepare(True))
    def test_preventive_block_no_schedule_change(self):
        from app.models.whatsapp_mensagem import WhatsAppMensagem
        from app.services.whatsapp_comunicacao import append,recipient_scope
        mid='synthetic-'+uuid4().hex
        self.db.add(WhatsAppMensagem(message_id=mid,phone_number_id=self.emitter,fingerprint='a'*64,resposta=''))
        self.db.flush()
        coordinate(self.db,self.emitter,self.phone)
        append(self.db,scope=recipient_scope(self.emitter,self.phone),emitter=self.emitter,phone=self.phone,
               state='INTERROMPIDA',key=uuid4().hex*2,fingerprint='b'*64,message=mid)
        self.db.commit();self.assertIsNone(self.prepare(True))
        self.assertIsNone(self.db.get(Follow,self.aid).proximo_envio_em)
    def race_preparation(self, owner, expected):
        import time
        self.db.rollback()
        def run():
            with Session(self.engine) as db:
                try:
                    c=self.service.prepare(db,self.aid);identity=c.id if c else None;db.commit();return identity
                except CheckinInvalid as exc:
                    db.rollback();return str(exc)
        with ThreadPoolExecutor(1) as pool:
            future=pool.submit(run)
            try:
                deadline=time.monotonic()+2
                observed=False
                while time.monotonic()<deadline:
                    with self.engine.connect() as probe:
                        observed=bool(probe.scalar(text("SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()")))
                    if observed: break
                    time.sleep(.01)
                self.assertTrue(observed,'PostgreSQL lock wait was not observed')
            finally:owner.commit()
            result=future.result(5)
        if expected=='created':self.assertIsInstance(result,int)
        else:self.assertEqual(result,expected)
    def test_concurrent_phone_change_revalidated(self):
        with Session(self.engine) as owner:
            self.service.configure(owner,'5511987650000',**self.scope)
            self.race_preparation(owner,'DESTINATION_CHANGED')
    def test_concurrent_revocation_blocks_prepare(self):
        from app.services.whatsapp_autorizacao import register
        from app.schemas.whatsapp_autorizacao import AuthorizationRevoke
        with Session(self.engine) as owner:
            register(owner,self.scope,uuid4().hex,AuthorizationRevoke(motivo='SOLICITACAO_TITULAR'),revoke=True)
            self.race_preparation(owner,None)
    def test_concurrent_authorization_then_prepare(self):
        from app.services.whatsapp_autorizacao import register
        from app.schemas.whatsapp_autorizacao import AuthorizationRevoke,AuthorizationCreate
        register(self.db,self.scope,uuid4().hex,AuthorizationRevoke(motivo='SOLICITACAO_TITULAR'),revoke=True)
        self.db.commit()
        with Session(self.engine) as owner:
            payload=AuthorizationCreate(origem='DOCUMENTO_ELETRONICO',obtida_em=owner.scalar(text('SELECT clock_timestamp()')),
                referencia_evidencia='synthetic-new-evidence',evidencia_sha256='b'*64,evidencia_verificada=True)
            register(owner,self.scope,uuid4().hex,payload)
            self.race_preparation(owner,'created')
    def test_absent_emitter_fails_before_preparation(self):
        with patch.dict(os.environ,{'WHATSAPP_PHONE_NUMBER_ID':''}):
            with self.assertRaisesRegex(CheckinInvalid,'EMITTER'):self.prepare()
        self.db.rollback()

    def alias_attempt(self,proof):
        cid,_=self.other()
        c=self.db.get(Conversation,cid);c.status='EXPIRADA'
        c.telefone='5511998765432'
        self.db.get(Follow,c.acompanhamento_whatsapp_id).telefone=c.telefone
        self.db.add(Attempt(conversa_id=cid,tentativa=1,correlacao_id=str(uuid4()),phone_number_id=self.emitter,estado='INCERTO'))
        if proof:
            from app.services.whatsapp_transporte import capture
            capture(self.db,{'messages':[{'id':'wamid.synthetic-'+uuid4().hex}],
                'contacts':[{'input':c.telefone,'wa_id':self.phone}]},emitter=self.emitter,
                requested=c.telefone,contextual=cid,origin='META_CONVITE')
        self.db.commit()
    def test_proven_alias_uncertain_attempt_blocks(self):
        self.alias_attempt(True);self.assertIsNone(self.prepare(True))
    def test_unproven_other_phone_is_not_identity(self):
        self.alias_attempt(False);self.assertIsNotNone(self.prepare(True))
    def test_expired_other_followup_not_in_automatic_candidates(self):
        self.other(True)
        self.assertNotIn(self.aid,self.service.eligible_ids(self.db))
