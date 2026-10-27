"""Communication infrastructure only: owned PostgreSQL, simulated Meta."""
import os
import json
import unittest
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from threading import Event as Signal
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from sqlalchemy import select, text, inspect, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import test_whatsapp_multilinhas as multi
import test_whatsapp_convite_envio as delivery
from app.models.whatsapp_comunicacao import WhatsAppComunicacaoEvento as Event, WhatsAppRespostaExecucao as Execution
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Conversation, AcompanhamentoWhatsApp as Follow
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.services.whatsapp_comunicacao import interrupt, read, reactivate, require_output, coordinate, digest, blocked
from app.services.checkin_bem_estar import CheckinInvalid, CheckinDenied
from app.services.whatsapp_resposta import deliver, evidence
from app.schemas.whatsapp_autorizacao import AuthorizationCreate


@unittest.skipUnless(delivery.foundation.URL,'Owned disposable PostgreSQL required')
class CommunicationTests(unittest.TestCase):
    setUpClass=classmethod(delivery.DeliveryTests.setUpClass.__func__)
    cleanup=classmethod(delivery.DeliveryTests.cleanup.__func__)
    snapshot=delivery.DeliveryTests.snapshot
    command_grant=delivery.DeliveryTests.command_grant
    path=delivery.DeliveryTests.path
    legacy=multi.MultilineTests.legacy
    def setUp(self):
        delivery.DeliveryTests.setUp(self)
        self.phone=self.db.get(Conversation,self.cid).telefone
        self.emitter=os.environ['WHATSAPP_PHONE_NUMBER_ID']
        self.sender=self.phone
    def receipt(self,content='PARAR',reference=None,reply='Synthetic response',mental=True):
        mid='synthetic-'+uuid4().hex
        self.db.add(Receipt(message_id=mid,phone_number_id=self.emitter,
            fingerprint=digest(json.dumps([self.emitter,self.sender,content,reference],ensure_ascii=False)),
            fingerprint_versao=2,context_wamid=reference,resposta=reply,
            resolucao='CONTEXTUAL_ATUAL' if mental else 'LEGADO_SEM_CONVERSA',
            conversa_contextual_id=self.cid if mental else None))
        self.db.commit();return mid
    def stop(self,mid=None,reference=None):
        return interrupt(self.db,message_id=mid or self.receipt(),emitter=self.emitter,
                         sender=self.sender,content='PARAR',context_wamid=reference)
    def proof(self):
        from app.services.whatsapp_transporte import capture
        reference='wamid.'+uuid4().hex
        capture(self.db,{'messages':[{'id':reference}], 'contacts':[{'input':self.phone,'wa_id':self.sender}]},
                emitter=self.emitter,requested=self.phone,contextual=self.cid,origin='META_CONVITE')
        self.db.commit();return reference
    def payload(self):
        return AuthorizationCreate(origem='DOCUMENTO_ELETRONICO',obtida_em=self.db.scalar(select(func.clock_timestamp())),
            referencia_evidencia='synthetic-evidence-'+uuid4().hex,evidencia_sha256='a'*64,evidencia_verificada=True)
    def remote(self,*a,**kw):
        self.assertFalse(self.db.in_transaction())
        return {'messages':[{'id':'wamid.'+uuid4().hex}]}
    def test_stop_no_clinical_or_authorization_mutation(self):
        mid=self.receipt();before=self.snapshot()
        self.stop(mid);self.db.commit()
        self.assertEqual({k:v[1] for k,v in before.items() if k != 'whatsapp_mensagens'},{k:v[1] for k,v in self.snapshot().items() if k != 'whatsapp_mensagens'})
        c=self.db.get(Conversation,self.cid);a=self.db.get(Follow,c.acompanhamento_whatsapp_id)
        self.assertEqual(c.status,'AGUARDANDO_ACEITE');self.assertEqual(a.status,'ATIVO')
        self.assertEqual(a.consentimento_status,'PENDENTE')
    def test_timeline_author_and_state_independent(self):
        self.stop();self.db.commit()
        with Session(self.engine) as db:
            value=read(db,self.scope)
            self.assertEqual(value['estado'],'WHATSAPP_INTERROMPIDO')
            item=value['eventos'][0]
            self.assertEqual(item['tipo'],'COMUNICACAO_WHATSAPP_INTERROMPIDA')
            self.assertEqual(item['autoria']['pessoa_id'],self.person)
            self.assertEqual(item['origem'],'WHATSAPP')
            self.assertNotIn('telefone',json.dumps(value,default=str))
    def test_contextual_reference_and_proven_alias(self):
        self.sender='5511'+str(self.cid).zfill(8)
        ref=self.proof();mid=self.receipt(reference=ref)
        self.stop(mid,ref);self.db.commit()
        self.assertEqual(read(self.db,self.scope)['estado'],'WHATSAPP_INTERROMPIDO')
    def test_heuristic_alias_rejected(self):
        self.sender='5511'+str(self.cid).zfill(8)
        row=self.stop();self.db.commit()
        self.assertIsNone(row.acompanhamento_id)
        self.assertTrue(blocked(self.db,self.emitter,self.sender))
        self.assertFalse(blocked(self.db,self.emitter,self.phone))
    def test_stop_duplicate_one_event(self):
        mid=self.receipt();a=self.stop(mid);identity=a.id;self.db.commit()
        self.assertEqual(self.stop(mid).id,identity);self.db.commit()
        self.assertEqual(len(read(self.db,self.scope)['eventos']),1)
    def test_stop_rollback_no_timeline_event(self):
        self.stop();self.db.rollback()
        self.assertEqual(read(self.db,self.scope)['eventos'],[])
    def test_bad_receipt_rejected(self):
        mid=self.receipt(content='SIM')
        with self.assertRaises(CheckinInvalid):self.stop(mid)
        self.db.rollback()
    def test_wrong_emitter_rejected(self):
        mid=self.receipt()
        with self.assertRaises(CheckinInvalid):
            interrupt(self.db,message_id=mid,emitter='other',sender=self.sender,content='PARAR')
        self.db.rollback()
    def test_sim_does_not_reactivate(self):
        self.stop();self.db.commit()
        mid=self.receipt(content='SIM')
        with self.assertRaises(CheckinInvalid):interrupt(self.db,message_id=mid,emitter=self.emitter,sender=self.sender,content='SIM')
        self.db.rollback();self.assertEqual(read(self.db,self.scope)['estado'],'WHATSAPP_INTERROMPIDO')
    def test_reactivation_explicit_evidence_and_replay(self):
        self.stop();self.db.commit()
        payload=self.payload();key=uuid4().hex
        item=reactivate(self.db,self.scope,key,payload);self.db.commit()
        self.assertEqual(item['tipo'],'COMUNICACAO_WHATSAPP_REATIVADA')
        self.assertEqual(reactivate(self.db,self.scope,key,payload)['id'],item['id']);self.db.commit()
        value=read(self.db,self.scope)
        self.assertEqual(value['estado'],'SEM_INTERRUPCAO_REGISTRADA');self.assertEqual(len(value['eventos']),2)
    def test_old_evidence_reactivation_denied(self):
        payload=self.payload();self.stop();self.db.commit()
        with self.assertRaises(CheckinInvalid):reactivate(self.db,self.scope,uuid4().hex,payload)
        self.db.rollback()
    def test_read_wrong_institution_denied(self):
        self.stop();self.db.commit()
        with self.assertRaises(CheckinDenied):read(self.db,dict(self.scope,institution=self.institution+99999))
    def test_read_unauthorized_actor_denied(self):
        with self.assertRaises(CheckinDenied):read(self.db,dict(self.scope,actor=2147483647))
    def test_reactivation_unauthorized_denied(self):
        self.stop();self.db.commit()
        with self.assertRaises(CheckinDenied):reactivate(self.db,dict(self.scope,actor=2147483647),uuid4().hex,self.payload())
        self.db.rollback()
    def test_immutable_history(self):
        row=self.stop();self.db.commit()
        with self.assertRaises(Exception):
            self.db.execute(text('UPDATE whatsapp_comunicacao_eventos SET estado=estado WHERE id=:id'),{'id':row.id})
        self.db.rollback()
    def test_ambiguity_preventive_not_person_timeline(self):
        self.legacy(phone=self.phone)
        self.stop();self.db.commit()
        value=read(self.db,self.scope)
        self.assertTrue(value['bloqueio_preventivo']);self.assertEqual(value['eventos'],[])
    def test_blocked_navigation_no_send(self):
        self.legacy(phone=self.phone);self.stop();self.db.commit()
        mid=self.receipt(content='hello',mental=False)
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertFalse(deliver(self.db,mid,self.sender));post.assert_not_called()
    def test_blocked_invitation_no_send(self):
        self.stop();self.db.commit()
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(CheckinInvalid):self.service.deliver_invitation(self.db,self.cid,context=self.scope)
            post.assert_not_called()
        self.db.rollback()
    def test_reply_durable_no_http_transaction_and_no_duplicate(self):
        mid=self.receipt(content='SIM')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=self.remote) as remote:
            self.assertTrue(deliver(self.db,mid,self.sender));self.assertFalse(deliver(self.db,mid,self.sender));remote.assert_called_once()
        with Session(self.engine) as db:self.assertEqual(db.get(Execution,mid).estado,'CONFIRMADO')
    def test_reply_timeout_is_uncertain_no_retry(self):
        mid=self.receipt(content='SIM')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):deliver(self.db,mid,self.sender)
        self.assertEqual(self.db.get(Execution,mid).estado,'INCERTO');self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post') as remote:
            self.assertFalse(deliver(self.db,mid,self.sender));remote.assert_not_called()
    def test_reply_missing_wamid_uncertain(self):
        mid=self.receipt(content='SIM')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',return_value={}):
            with self.assertRaises(ValueError):deliver(self.db,mid,self.sender)
        self.assertEqual(self.db.get(Execution,mid).estado,'INCERTO')
    def test_explicit_rejection_not_delivery(self):
        from app.services.whatsapp_sender_service import MetaInvitationRejected
        mid=self.receipt(content='SIM')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=MetaInvitationRejected(400,100)):
            with self.assertRaises(MetaInvitationRejected):deliver(self.db,mid,self.sender)
        self.assertEqual(self.db.get(Execution,mid).estado,'FALHA_DEFINITIVA')
    def test_concurrent_replies_one_io(self):
        mid=self.receipt(content='SIM');entered=Signal();release=Signal()
        def remote(*a,**kw):
            entered.set();self.assertTrue(release.wait(5));return {'messages':[{'id':'wamid.'+uuid4().hex}]}
        def send():
            with Session(self.engine) as db:return deliver(db,mid,self.sender)
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=remote) as transport,ThreadPoolExecutor(2) as pool:
            first=pool.submit(send);self.assertTrue(entered.wait(5))
            try:self.assertFalse(pool.submit(send).result(5))
            finally:release.set()
            self.assertTrue(first.result(5));transport.assert_called_once()
    def test_stop_after_execution_started_blocks_next_only(self):
        mid=self.receipt(content='SIM');stop_id=self.receipt();entered=Signal();release=Signal()
        def remote(*a,**kw):
            entered.set();self.assertTrue(release.wait(5));return {'messages':[{'id':'wamid.'+uuid4().hex}]}
        def send():
            with Session(self.engine) as db:return deliver(db,mid,self.sender)
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=remote),ThreadPoolExecutor(1) as pool:
            running=pool.submit(send);self.assertTrue(entered.wait(5))
            try:self.stop(stop_id);self.db.commit()
            finally:release.set()
            self.assertTrue(running.result(5))
        later=self.receipt(content='other')
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertFalse(deliver(self.db,later,self.sender));post.assert_not_called()
    def test_callback_read_reconciliation(self):
        from app.services.whatsapp_convite_status import parse_statuses,persist_statuses
        mid=self.receipt(content='SIM')
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=self.remote):deliver(self.db,mid,self.sender)
        row=self.db.get(Execution,mid);wamid=row.wamid;self.db.rollback()
        events=parse_statuses({'statuses':[{'id':wamid,'status':'delivered','timestamp':'1700000000'}]},self.emitter)
        persist_statuses(self.db,events);persist_statuses(self.db,events)
        self.assertEqual(len(evidence(self.db,mid)['eventos']),1)
    def test_indexes_preserved_and_head(self):
        with self.engine.connect() as c:
            self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'e14b_close_v1')
            names={i['name'] for i in inspect(c).get_indexes('whatsapp_conversas_contextuais')}
            self.assertTrue({'ix_wcc_aberta_telefone','uq_wcc_aberta_acompanhamento'}<=names)
            self.assertNotIn('uq_wcc_aberta_telefone',names)
    def test_ingress_remains_unconnected(self):
        from pathlib import Path
        source=Path('app/services/whatsapp_ingress.py').read_text()
        self.assertNotIn('whatsapp_multilinhas',source);self.assertIn('process_selected',source)
        self.assertIn('process_stop',source)

    def test_receipt_unique_and_fk(self):
        row=self.stop();self.db.commit()
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.add(Event(escopo='D:test',phone_number_id=self.emitter,destino_sha256='a'*64,
                estado='INTERROMPIDA',origem='WHATSAPP',mensagem_id=row.mensagem_id,
                chave='b'*64,comando_sha256='c'*64));self.db.flush()
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.add(Event(escopo='D:test',phone_number_id=self.emitter,destino_sha256='a'*64,
                estado='INTERROMPIDA',origem='WHATSAPP',mensagem_id='nonexistent',
                chave='b'*64,comando_sha256='c'*64));self.db.flush()
    def test_http_visibility_and_denial(self):
        from fastapi import FastAPI
        from test_whatsapp_security import LocalClient
        from types import SimpleNamespace
        from app.routers.whatsapp_mental import router
        from app.core.deps import get_usuario_atual
        from app.database import get_db
        self.stop();self.db.commit()
        app=FastAPI();app.include_router(router)
        def session():
            with Session(self.engine) as db:yield db
        app.dependency_overrides[get_db]=session
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor)
        client=LocalClient(app)
        url=f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/whatsapp/comunicacao'
        response=client.get(url,params={'instituicao_id':self.institution})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['eventos'][0]['tipo'],'COMUNICACAO_WHATSAPP_INTERROMPIDA')
        self.assertEqual(client.get(url,params={'instituicao_id':999999}).status_code,403)
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE contexto_assistencial_id=:c'),{'c':self.open});self.db.commit()
        self.assertEqual(client.get(url,params={'instituicao_id':self.institution}).status_code,403)
    def test_journey_projection_no_clinical_analysis_changes(self):
        from app.services.saude_mental import SaudeMentalService
        def journey():
            return SaudeMentalService().journey(self.db,actor_id=self.actor,institution=self.institution,person=self.person,context=self.open).model_dump(mode='json')
        before=journey();self.db.rollback()
        self.stop();self.db.commit()
        after=journey()
        self.assertEqual(len(after['comunicacao_whatsapp']['eventos']),1)
        before.pop('comunicacao_whatsapp');after.pop('comunicacao_whatsapp')
        self.assertEqual(before,after)
    def test_stop_concurrent_duplicate(self):
        mid=self.receipt()
        def command():
            with Session(self.engine) as db:
                row=interrupt(db,message_id=mid,emitter=self.emitter,sender=self.sender,content='PARAR');identity=row.id;db.commit();return identity
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(lambda _:command(),range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(len(read(self.db,self.scope)['eventos']),1)
    def test_before_execution_commit_failure_no_io(self):
        mid=self.receipt(content='SIM')
        with patch.object(self.db,'commit',side_effect=RuntimeError('synthetic')),patch('app.services.whatsapp_sender_service.requests.post') as remote:
            with self.assertRaises(RuntimeError):deliver(self.db,mid,self.sender)
            remote.assert_not_called()
        self.assertIsNone(self.db.get(Execution,mid))
    def test_acceptance_commit_ack_lost_no_retry(self):
        mid=self.receipt(content='SIM');original=self.db.commit;count=0
        def commit():
            nonlocal count
            count+=1;original()
            if count==3:raise RuntimeError('ack lost')
        with patch.object(self.db,'commit',side_effect=commit),patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=self.remote):
            with self.assertRaises(RuntimeError):deliver(self.db,mid,self.sender)
        self.assertEqual(self.db.get(Execution,mid).estado,'CONFIRMADO');self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post') as remote:
            self.assertFalse(deliver(self.db,mid,self.sender));remote.assert_not_called()
    def test_persistence_failure_after_acceptance_uncertain(self):
        mid=self.receipt(content='SIM');original=self.db.commit;count=0
        def commit():
            nonlocal count
            count+=1
            if count==3:raise RuntimeError('commit unavailable')
            original()
        with patch.object(self.db,'commit',side_effect=commit),patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=self.remote):
            with self.assertRaises(RuntimeError):deliver(self.db,mid,self.sender)
        self.assertEqual(self.db.get(Execution,mid).estado,'INCERTO')
        self.assertTrue(self.db.get(Execution,mid).wamid.startswith('wamid.'))
        self.assertEqual(self.db.get(Execution,mid).graph_http_status,200)
    def test_stop_between_preparation_and_execution_no_io(self):
        mid=self.receipt(content='SIM');stop_id=self.receipt();original=self.db.commit;count=0
        def commit():
            nonlocal count
            count+=1;original()
            if count==1:
                with Session(self.engine) as other:
                    interrupt(other,message_id=stop_id,emitter=self.emitter,sender=self.sender,content='PARAR');other.commit()
        with patch.object(self.db,'commit',side_effect=commit),patch('app.services.whatsapp_sender_service.requests.post') as remote:
            self.assertFalse(deliver(self.db,mid,self.sender));remote.assert_not_called()
        self.assertEqual(self.db.get(Execution,mid).estado,'PREPARADO')
    def test_preventive_block_alias_proven_and_other_emitter_independent(self):
        self.sender='5511'+str(self.cid).zfill(8);self.proof()
        self.legacy(phone=self.sender)
        self.stop();self.db.commit()
        self.assertTrue(blocked(self.db,self.emitter,self.phone))
        self.assertFalse(blocked(self.db,'other',self.phone))
    def test_reactivate_context_does_not_remove_recipient_barrier(self):
        self.stop();self.db.commit();self.legacy(phone=self.phone)
        self.stop();self.db.commit()
        reactivate(self.db,self.scope,uuid4().hex,self.payload());self.db.commit()
        state=read(self.db,self.scope)
        self.assertEqual(state['estado'],'WHATSAPP_INTERROMPIDO');self.assertTrue(state['bloqueio_preventivo'])
    def test_recipient_release_does_not_grant_context(self):
        from app.services.whatsapp_comunicacao import release_recipient
        self.stop();self.db.commit();self.legacy(phone=self.phone);self.stop();self.db.commit()
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:id"),{'id':self.actor});self.db.commit()
        release_recipient(self.db,actor=self.actor,emitter=self.emitter,phone=self.phone,key=uuid4().hex,payload=self.payload());self.db.commit()
        state=read(self.db,self.scope)
        self.assertFalse(state['bloqueio_preventivo']);self.assertEqual(state['estado'],'WHATSAPP_INTERROMPIDO')
    def test_transport_caller_inventory(self):
        import ast
        from pathlib import Path
        found=[]
        for path in Path('app').rglob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('enviar_texto','enviar_template'):
                    found.append((str(path),node.func.attr))
        self.assertEqual(sorted(found),[('app/services/whatsapp_convite_envio.py','enviar_template'),('app/services/whatsapp_resposta.py','enviar_texto')])

    def test_timeline_not_visible_before_durable_commit(self):
        self.stop()
        with Session(self.engine) as independent:
            self.assertEqual(read(independent,self.scope)['eventos'],[])
        self.db.commit()
        with Session(self.engine) as independent:
            self.assertEqual(len(read(independent,self.scope)['eventos']),1)
    def test_reactivation_serializes_with_send(self):
        self.stop();self.db.commit();mid=self.receipt(content='SIM')
        reactivate(self.db,self.scope,uuid4().hex,self.payload())
        def send():
            with Session(self.engine) as db:return deliver(db,mid,self.sender)
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',return_value={'messages':[{'id':'wamid.'+uuid4().hex}]}),ThreadPoolExecutor(1) as pool:
            running=pool.submit(send)
            try:
                from concurrent.futures import TimeoutError as Pending
                with self.assertRaises(Pending):running.result(.15)
            finally:self.db.commit()
            self.assertTrue(running.result(5))
    def test_concurrent_preventive_blocks_form_one_history(self):
        self.legacy(phone=self.phone)
        mids=[self.receipt(),self.receipt()]
        def stop(mid):
            with Session(self.engine) as db:
                row=interrupt(db,message_id=mid,emitter=self.emitter,sender=self.sender,content='PARAR');identity=row.id;db.commit();return identity
        with ThreadPoolExecutor(2) as pool:ids=list(pool.map(stop,mids))
        rows=list(self.db.scalars(select(Event).where(Event.id.in_(ids)).order_by(Event.id)))
        self.assertIsNone(rows[0].anterior_id);self.assertEqual(rows[1].anterior_id,rows[0].id)
        self.assertTrue(read(self.db,self.scope)['bloqueio_preventivo'])
    def test_two_distinct_receipts_same_recipient_not_duplicate(self):
        mids=[self.receipt(content='one'),self.receipt(content='two')]
        def send(mid):
            with Session(self.engine) as db:return deliver(db,mid,self.sender)
        def remote(*a,**kw):return {'messages':[{'id':'wamid.'+uuid4().hex}]}
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_texto',side_effect=remote) as remote,ThreadPoolExecutor(2) as pool:
            self.assertEqual(list(pool.map(send,mids)),[True,True]);self.assertEqual(remote.call_count,2)
        self.assertEqual(len(list(self.db.scalars(select(Execution).where(Execution.mensagem_id.in_(mids))))),2)

    def test_manager_root_does_not_grant_timeline_access(self):
        self.stop();self.db.commit()
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE contexto_assistencial_id=:c'),{'c':self.open})
        self.db.execute(text("UPDATE usuario_instituicao_acessos SET perfil_institucional='GESTOR' WHERE usuario_id=:u AND instituicao_id=:i"),{'u':self.actor,'i':self.institution})
        self.db.commit()
        with self.assertRaises(CheckinDenied):read(self.db,self.scope)
    def test_unknown_reference_never_selects_another_followup(self):
        ref='wamid.unknown';mid=self.receipt(reference=ref)
        self.stop(mid,ref);self.db.commit()
        state=read(self.db,self.scope)
        self.assertEqual(state['eventos'],[]);self.assertTrue(state['bloqueio_preventivo'])
