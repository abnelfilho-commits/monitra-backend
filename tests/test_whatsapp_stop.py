"""PARAR integration: real disposable PostgreSQL; all HTTP forbidden by fixture."""
import json
import unittest
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Pending
from threading import Event as Signal
from unittest.mock import patch
from sqlalchemy import select, text, func
from sqlalchemy.orm import Session
import test_whatsapp_comunicacao as fixture
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_resolucao import WhatsAppResolucao as Audit
from app.models.whatsapp_comunicacao import WhatsAppComunicacaoEvento as Event, WhatsAppRespostaExecucao as Execution
from app.services.whatsapp_ingress import process_message
from app.services.whatsapp_comunicacao import read, reactivate, blocked
from app.services.whatsapp_stop import RESPONSE, BLOCKED
from app.services.whatsapp_resposta import deliver


@unittest.skipUnless(fixture.delivery.foundation.URL, 'Owned disposable PostgreSQL required')
class StopTests(unittest.TestCase):
    setUpClass=classmethod(fixture.CommunicationTests.setUpClass.__func__)
    cleanup=classmethod(fixture.CommunicationTests.cleanup.__func__)
    setUp=fixture.CommunicationTests.setUp
    snapshot=fixture.CommunicationTests.snapshot
    command_grant=fixture.CommunicationTests.command_grant
    path=fixture.CommunicationTests.path
    legacy=fixture.CommunicationTests.legacy
    proof=fixture.CommunicationTests.proof
    payload=fixture.CommunicationTests.payload
    receipt=fixture.CommunicationTests.receipt

    def incoming(self, content='PARAR', ref=None, mid=None, sender=None, emitter=None, db=None):
        self.mid=mid or 'synthetic-stop-'+uuid4().hex
        return process_message(db or self.db,self.mid,emitter or self.emitter,sender or self.sender,content,ref)

    def state(self):
        return read(self.db,self.scope)

    def event(self):
        return self.db.scalar(select(Event).where(Event.mensagem_id==self.mid))

    def assert_preserved(self, before):
        self.assertEqual({k:v[1] for k,v in before.items() if k != 'whatsapp_mensagens'}, {k:v[1] for k,v in self.snapshot().items() if k != 'whatsapp_mensagens'})

    def test_contextual_reference(self):
        ref=self.proof();before=self.snapshot()
        self.assertEqual(self.incoming(ref=ref),RESPONSE)
        self.assert_preserved(before)
        self.assertEqual(self.event().acompanhamento_id,self.db.get(Conversation,self.cid).acompanhamento_whatsapp_id)
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_contextual_id,self.cid)
        self.assertFalse(self.db.get(Audit,self.mid).decisao['clinical_execution'])

    def test_expired_reference_current_followup(self):
        ref=self.proof()
        self.db.execute(text("UPDATE whatsapp_conversas_contextuais SET created_at=clock_timestamp()-interval '2 days',expires_at=clock_timestamp()-interval '1 day',status='EXPIRADA' WHERE id=:i"),{'i':self.cid});self.db.commit()
        before=self.snapshot();self.incoming(ref=ref)
        self.assert_preserved(before);self.assertEqual(len(self.state()['eventos']),1)

    def test_completed_reference_current_followup(self):
        ref=self.proof();self.db.get(Conversation,self.cid).status='CANCELADA';self.db.commit()
        self.incoming(ref=ref);self.assertEqual(len(self.state()['eventos']),1)
        self.assertEqual(self.db.get(Conversation,self.cid).status,'CANCELADA')

    def test_unreferenced_unique(self):
        self.incoming();self.assertEqual(len(self.state()['eventos']),1)
        self.assertIsNone(self.db.get(Receipt,self.mid).conversa_contextual_id)
        self.assertEqual(self.db.get(Audit,self.mid).decisao['outcome'],'PARAR_ACOMPANHAMENTO')

    def test_invalid_reference_no_fallback(self):
        before=self.snapshot();self.incoming(ref='wamid.unknown')
        self.assert_preserved(before);self.assertTrue(self.state()['bloqueio_preventivo'])
        self.assertEqual(self.state()['eventos'],[])

    def test_wrong_sender_does_not_interrupt_target(self):
        ref=self.proof();other='5510'+str(self.cid).zfill(8)
        self.incoming(ref=ref,sender=other)
        self.assertIsNone(self.event().acompanhamento_id)
        self.assertTrue(blocked(self.db,self.emitter,other))
        self.assertEqual(self.state()['estado'],'SEM_INTERRUPCAO_REGISTRADA')

    def test_wrong_emitter_does_not_select_target(self):
        ref=self.proof();self.incoming(ref=ref,emitter='98765')
        self.assertIsNone(self.event().acompanhamento_id)
        self.assertFalse(blocked(self.db,self.emitter,self.sender))

    def test_brazilian_variants_need_evidence(self):
        self.sender=self.phone[:4]+self.phone[5:] if len(self.phone)==13 else self.phone+'1'
        self.incoming();self.assertIsNone(self.event().acompanhamento_id)
        self.assertFalse(blocked(self.db,self.emitter,self.phone))

    def test_proven_alias_selects_context(self):
        self.sender='5510'+str(self.cid).zfill(8);ref=self.proof()
        self.incoming(ref=ref);self.assertIsNotNone(self.event().acompanhamento_id)

    def test_contradictory_evidence_preventive(self):
        ref=self.proof();self.sender='5510'+str(self.cid).zfill(8);self.proof()
        self.incoming(ref=ref);self.assertIsNone(self.event().acompanhamento_id)
        self.assertEqual(self.db.get(Audit,self.mid).decisao['outcome'],'IDENTIDADE_INCOMPATIVEL')

    def test_neuro_ambiguity_no_individual_event(self):
        self.legacy();self.incoming()
        self.assertTrue(self.state()['bloqueio_preventivo']);self.assertEqual(self.state()['eventos'],[])

    def test_cardio_ambiguity_no_individual_event(self):
        self.legacy(line='CARDIO');self.incoming()
        self.assertTrue(self.state()['bloqueio_preventivo']);self.assertEqual(self.state()['eventos'],[])

    def legacy_reference(self,line):
        from app.services.whatsapp_transporte import capture
        c=self.legacy(line=line);before=(c.etapa_atual,c.paciente_id,c.care_line,c.data_referencia)
        ref='wamid.'+uuid4().hex
        capture(self.db,{'messages':[{'id':ref}],'contacts':[{'input':self.phone,'wa_id':self.phone}]},emitter=self.emitter,requested=self.phone,legacy=c.id,origin='META_RESPOSTA');self.db.commit()
        self.incoming(ref=ref)
        self.assertEqual((c.etapa_atual,c.paciente_id,c.care_line,c.data_referencia),before)
        self.assertIsNone(self.event().acompanhamento_id);self.assertEqual(self.state()['eventos'],[])

    def test_neuro_reference_protects_transport(self): self.legacy_reference('NEURO')
    def test_cardio_reference_protects_transport(self): self.legacy_reference('CARDIO')

    def test_inactive_link_does_not_attribute_person(self):
        ref=self.proof();self.db.execute(text('UPDATE paciente_instituicoes SET ativo=false WHERE id=(SELECT paciente_instituicao_id FROM contextos_assistenciais WHERE id=:i)'),{'i':self.open});self.db.commit()
        self.incoming(ref=ref);self.assertIsNone(self.event().acompanhamento_id)

    def test_whitespace_case_classification(self):
        self.incoming('  parar \n');self.assertIsNotNone(self.event())

    def test_sim_blocked_after_contextual_stop(self):
        self.incoming();self.assertEqual(self.incoming('SIM'),BLOCKED)
        self.assertEqual(self.db.get(Conversation,self.cid).status,'AGUARDANDO_ACEITE')
        self.assertEqual(self.db.get(Follow,self.db.get(Conversation,self.cid).acompanhamento_whatsapp_id).consentimento_status,'PENDENTE')

    def test_sim_blocked_after_preventive_stop(self):
        c=self.legacy();before=c.etapa_atual;self.incoming()
        self.assertEqual(self.incoming('SIM'),BLOCKED);self.assertEqual(c.etapa_atual,before)

    def test_explicit_reactivation_then_sim(self):
        self.incoming();reactivate(self.db,self.scope,uuid4().hex,self.payload());self.db.commit()
        self.incoming('SIM');self.assertEqual(self.db.get(Conversation,self.cid).status,'EM_ANDAMENTO')
        self.assertEqual([e['tipo'] for e in self.state()['eventos']],['COMUNICACAO_WHATSAPP_INTERROMPIDA','COMUNICACAO_WHATSAPP_REATIVADA'])

    def test_duplicate_replay_after_reactivation_no_new_interruption(self):
        mid='synthetic-'+uuid4().hex;self.incoming(mid=mid)
        reactivate(self.db,self.scope,uuid4().hex,self.payload());self.db.commit()
        self.incoming(mid=mid);self.assertEqual(self.state()['estado'],'SEM_INTERRUPCAO_REGISTRADA')
        self.assertEqual(len(self.state()['eventos']),2)

    def test_sim_cannot_remove_recipient_barrier(self):
        self.incoming();self.legacy();self.incoming()
        reactivate(self.db,self.scope,uuid4().hex,self.payload());self.db.commit()
        self.incoming('SIM');self.assertTrue(self.state()['bloqueio_preventivo'])
        self.assertEqual(self.db.get(Conversation,self.cid).status,'AGUARDANDO_ACEITE')

    def test_fingerprint_conflict(self):
        from fastapi import HTTPException
        mid='synthetic-'+uuid4().hex;self.incoming(mid=mid)
        with self.assertRaises(HTTPException) as error:self.incoming(ref='wamid.other',mid=mid)
        self.assertEqual(error.exception.status_code,409)
        self.assertEqual(len(self.state()['eventos']),1)

    def test_rollback_before_commit(self):
        mid='synthetic-'+uuid4().hex
        with patch.object(self.db,'commit',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):self.incoming(mid=mid)
        with Session(self.engine) as db:
            self.assertIsNone(db.get(Receipt,mid));self.assertIsNone(db.get(Audit,mid))
            self.assertIsNone(db.scalar(select(Event).where(Event.mensagem_id==mid)))

    def test_concurrent_duplicate(self):
        mid='synthetic-'+uuid4().hex;self.db.rollback()
        def call(_):
            with Session(self.engine) as db:return process_message(db,mid,self.emitter,self.sender,'PARAR')
        with ThreadPoolExecutor(2) as pool:self.assertEqual(list(pool.map(call,range(2))),[RESPONSE,RESPONSE])
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Event).where(Event.mensagem_id==mid)),1)

    def test_no_reply_after_stop(self):
        self.incoming()
        with patch('app.services.whatsapp_sender_service.requests.post') as http:
            self.assertFalse(deliver(self.db,self.mid,self.sender));http.assert_not_called()

    def test_ingress_does_not_execute_clinical_handlers_for_stop(self):
        with patch('app.services.whatsapp_mental.WhatsAppMentalService.receive') as mental,patch('app.services.whatsapp_ingress.processar_mensagem') as legacy:
            self.incoming();mental.assert_not_called();legacy.assert_not_called()

    def test_direct_receivers_refuse_unaudited_stop(self):
        from app.services.whatsapp_conversation_service import processar_mensagem
        from app.services.checkin_bem_estar import CheckinInvalid
        with self.assertRaisesRegex(CheckinInvalid,'STOP_REQUIRES'):self.service.receive(self.db,self.cid,'PARAR')
        with self.assertRaisesRegex(CheckinInvalid,'STOP_REQUIRES'):processar_mensagem(self.db,self.sender,'PARAR')

    def test_audit_contains_no_transport_or_clinical_content(self):
        ref=self.proof();self.incoming(ref=ref)
        value=json.dumps(self.db.get(Audit,self.mid).decisao)
        for secret in (self.phone,ref,'respostas_json','humor'):self.assertNotIn(secret,value)

    def test_two_mental_followups_preventive(self):
        from app.models.contexto_assistencial import ContextoAssistencial as Context
        from datetime import timedelta
        original=self.db.get(Conversation,self.cid)
        context=self.db.get(Context,self.contexts[1]);context.ativo=True;context.data_fim=None
        from app.models.contexto_assistencial import ContextoAssistencialLinha
        self.db.add(ContextoAssistencialLinha(contexto_assistencial_id=context.id,modulo_id=3,ativo=True))
        follow=Follow(contexto_assistencial_id=context.id,paciente_id=original.paciente_id,
            telefone=self.phone,criado_por_usuario_id=self.actor)
        self.db.add(follow);self.db.flush()
        now=self.db.scalar(select(func.clock_timestamp()))
        self.db.add(Conversation(acompanhamento_whatsapp_id=follow.id,contexto_assistencial_id=context.id,
            paciente_id=original.paciente_id,telefone=self.phone,data_referencia=now.date(),
            created_at=now-timedelta(days=2),expires_at=now-timedelta(days=1),status='EXPIRADA'))
        self.db.commit();self.incoming()
        self.assertIsNone(self.event().acompanhamento_id);self.assertEqual(self.state()['eventos'],[])

    def test_multiple_invitations_same_followup_one_context_event(self):
        from datetime import timedelta
        c=self.db.get(Conversation,self.cid);now=self.db.scalar(select(func.clock_timestamp()))
        self.db.add(Conversation(acompanhamento_whatsapp_id=c.acompanhamento_whatsapp_id,
            contexto_assistencial_id=c.contexto_assistencial_id,paciente_id=c.paciente_id,
            telefone=c.telefone,data_referencia=now.date(),created_at=now-timedelta(days=3),
            expires_at=now-timedelta(days=2),status='EXPIRADA'))
        self.db.commit();self.incoming()
        self.assertEqual(len(self.state()['eventos']),1)
        self.assertIsNone(self.db.get(Receipt,self.mid).conversa_contextual_id)

    def test_stop_does_not_require_prior_authorization_to_withdraw(self):
        from app.services.whatsapp_autorizacao import register
        from app.schemas.whatsapp_autorizacao import AuthorizationRevoke
        register(self.db,self.scope,uuid4().hex,AuthorizationRevoke(motivo='SOLICITACAO_TITULAR'),revoke=True);self.db.commit()
        self.incoming();self.assertEqual(len(self.state()['eventos']),1)

    def test_stop_serializes_before_preparation(self):
        from app.services import whatsapp_stop
        c=self.db.get(Conversation,self.cid);aid=c.acompanhamento_whatsapp_id
        c.status='CONCLUIDA';self.db.get(Follow,aid).proximo_envio_em=None;self.db.commit()
        entered=Signal();release=Signal();original=whatsapp_stop.persist
        def hold(*args):
            result=original(*args);entered.set();self.assertTrue(release.wait(5));return result
        def stop():
            with Session(self.engine) as db:return process_message(db,'race-'+uuid4().hex,self.emitter,self.sender,'PARAR')
        def prepare():
            with Session(self.engine) as db:
                result=self.service.prepare(db,aid);db.commit();return result
        with patch.object(whatsapp_stop,'persist',side_effect=hold),ThreadPoolExecutor(2) as pool:
            running=pool.submit(stop);self.assertTrue(entered.wait(5))
            next_=pool.submit(prepare)
            try:
                with self.assertRaises(Pending):next_.result(.15)
            finally:release.set()
            self.assertEqual(running.result(5),RESPONSE);self.assertIsNone(next_.result(5))

    def test_stop_between_invitation_prepare_and_execution(self):
        original=self.db.commit;count=0
        def commit():
            nonlocal count
            count+=1;original()
            if count==1:
                with Session(self.engine) as db:process_message(db,'race-'+uuid4().hex,self.emitter,self.sender,'PARAR')
        from app.services.checkin_bem_estar import CheckinInvalid
        with patch.object(self.db,'commit',side_effect=commit),patch('app.services.whatsapp_sender_service.requests.post') as http:
            with self.assertRaisesRegex(CheckinInvalid,'WHATSAPP_INTERROMPIDO'):
                self.service.deliver_invitation(self.db,self.cid,context=self.scope)
            http.assert_not_called()
        self.db.rollback()
        from app.models.whatsapp_convite import WhatsAppConviteEnvio as Attempt
        self.assertEqual(self.db.scalar(select(Attempt).where(Attempt.conversa_id==self.cid)).estado,'PREPARADO')

    def test_stop_during_uncertain_external_execution_no_retry(self):
        entered=Signal();release=Signal()
        def remote(*a,**kw):
            entered.set();self.assertTrue(release.wait(5));raise TimeoutError('simulated uncertain result')
        def send():
            with Session(self.engine) as db:return self.service.deliver_invitation(db,self.cid,context=self.scope)
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_template',side_effect=remote) as http,ThreadPoolExecutor(1) as pool:
            running=pool.submit(send);self.assertTrue(entered.wait(5))
            try:self.incoming()
            finally:release.set()
            with self.assertRaises(TimeoutError):running.result(5)
            http.assert_called_once()
        from app.models.whatsapp_convite import WhatsAppConviteEnvio as Attempt
        self.assertEqual(self.db.scalar(select(Attempt).where(Attempt.conversa_id==self.cid)).estado,'INCERTO');self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post') as http:
            from app.services.checkin_bem_estar import CheckinInvalid
            with self.assertRaisesRegex(CheckinInvalid,'WHATSAPP_INTERROMPIDO'):
                self.service.deliver_invitation(self.db,self.cid,context=self.scope,explicit_retry=True)
            http.assert_not_called()

    def test_reactivation_serializes_before_new_stop(self):
        self.incoming();reactivate(self.db,self.scope,uuid4().hex,self.payload())
        def stop():
            with Session(self.engine) as db:return process_message(db,'race-'+uuid4().hex,self.emitter,self.sender,'PARAR')
        with ThreadPoolExecutor(1) as pool:
            running=pool.submit(stop)
            try:
                with self.assertRaises(Pending):running.result(.15)
            finally:self.db.commit()
            self.assertEqual(running.result(5),RESPONSE)
        self.assertEqual(self.state()['estado'],'WHATSAPP_INTERROMPIDO')
        self.assertEqual(len(self.state()['eventos']),3)

    def test_webhook_invalid_hmac_does_not_process_stop(self):
        from app.services.whatsapp_ingress import authenticated_events
        from fastapi import HTTPException
        with patch.dict('os.environ',{'WHATSAPP_APP_SECRET':'synthetic-secret','WHATSAPP_PHONE_NUMBER_ID':self.emitter}):
            with self.assertRaises(HTTPException) as error:authenticated_events(b'{}','sha256=invalid')
        self.assertEqual(error.exception.status_code,403)
        self.assertEqual(self.state()['eventos'],[])

    def test_legacy_navigation_not_created_by_stop(self):
        from app.models.whatsapp_conversa import WhatsAppConversa as Legacy
        before=self.db.scalar(select(func.count()).select_from(Legacy))
        self.incoming(sender='5500'+str(self.cid).zfill(8))
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Legacy)),before)
        self.assertIsNone(self.event().acompanhamento_id)

    def test_stop_replay_version_one_preserved(self):
        from app.services.whatsapp_comunicacao import digest
        mid='historical-'+uuid4().hex
        self.db.add(Receipt(message_id=mid,phone_number_id=self.emitter,
            fingerprint=digest(json.dumps([self.emitter,self.sender,'PARAR'],ensure_ascii=False)),
            fingerprint_versao=1,resposta='historical result'))
        self.db.commit();self.assertEqual(self.incoming(mid=mid),'historical result')
        self.assertEqual(self.state()['eventos'],[])

    def test_conflicting_proof_stop_ack_does_not_retry_reply(self):
        from app.routers.whatsapp import process_validated
        ref=self.proof();self.sender='5510'+str(self.cid).zfill(8);self.proof()
        mid='synthetic-'+uuid4().hex
        with patch('app.services.whatsapp_sender_service.requests.post') as http:
            result=process_validated(self.db,[(mid,self.emitter,self.sender,'PARAR',ref)])
            self.assertEqual(result,{'status':'processed'});http.assert_not_called()
        self.assertIsNotNone(self.db.get(Audit,mid))

    def test_e12c_ledger_exactly_preserved(self):
        def ledger():
            return self.db.execute(text('SELECT row_to_json(t)::text FROM whatsapp_autorizacoes_comunicacao t ORDER BY id')).scalars().all()
        before=ledger();self.incoming();self.incoming('SIM')
        self.assertEqual(ledger(),before)
