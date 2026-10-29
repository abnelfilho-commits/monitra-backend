"""Cutover contracts on real owned PostgreSQL. No real HTTP or persistent schema."""
import importlib.util
import json
import unittest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as Pending
from threading import Event as Signal
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy import text, select, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError, IntegrityError
from alembic import command
from test_m0_baseline import config
import test_whatsapp_stop as stop_fixture
import test_whatsapp_convite_envio as delivery
from app.services.whatsapp_ingress import process_message
from app.services.whatsapp_selected import process_selected
from app.services.checkin_bem_estar import CheckinInvalid
from app.services.whatsapp_runtime import require_active
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Conversation, AcompanhamentoWhatsApp as Follow
from app.models.whatsapp_mensagem import WhatsAppMensagem as Receipt
from app.models.whatsapp_resolucao import WhatsAppResolucao as Audit
from app.models.whatsapp_conversa import WhatsAppConversa as Legacy


@unittest.skipUnless(delivery.foundation.URL, 'Owned disposable PostgreSQL required')
class ActivationTests(unittest.TestCase):
    setUpClass=stop_fixture.StopTests.__dict__['setUpClass']
    cleanup=stop_fixture.StopTests.__dict__['cleanup']
    setUp=stop_fixture.StopTests.setUp
    snapshot=stop_fixture.StopTests.snapshot
    command_grant=stop_fixture.StopTests.command_grant
    path=stop_fixture.StopTests.path
    legacy=stop_fixture.StopTests.legacy
    proof=stop_fixture.StopTests.proof
    payload=stop_fixture.StopTests.payload
    receipt=stop_fixture.StopTests.receipt

    def call(self, content='SIM', ref=None, phone=None, mid=None, db=None):
        self.mid=mid or 'activation-'+uuid4().hex
        return process_message(db or self.db,self.mid,self.emitter,phone or self.phone,content,ref)

    def pause(self):
        self.db.rollback()
        with self.engine.begin() as c:c.execute(text('UPDATE whatsapp_runtime SET active=false WHERE id=1'))

    def two_mental(self):
        first=self.cid;phone=self.phone
        delivery.DeliveryTests.setUp(self)
        self.db.get(Conversation,self.cid).status='CONCLUIDA';self.db.commit()
        self.service.configure(self.db,phone,**self.scope);self.db.commit()
        from app.services.whatsapp_autorizacao import register
        register(self.db,self.scope,uuid4().hex,self.payload());self.db.commit()
        second=self.db.get(Conversation,self.cid)
        second.telefone=phone;second.status='AGUARDANDO_ACEITE';self.db.commit()
        self.phone=phone;self.sender=phone
        return first,self.cid

    def test_two_mental_same_phone_unreferenced_ambiguous(self):
        first,second=self.two_mental();self.call()
        self.assertEqual(self.db.get(Audit,self.mid).decisao['outcome'],'AMBIGUA')
        for cid in (first,second):self.assertEqual(self.db.get(Conversation,cid).status,'AGUARDANDO_ACEITE')
        self.assertIsNone(self.db.get(Receipt,self.mid).conversa_contextual_id)

    def test_two_mental_reference_selects_exact_context(self):
        first,second=self.two_mental();ref=self.proof();self.call(ref=ref)
        self.assertEqual(self.db.get(Conversation,first).status,'AGUARDANDO_ACEITE')
        self.assertEqual(self.db.get(Conversation,second).status,'EM_ANDAMENTO')
        self.assertEqual(self.db.get(Receipt,self.mid).conversa_contextual_id,second)

    def test_two_mental_parar_without_reference_is_preventive(self):
        first,second=self.two_mental();self.call('PARAR')
        from app.models.whatsapp_comunicacao import WhatsAppComunicacaoEvento as Event
        event=self.db.scalar(select(Event).where(Event.mensagem_id==self.mid))
        self.assertIsNone(event.acompanhamento_id)
        for cid in (first,second):self.assertEqual(self.db.get(Conversation,cid).status,'AGUARDANDO_ACEITE')

    def test_two_mental_parar_reference_does_not_block_other_followup(self):
        first,second=self.two_mental();ref=self.proof();self.call('PARAR',ref)
        from app.services.whatsapp_comunicacao import blocked
        self.assertFalse(blocked(self.db,self.emitter,self.phone,follow_id=self.db.get(Conversation,first).acompanhamento_whatsapp_id))
        self.assertTrue(blocked(self.db,self.emitter,self.phone,follow_id=self.db.get(Conversation,second).acompanhamento_whatsapp_id))

    def test_concurrent_preparation_different_followups_same_phone(self):
        first,second=self.two_mental();aids=[]
        for cid in (first,second):
            c=self.db.get(Conversation,cid);c.status='CONCLUIDA';aids.append(c.acompanhamento_whatsapp_id)
            self.db.get(Follow,c.acompanhamento_whatsapp_id).proximo_envio_em=None
        self.db.commit()
        def prepare(aid):
            with Session(self.engine) as db:
                c=self.service.prepare(db,aid);identity=c.id if c else None;db.commit();return identity
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(prepare,aids))
        self.assertTrue(all(results));self.assertEqual(len(set(results)),2)

    def test_followup_unique_index_still_enforced(self):
        c=self.db.get(Conversation,self.cid)
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.add(Conversation(acompanhamento_whatsapp_id=c.acompanhamento_whatsapp_id,
                contexto_assistencial_id=c.contexto_assistencial_id,paciente_id=c.paciente_id,
                telefone=c.telefone,data_referencia=c.data_referencia,expires_at=c.expires_at))
            self.db.flush()

    def test_phone_index_is_nonunique(self):
        with self.engine.connect() as c:
            indexes={i['name']:i for i in inspect(c).get_indexes('whatsapp_conversas_contextuais')}
        self.assertNotIn('uq_wcc_aberta_telefone',indexes)
        self.assertFalse(indexes['ix_wcc_aberta_telefone']['unique'])
        self.assertTrue(indexes['uq_wcc_aberta_acompanhamento']['unique'])

    def test_paused_ingress_has_no_receipt_or_effect(self):
        self.pause();mid='paused-'+uuid4().hex
        with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):self.call(mid=mid)
        self.assertIsNone(self.db.get(Receipt,mid))
        self.assertEqual(self.db.get(Conversation,self.cid).status,'AGUARDANDO_ACEITE')

    def test_paused_stop_is_retryable_without_acknowledgement(self):
        self.pause()
        with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):self.call('PARAR')
        self.assertIsNone(self.db.get(Audit,self.mid))

    def test_paused_preparation_does_not_advance_schedule(self):
        aid=self.db.get(Conversation,self.cid).acompanhamento_whatsapp_id;self.pause()
        with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):self.service.prepare(self.db,aid)
        self.db.rollback()

    def test_paused_invitation_has_no_http(self):
        self.pause()
        with patch('app.services.whatsapp_sender_service.requests.post') as http:
            with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):
                self.service.deliver_invitation(self.db,self.cid,context=self.scope)
            http.assert_not_called()
        self.db.rollback()

    def test_pause_between_durable_boundaries_prevents_http(self):
        original=self.db.commit;count=0
        def commit():
            nonlocal count
            original();count+=1
            if count==1:
                with self.engine.begin() as c:c.execute(text('UPDATE whatsapp_runtime SET active=false WHERE id=1'))
        with patch.object(self.db,'commit',side_effect=commit),patch('app.services.whatsapp_sender_service.requests.post') as http:
            with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):
                self.service.deliver_invitation(self.db,self.cid,context=self.scope)
            http.assert_not_called()
        self.db.rollback()

    def test_pause_waits_for_authorized_transaction(self):
        self.db.rollback();require_active(self.db)
        def pause():
            with self.engine.begin() as c:c.execute(text('UPDATE whatsapp_runtime SET active=false WHERE id=1'))
        with ThreadPoolExecutor(1) as pool:
            pending=pool.submit(pause)
            try:
                with self.assertRaises(Pending):pending.result(.15)
            finally:self.db.rollback()
            pending.result(5)
        with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):require_active(self.db)
        self.db.rollback()

    def test_old_writer_fenced_on_every_whatsapp_table(self):
        spec=importlib.util.spec_from_file_location('fence','alembic_canonical/versions/e14b_close_v1.py')
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        for table in migration.TABLES:
            with self.subTest(table=table),self.engine.connect() as c:
                with self.assertRaisesRegex(DBAPIError,'WHATSAPP_WRITER_PROTOCOL_REQUIRED'):
                    c.exec_driver_sql('DELETE FROM '+table+' WHERE false')
                c.rollback()

    def test_protocol_marker_is_transaction_local(self):
        self.db.rollback()
        with self.engine.connect() as conn:
            with Session(bind=conn) as db:
                self.assertEqual(db.scalar(text("SELECT current_setting('integra.whatsapp_protocol',true)")),'e14b_close_v1')
                db.commit()
            self.assertNotEqual(conn.scalar(text("SELECT current_setting('integra.whatsapp_protocol',true)")),'e14b_close_v1')
            conn.rollback()
            with self.assertRaisesRegex(DBAPIError,'WRITER_PROTOCOL'):
                conn.exec_driver_sql('UPDATE whatsapp_mensagens SET resposta=resposta WHERE false')
            conn.rollback()

    def test_runtime_role_can_lock_but_cannot_activate(self):
        self.db.rollback()
        role='e14b_close_'+uuid4().hex
        try:
            self.db.execute(text('CREATE ROLE '+role+' NOLOGIN'))
            self.db.execute(text('GRANT USAGE ON SCHEMA public TO '+role))
            self.db.execute(text('GRANT SELECT, UPDATE(id) ON whatsapp_runtime TO '+role))
            self.db.execute(text('SET LOCAL ROLE '+role))
            require_active(self.db)
            for column,value in (('active','false'),('protocol',"'other'")):
                with self.subTest(column=column),self.assertRaisesRegex(DBAPIError,'permission denied'):
                    with self.db.begin_nested():
                        self.db.execute(text('UPDATE whatsapp_runtime SET '+column+'='+value))
            with self.assertRaisesRegex(DBAPIError,'permission denied'):
                with self.db.begin_nested():self.db.execute(text('DELETE FROM whatsapp_runtime'))
        finally:
            self.db.rollback()  # Also drops the transactionally created NOLOGIN test role.
        self.assertIsNone(self.db.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:r'),{'r':role}))

    def test_missing_runtime_schema_fails_closed(self):
        self.db.rollback()
        with self.db.begin():
            self.db.execute(text('ALTER TABLE whatsapp_runtime RENAME TO whatsapp_runtime_unavailable'))
            with self.assertRaises(DBAPIError):self.call()
        # process_message rolls back including the synthetic rename.
        with self.engine.connect() as c:self.assertIsNotNone(c.scalar(text("SELECT to_regclass('whatsapp_runtime')")))

    def fresh_phone(self):
        phone='55118'+str(self.cid).zfill(8)
        c=self.legacy(phone=phone);self.db.delete(c);self.db.commit();return phone

    def test_fresh_legacy_navigation_never_uses_phone_search(self):
        phone=self.fresh_phone()
        with patch('app.services.whatsapp_conversation_service.buscar_responsavel_por_telefone',side_effect=AssertionError('unsafe lookup')):
            self.call('OI',phone=phone)
        self.assertEqual(self.db.get(Audit,self.mid).decisao['outcome'],'NAVEGACAO_NOVA')
        self.assertIsNotNone(self.db.get(Receipt,self.mid).conversa_legada_id)

    def test_concurrent_fresh_navigation_creates_one_session(self):
        phone=self.fresh_phone();self.db.rollback()
        def call(i):
            with Session(self.engine) as db:return process_message(db,'fresh-'+uuid4().hex,self.emitter,phone,'OI')
        with ThreadPoolExecutor(2) as pool:list(pool.map(call,range(2)))
        self.assertEqual(len(list(self.db.scalars(select(Legacy).where(Legacy.telefone==phone)))),1)

    def test_fresh_navigation_handler_failure_rolls_back_session(self):
        phone=self.fresh_phone()
        with patch('app.services.whatsapp_conversation_service.processar_mensagem',side_effect=ValueError('synthetic')):
            with self.assertRaises(ValueError):self.call('OI',phone=phone)
        self.assertIsNone(self.db.get(Receipt,self.mid))
        self.assertEqual(list(self.db.scalars(select(Legacy).where(Legacy.telefone==phone))),[])

    def test_fresh_navigation_unknown_reference_does_not_fallback(self):
        phone=self.fresh_phone();self.call('OI',ref='wamid.unknown',phone=phone)
        self.assertEqual(list(self.db.scalars(select(Legacy).where(Legacy.telefone==phone))),[])

    def test_fresh_navigation_sim_does_not_start_menu(self):
        phone=self.fresh_phone();self.call('SIM',phone=phone)
        self.assertEqual(list(self.db.scalars(select(Legacy).where(Legacy.telefone==phone))),[])

    def test_fresh_navigation_unproven_alias_does_not_start_menu(self):
        phone=self.fresh_phone();self.call('OI',phone=phone[:4]+phone[5:])
        self.assertEqual(list(self.db.scalars(select(Legacy).where(Legacy.telefone==phone))),[])

    def test_retired_dispatch_cannot_choose_first_phone_match(self):
        from app.services.whatsapp_mental import dispatch
        with self.assertRaisesRegex(CheckinInvalid,'SELECTED_INGRESS'):
            dispatch(self.db,self.phone,'SIM',lambda *a:self.fail('legacy fallback'))

    def test_recovery_refuses_destructive_downgrade(self):
        self.db.rollback()
        with self.engine.begin() as c:
            with self.assertRaisesRegex(RuntimeError,'forward recovery'):
                command.downgrade(config(c),'e14b3b2_comunicacao')
            self.assertEqual(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar(),'mh_weekly_config_v1')


@unittest.skipUnless(delivery.foundation.URL, 'Owned disposable PostgreSQL required')
class CutoverMigrationTests(unittest.TestCase):
    setUpClass=classmethod(delivery.foundation.PersistenceTests.setUpClass.__func__)
    cleanup=classmethod(delivery.foundation.PersistenceTests.cleanup.__func__)
    snapshot=delivery.foundation.PersistenceTests.snapshot
    command_grant=delivery.foundation.PersistenceTests.command_grant
    path=delivery.foundation.PersistenceTests.path

    def setUp(self):
        with patch.object(delivery.foundation,'HEAD','e14b3b2_comunicacao'):
            delivery.foundation.PersistenceTests.setUp(self)

    def test_upgrade_preserves_rows_pauses_and_fences_atomically(self):
        self.db.rollback()
        with self.engine.connect() as c:
            before=c.execute(text('SELECT row_to_json(t)::jsonb FROM whatsapp_conversas_contextuais t ORDER BY id')).all()
            self.assertIn('uq_wcc_aberta_telefone',{i['name'] for i in inspect(c).get_indexes('whatsapp_conversas_contextuais')})
        # Drift aborts the entire cutover; no half-installed pause/fence survives.
        with self.assertRaises(DBAPIError):
            with self.engine.begin() as c:
                c.execute(text('DROP INDEX uq_wcc_aberta_telefone'))
                command.upgrade(config(c),'e14b_close_v1')
        with self.engine.connect() as c:
            self.assertIsNone(c.scalar(text("SELECT to_regclass('whatsapp_runtime')")))
            self.assertEqual(c.scalar(text('SELECT version_num FROM alembic_version')),'e14b3b2_comunicacao')
        with self.engine.begin() as c:command.upgrade(config(c),'e14b_close_v1')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT row_to_json(t)::jsonb FROM whatsapp_conversas_contextuais t ORDER BY id')).all(),before)
            self.assertEqual(c.execute(text('SELECT protocol, active FROM whatsapp_runtime')).one(),('e14b_close_v1',False))
            self.assertEqual(c.scalar(text("SELECT count(*) FROM pg_trigger WHERE tgname='whatsapp_writer_fence'")),11)
        with self.assertRaisesRegex(CheckinInvalid,'RUNTIME'):require_active(self.db)
        self.db.rollback()
