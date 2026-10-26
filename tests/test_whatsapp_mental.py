"""WhatsApp MH real PostgreSQL, canonical authorizations and clinical persistence."""
import os
import unittest
from datetime import timedelta
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow, WhatsAppConversaContextual as Conversation
from app.models.registro_proveniencia import RegistroProveniencia
from app.services.whatsapp_mental import WhatsAppMentalService, dispatch, now_utc
from app.services.whatsapp_ingress import process_message
from app.services.whatsapp_sender_service import WhatsAppSenderService
from app.services.checkin_bem_estar import CheckinDenied, CheckinInvalid
from app.routers import whatsapp_mental as api
import test_checkin_bem_estar as fixture


class SenderTests(unittest.TestCase):
    def test_template_and_text_payload(self):
        env={'WHATSAPP_ACCESS_TOKEN':'synthetic','WHATSAPP_PHONE_NUMBER_ID':'123',
             'WHATSAPP_MENTAL_TEMPLATE_NAME':'integra_care_checkin_bem_estar','WHATSAPP_MENTAL_TEMPLATE_LANGUAGE':'pt_BR'}
        with patch.dict(os.environ,env), patch('app.services.whatsapp_sender_service.requests.post') as post:
            post.return_value.ok=True
            WhatsAppSenderService.enviar_texto('5511999999999','Synthetic')
            self.assertEqual(post.call_args.kwargs['json']['type'],'text')
            self.assertEqual(post.call_args.args[0], 'https://graph.facebook.com/v23.0/123/messages')
            WhatsAppSenderService.enviar_template('5511999999999')
            self.assertEqual(post.call_args.args[0], 'https://graph.facebook.com/v25.0/123/messages')
            self.assertEqual(post.call_args.kwargs['json']['template'],{'name':'integra_care_checkin_bem_estar','language':{'code':'pt_BR'}})
            self.assertEqual(post.call_args.kwargs['timeout'],15)
        for key in env:
            with patch.dict(os.environ,dict(env,**{key:''})), patch('app.services.whatsapp_sender_service.requests.post') as post:
                with self.assertRaises(ValueError): WhatsAppSenderService.enviar_template('5511999999999')
                post.assert_not_called()


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class MentalWhatsAppTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(fixture.CheckinTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.CheckinTests.tearDownClass.__func__)
    tearDown=fixture.CheckinTests.tearDown
    command_grant=fixture.CheckinTests.command_grant
    counts=fixture.CheckinTests.counts
    path=fixture.CheckinTests.path

    def setUp(self):
        fixture.CheckinTests.setUp(self)
        emitter=patch.dict(os.environ, {'WHATSAPP_PHONE_NUMBER_ID':'123'})
        emitter.start();self.addCleanup(emitter.stop)
        self.app.include_router(api.router)
        self.w=WhatsAppMentalService()
        self.scope=dict(actor=self.actor,institution=self.institution,person=self.person,context=self.open)
        self.phone='55659'+str(self.open).zfill(8)
        self.counter=0

    def config(self):
        a=self.w.configure(self.db,self.phone,**self.scope);self.db.commit()
        self.aid=a.id
        from whatsapp_authorization_fixture import authorize_follow
        authorize_follow(self.db,self.scope)
        return a

    def prepare(self):
        a=self.config()
        c=self.w.prepare(self.db,a.id);self.db.commit()
        self.cid=c.id;return c

    def incoming(self,content,identity=None):
        self.counter+=1
        return process_message(self.db,str(self.open)+'-'+(identity or 'mh-'+str(self.counter)),'123',self.phone,content)

    def finish(self,event='2',description=None):
        self.incoming('sim')
        for _ in range(7):self.incoming('1')
        self.incoming(event)
        if event=='1':self.incoming(description or 'PULAR')
        return self.incoming('1',identity='last')

    def test_consent_canonical_completion_and_dedup(self):
        c=self.prepare();expiry=c.expires_at
        self.assertEqual(self.counts(),(0,0,0))
        self.incoming('sim');self.assertEqual(self.db.get(Follow,self.aid).consentimento_status,'CONSENTIDO')
        self.incoming('invalid')
        c=self.db.get(Conversation,self.cid)
        self.assertEqual(c.etapa_atual,'humor');self.assertEqual(c.respostas_json,{})
        for _ in range(7):self.incoming('1')
        self.incoming('2');self.assertEqual(self.counts(),(0,0,0))
        self.incoming('s',identity='final');self.incoming('s',identity='final')
        self.assertEqual(self.counts(),(1,9,1))
        p=self.db.scalar(select(RegistroProveniencia).where(RegistroProveniencia.respondente_pessoa_id==self.person))
        self.assertEqual((p.canal,p.modalidade,p.registrador_profissional_id,p.registrador_pessoa_id),('WHATSAPP','AUTORRELATO',None,self.person))
        c=self.db.get(Conversation,self.cid)
        self.assertEqual(c.status,'CONCLUIDA');self.assertEqual(c.expires_at,expiry)
        self.assertEqual(c.respostas_json['humor'],'MUITO_RUIM');self.assertEqual(c.respostas_json['pedido_ajuda'],'SIM')
        self.assertIsNone(self.db.scalar(text('SELECT criado_por_usuario_id FROM registros_longitudinais WHERE id=:id'),{'id':p.registro_id}))

    def test_event_description_and_skip(self):
        self.prepare();self.finish('1','Synthetic event')
        self.assertEqual(self.counts(),(1,10,1))
        self.assertEqual(self.db.get(Conversation,self.cid).respostas_json['evento_descricao'],'Synthetic event')

    def test_optional_event_description(self):
        self.prepare();self.finish('1','PULAR')
        self.assertEqual(self.counts(),(1,9,1))

    def test_no_enabler_authorization_rechecked_at_completion(self):
        self.prepare();self.incoming('sim')
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),{'i':self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']});self.db.commit()
        for _ in range(7): self.incoming('1')
        self.incoming('2');self.incoming('2')
        self.assertEqual(self.counts(),(1,9,1))

    def test_stop_before_and_during_questionnaire(self):
        self.prepare();self.incoming('sim');self.incoming('PARAR')
        a=self.db.get(Follow,self.aid)
        self.assertEqual((a.status,a.consentimento_status),('ENCERRADO','REVOGADO'))
        self.assertIsNotNone(a.revogado_em)
        self.assertEqual(self.db.get(Conversation,self.cid).status,'CANCELADA')
        self.assertIsNone(self.w.prepare(self.db,self.aid))
        self.assertEqual(self.counts(),(0,0,0))

    def test_stop_at_invitation(self):
        self.prepare();self.incoming('PARAR')
        self.assertEqual(self.db.get(Follow,self.aid).consentimento_status,'REVOGADO')

    def test_fixed_expiry_no_partial_record_and_future_fallback(self):
        self.prepare();self.incoming('sim');self.incoming('1')
        self.db.execute(text("UPDATE whatsapp_conversas_contextuais SET created_at=clock_timestamp()-interval '25 hours',expires_at=clock_timestamp()-interval '1 hour' WHERE id=:i"),{'i':self.cid});self.db.commit()
        self.incoming('1')
        self.assertEqual(self.db.get(Conversation,self.cid).status,'EXPIRADA')
        self.assertEqual(self.counts(),(0,0,0))
        legacy=Mock(return_value='legacy')
        self.assertEqual(dispatch(self.db,self.phone,'oi',legacy),'legacy');legacy.assert_called_once()

    def test_dispatch_precedence_and_absent_completed_fallback(self):
        self.config()
        legacy=Mock(return_value='legacy')
        self.assertEqual(dispatch(self.db,self.phone,'oi',legacy),'legacy')
        c=self.w.prepare(self.db,self.aid);self.db.commit();self.cid=c.id
        legacy.reset_mock();dispatch(self.db,self.phone,'sim',legacy);self.db.commit();legacy.assert_not_called()
        for _ in range(7):self.incoming('1')
        self.incoming('2');self.incoming('2')
        self.assertEqual(dispatch(self.db,self.phone,'oi',legacy),'legacy')

    def test_denied_without_capability_outside_context_or_inactive_line(self):
        with self.assertRaises(CheckinDenied):self.w.configure(self.db,self.phone,**dict(self.scope,context=self.contexts[1]))
        self.db.rollback()
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c AND modulo_id=3'),{'c':self.open})
        with self.assertRaises(CheckinDenied): self.config()
        self.db.rollback()
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),{'i':self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']})
        with self.assertRaises(CheckinDenied): self.config()
        self.db.rollback()

    def test_inactive_line_prevents_dispatch_and_completion(self):
        self.prepare();self.incoming('sim')
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c AND modulo_id=3'),{'c':self.open});self.db.commit()
        self.incoming('1')
        self.assertEqual(self.db.get(Conversation,self.cid).status,'CANCELADA')
        self.assertIsNone(self.w.prepare(self.db,self.aid))
        self.assertEqual(self.counts(),(0,0,0))

    def test_constraints_and_blocked_phone_does_not_advance_schedule(self):
        self.prepare()
        a=self.db.get(Follow,self.aid)
        values=dict(contexto_assistencial_id=a.contexto_assistencial_id,paciente_id=a.paciente_id,telefone=a.telefone,criado_por_usuario_id=self.actor)
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():self.db.add(Follow(**values));self.db.flush()
        # A second context for the same patient can legitimately share this phone.
        other=Follow(**dict(values,contexto_assistencial_id=self.closed));self.db.add(other);self.db.flush()
        second_id=other.id
        # Temporarily make the second context current, retaining physical validity.
        self.db.execute(text('UPDATE contextos_assistenciais SET ativo=false WHERE id=:i'),{'i':self.open})
        self.db.execute(text('UPDATE contextos_assistenciais SET data_fim=NULL,ativo=true WHERE id=:i'),{'i':self.closed})
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),{'c':self.closed})
        self.db.commit()
        self.assertIsNone(self.w.prepare(self.db,second_id))
        self.assertIsNone(self.db.get(Follow,second_id).proximo_envio_em)
        now=now_utc(self.db)
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.add(Conversation(acompanhamento_whatsapp_id=second_id,contexto_assistencial_id=self.closed,paciente_id=a.paciente_id,telefone=self.phone,data_referencia=now.date(),expires_at=now+timedelta(hours=24)))
                self.db.flush()
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.add(Conversation(acompanhamento_whatsapp_id=self.aid,contexto_assistencial_id=self.open,paciente_id=a.paciente_id,telefone='5511999999999',data_referencia=now.date(),expires_at=now+timedelta(hours=24)))
                self.db.flush()

    def test_concurrent_dispatch_creates_one_execution(self):
        self.config();self.db.rollback()
        engine=self.db.get_bind()
        def run():
            with Session(engine) as db:
                c=WhatsAppMentalService().prepare(db,self.aid)
                result=c.id if c else None;db.commit();return result
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:run(),range(2)))
        self.assertEqual(sum(x is not None for x in results),1)

    def test_transport_failure_retry_does_not_recreate_execution(self):
        self.prepare()
        from test_whatsapp_invitation_diagnostics import ENV
        self.env_patch = patch.dict(os.environ, ENV); self.env_patch.start(); self.addCleanup(self.env_patch.stop)
        with patch.object(WhatsAppSenderService,'enviar_template',side_effect=RuntimeError('transport')):
            with self.assertRaises(RuntimeError):self.w.deliver_invitation(self.db,self.cid,context=self.scope)
            self.db.rollback()
        with patch.object(WhatsAppSenderService,'enviar_template') as sender:
            self.assertFalse(self.w.deliver_invitation(self.db,self.cid,context=self.scope));self.db.commit()
            self.assertFalse(self.w.deliver_invitation(self.db,self.cid,context=self.scope));self.db.commit()
            sender.assert_not_called()
        self.assertEqual(self.counts(),(0,0,0))

    def test_api_lifecycle_and_controlled_dispatch(self):
        from urllib.parse import urlsplit,parse_qsl
        import json
        url=urlsplit(self.path());base=url.path+'/whatsapp';params=dict(parse_qsl(url.query))
        def req(method,suffix='',payload=None):
            return self.client.request(method,base+suffix,params=params,body=json.dumps(payload or {}).encode(),headers={'Content-Type':'application/json'})
        self.assertIsNone(req('GET').json())
        self.assertEqual(req('PUT',payload={'telefone':self.phone}).status_code,200)
        self.assertEqual(req('POST','/pausar').json()['status'],'PAUSADO')
        self.assertEqual(req('POST','/reativar').json()['status'],'ATIVO')
        from whatsapp_authorization_fixture import authorize_follow
        authorize_follow(self.db,self.scope)
        from test_whatsapp_invitation_diagnostics import ENV
        with patch.dict(os.environ, ENV), patch.object(WhatsAppSenderService,'enviar_template', return_value={'messages':[{'id':'wamid.synthetic'+str(self.open)}]}):
            r=req('POST','/disparar');self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['status'],'ENVIADO')
        self.assertEqual(req('POST','/encerrar').json()['consentimento_status'],'REVOGADO')
        self.assertEqual(req('POST','/reativar').status_code,409)

    def test_identity_constraint_and_canonical_entry_cannot_complete_twice(self):
        self.prepare()
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.execute(text('UPDATE acompanhamentos_whatsapp SET paciente_id=paciente_id+999999 WHERE id=:i'),{'i':self.aid})
        self.finish()
        from app.services.checkin_bem_estar import CheckinBemEstarService
        with self.assertRaises(CheckinDenied):
            CheckinBemEstarService().create_self_report(self.db,conversation_id=self.cid)
        self.assertEqual(self.counts(),(1,9,1))

    def test_atomic_failure_rolls_back_final_answer_and_receipt(self):
        self.prepare();self.incoming('sim')
        for _ in range(7):self.incoming('1')
        self.incoming('2')
        from app.services import checkin_bem_estar as module
        original=module.criar_registro_longitudinal
        def fail(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('synthetic')
        with patch.object(module,'criar_registro_longitudinal',side_effect=fail):
            with self.assertRaises(RuntimeError):self.incoming('1',identity='retry')
        self.assertEqual(self.counts(),(0,0,0))
        self.assertEqual(self.db.get(Conversation,self.cid).etapa_atual,'pedido_ajuda')
        self.incoming('1',identity='retry');self.assertEqual(self.counts(),(1,9,1))

    def test_paused_and_closed_context_prevent_dispatch(self):
        self.config()
        self.assertIn(self.aid,self.w.eligible_ids(self.db))
        self.w.lifecycle(self.db,'pausar',**self.scope);self.db.commit()
        self.assertIsNone(self.w.prepare(self.db,self.aid))
        self.w.lifecycle(self.db,'reativar',**self.scope);self.db.commit()
        self.db.execute(text('UPDATE contextos_assistenciais SET data_fim=CURRENT_DATE WHERE id=:c'),{'c':self.open});self.db.commit()
        self.assertIsNone(self.w.prepare(self.db,self.aid))
        self.assertNotIn(self.aid,self.w.eligible_ids(self.db))

    def test_z_migration_roundtrip_and_partial_indexes(self):
        from alembic import command
        from test_m0_baseline import config
        from sqlalchemy import inspect
        self.db.rollback()
        with self.db.get_bind().begin() as c:
            indexes={r['name']:r for r in inspect(c).get_indexes('whatsapp_conversas_contextuais')}
            for name in ('uq_wcc_aberta_acompanhamento','uq_wcc_aberta_telefone'):
                self.assertTrue(indexes[name]['unique'])
                self.assertIn('AGUARDANDO_ACEITE',str(indexes[name]['dialect_options']))
            revision = c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one()
            if revision in ('d92a_whatsapp_persistencia', 'd92e12_whatsapp_manual', 'd92e12c_autorizacao_whatsapp', 'e14b1_transporte', 'e14b2_referencia', 'e14b3a_multilinhas', 'e14b3b2_comunicacao'):
                # The new additive evidence migration deliberately forbids destructive rollback.
                # Keep the historical roundtrip below for fixtures pinned to the W3 revision.
                before = set(inspect(c).get_table_names())
                with self.assertRaisesRegex(RuntimeError, 'delivery evidence must be preserved|Manual request evidence requires separately approved removal|Channel authorization evidence requires separately approved removal|Transport evidence removal requires an approved recovery procedure|Routing evidence removal requires an approved recovery procedure|Communication evidence removal requires an approved recovery procedure'):
                    command.downgrade(config(c), 'w3_atendimento_mental_v1')
                self.assertEqual(set(inspect(c).get_table_names()), before)
                self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar_one(), revision)
                return
            command.downgrade(config(c),'w3_atendimento_mental_v1')
            self.assertNotIn('acompanhamentos_whatsapp',inspect(c).get_table_names())
            command.upgrade(config(c),'w3_whatsapp_mental_v1')
            self.assertIn('whatsapp_conversas_contextuais',inspect(c).get_table_names())
