"""Weekly executor on disposable PostgreSQL. All real HTTP is forbidden."""
import os
import unittest
from datetime import timedelta
from threading import Barrier, Event as Stop
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch, Mock
from sqlalchemy import select, text, inspect
from sqlalchemy.orm import Session
from sqlalchemy.exc import DBAPIError
from app.models.whatsapp_agenda import WhatsAppExecutorHabilitacao as Grant, WhatsAppAgendaCheckin as Occurrence, WhatsAppAgendaEvento as Event
from app.models.whatsapp_contextual import WhatsAppConversaContextual as Conversation, AcompanhamentoWhatsApp as Follow
from app.models.whatsapp_convite import WhatsAppConviteEnvio as Attempt
from app.services.whatsapp_agenda import (execute_occurrence, reconcile_occurrence, run_executor_batch,
    WeeklyExecution, authorize_weekly, set_executor_grant, automation_active)
from app.services.checkin_bem_estar import CheckinInvalid
import test_whatsapp_agenda as fixture


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ExecutorTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(fixture.AgendaTests.setUpClass.__func__)
    tearDownClass = classmethod(fixture.AgendaTests.tearDownClass.__func__)
    tearDown = fixture.AgendaTests.tearDown
    command_grant = fixture.AgendaTests.command_grant
    counts = fixture.AgendaTests.counts
    path = fixture.AgendaTests.path
    config = fixture.AgendaTests.config
    request = fixture.AgendaTests.request
    payload = fixture.AgendaTests.payload
    save = fixture.AgendaTests.save
    rows = fixture.AgendaTests.rows
    audit_count = fixture.AgendaTests.audit_count
    def setUp(self):
        fixture.AgendaTests.setUp(self)
        # Shared disposable class DB: revoke earlier test institutions without deleting audit.
        from app.services.whatsapp_agenda import latest_grant
        institutions=set(self.db.scalars(select(Grant.instituicao_id)))
        for institution in institutions:
            old=latest_grant(self.db,institution)
            if old.habilitado:
                self.db.add(Grant(instituicao_id=institution,usuario_id=old.usuario_id,
                    habilitado=False,motivo='Synthetic fixture cleanup'))
        self.db.commit()
        self.transport = patch.dict(os.environ, {'WHATSAPP_WEEKLY_EXECUTOR_ENABLED':'false',
            'WHATSAPP_ACCESS_TOKEN':'synthetic', 'WHATSAPP_MENTAL_TEMPLATE_NAME':'integra_care_checkin_bem_estar',
            'WHATSAPP_MENTAL_TEMPLATE_LANGUAGE':'pt_BR'})
        self.transport.start(); self.addCleanup(self.transport.stop)

    def scheduled(self, enable=True):
        self.assertEqual(self.save().status_code,200)
        self.oid=self.rows()[0].id
        if enable:
            self.db.add(Grant(instituicao_id=self.institution, usuario_id=self.actor, habilitado=True, motivo='Synthetic test grant'))
            self.db.commit()
        self.db.rollback()
        self.enabled=patch.dict(os.environ,{'WHATSAPP_WEEKLY_EXECUTOR_ENABLED':'true'})
        self.enabled.start(); self.addCleanup(self.enabled.stop)

    def accepted(self):
        result=Mock(status_code=200)
        result.json.return_value={'messages':[{'id':'wamid.weekly'+str(self.oid)}]}
        return result

    def execute(self, now=None):
        with patch('app.services.whatsapp_mental.now_utc',return_value=now or fixture.FRIDAY):
            execute_occurrence(self.db,self.oid)
        self.db.expire_all()
        return self.db.get(Occurrence,self.oid)

    def test_execution_disabled_and_missing_grant_never_send(self):
        self.scheduled(enable=False)
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.execute()
            with patch.dict(os.environ,{'WHATSAPP_WEEKLY_EXECUTOR_ENABLED':'false'}):
                run_executor_batch(lambda:Session(self.engine))
                self.execute()
            post.assert_not_called()
        self.assertEqual(self.db.get(Occurrence,self.oid).status,'AGENDADO')
        self.assertIsNone(self.db.get(Occurrence,self.oid).conversa_id)

    def test_acceptance_and_duplicate_and_recovery_do_not_send_twice(self):
        self.scheduled()
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.accepted()) as post:
            row=self.execute()
            self.assertEqual(row.status,'EXECUTADO')
            self.assertEqual(row.motivo_estado,'META_ACCEPTED')
            self.execute(); reconcile_occurrence(self.db,self.oid)
            post.assert_called_once()
        self.assertIsNotNone(row.conversa_id)
        self.assertEqual(self.db.get(Follow,self.aid).proximo_envio_em,fixture.FRIDAY+timedelta(days=7))
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM whatsapp_solicitacoes_manuais')),0)
        events=list(self.db.scalars(select(Event).where(Event.ocorrencia_id==self.oid,Event.origem=='EXECUTOR_SEMANAL_MENTAL')))
        self.assertEqual([e.estado_novo for e in events],['PROCESSANDO','EXECUTADO'])
        self.assertTrue(all(e.usuario_id is None for e in events))

    def test_future_and_expired_window(self):
        self.scheduled()
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertEqual(self.execute(fixture.FRIDAY-timedelta(microseconds=1)).status,'AGENDADO')
            self.assertEqual(self.execute(fixture.FRIDAY+timedelta(hours=2,microseconds=1)).status,'PERDIDO')
            post.assert_not_called()
        self.assertIsNone(self.db.get(Occurrence,self.oid).conversa_id)

    def test_exact_two_hour_boundary_accepts(self):
        self.scheduled()
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.accepted()) as post:
            self.assertEqual(self.execute(fixture.FRIDAY+timedelta(hours=2)).status,'EXECUTADO')
            post.assert_called_once()

    def test_uncertain_and_restart_never_resend(self):
        self.scheduled()
        with patch('app.services.whatsapp_sender_service.requests.post',side_effect=TimeoutError('synthetic')) as post:
            row=self.execute();self.assertEqual(row.status,'PROCESSANDO')
            self.assertEqual(row.motivo_estado,'OUTCOME_UNCERTAIN')
            self.db.rollback()
            with Session(self.engine) as other:
                reconcile_occurrence(other,self.oid)
                execute_occurrence(other,self.oid)
            post.assert_called_once()
        self.assertEqual(self.db.scalar(select(Attempt.estado).where(Attempt.conversa_id==row.conversa_id)),'INCERTO')

    def test_rejection_no_automatic_retry(self):
        self.scheduled()
        from app.services.whatsapp_sender_service import MetaInvitationRejected
        with patch('app.services.whatsapp_sender_service.WhatsAppSenderService.enviar_template',side_effect=MetaInvitationRejected(400,132000,None)) as send:
            row=self.execute(); self.assertEqual(row.status,'BLOQUEADO')
            self.assertEqual(row.motivo_estado,'META_REJECTED')
            self.execute();send.assert_called_once()

    def test_pause_before_execution(self):
        self.scheduled()
        self.assertEqual(self.save(programacao_ativa=False,versao_esperada=1).status_code,200)
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertEqual(self.execute().status,'BLOQUEADO');post.assert_not_called()

    def test_reprogram_after_claim_is_denied_before_meta(self):
        self.scheduled()
        with patch('app.services.whatsapp_convite_envio.deliver',side_effect=SystemExit):
            with self.assertRaises(SystemExit):self.execute()
        row=self.db.get(Occurrence,self.oid);self.assertEqual(row.status,'PROCESSANDO')
        self.assertEqual(self.save(horario_local='20:00',versao_esperada=1).status_code,200)
        grant=self.db.scalar(select(Grant).where(Grant.instituicao_id==self.institution))
        from app.services.whatsapp_convite_envio import deliver
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            with self.assertRaises(CheckinInvalid):
                deliver(self.db,row.conversa_id,WeeklyExecution(self.oid,self.institution,grant.id,1))
            post.assert_not_called()
        self.db.rollback()

    def test_crash_after_claim_no_transport_is_not_retried(self):
        self.scheduled()
        with patch('app.services.whatsapp_convite_envio.deliver',side_effect=SystemExit):
            with self.assertRaises(SystemExit):self.execute()
        self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.execute()
            reconcile_occurrence(self.db,self.oid,immediate=True)
            post.assert_not_called()
        row=self.db.get(Occurrence,self.oid)
        self.assertEqual((row.status,row.motivo_estado),('PROCESSANDO','OUTCOME_UNCERTAIN'))

    def test_concurrent_claim_single_send(self):
        self.scheduled(); gate=Barrier(2)
        def work(_):
            with Session(self.engine) as db:
                gate.wait(timeout=10);execute_occurrence(db,self.oid)
        with patch('app.services.whatsapp_mental.now_utc',return_value=fixture.FRIDAY),patch('app.services.whatsapp_sender_service.requests.post',return_value=self.accepted()) as post:
            with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(work,range(2)))
            post.assert_called_once()
        self.db.expire_all()
        self.assertEqual(self.db.get(Occurrence,self.oid).status,'EXECUTADO')

    def test_grant_revocation_and_institution_isolation(self):
        self.scheduled()
        row=self.db.get(Occurrence,self.oid);grant=self.db.scalar(select(Grant).where(Grant.instituicao_id==self.institution))
        with patch('app.services.whatsapp_mental.now_utc',return_value=fixture.FRIDAY):
            for execution in (WeeklyExecution(self.oid,self.institutions[1],grant.id,1),WeeklyExecution(self.oid,self.institution,grant.id+999,1)):
                with self.assertRaises(CheckinInvalid):authorize_weekly(self.db,execution,self.a)
        self.db.add(Grant(instituicao_id=self.institution, usuario_id=self.actor,habilitado=False,motivo='Synthetic revocation'));self.db.commit()
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.execute();post.assert_not_called()
        self.assertEqual(row.status,'AGENDADO')

    def test_audit_immutable_and_grant_authorization(self):
        self.scheduled()
        with self.assertRaises(Exception):
            set_executor_grant(self.db,institution=self.institution,actor=self.actor,enabled=True,reason='Synthetic grant')
        self.db.rollback()
        for statement in ('UPDATE whatsapp_executor_habilitacoes SET habilitado=false','DELETE FROM whatsapp_executor_habilitacoes','TRUNCATE whatsapp_executor_habilitacoes'):
            with self.assertRaises(DBAPIError),self.db.begin_nested():self.db.execute(text(statement))
        physical={c['name'] for c in inspect(self.engine).get_columns(Grant.__tablename__)}
        self.assertEqual(physical,set(Grant.__table__.c.keys()))

    def test_batch_and_stopped_batch(self):
        self.scheduled()
        with patch('app.services.whatsapp_mental.now_utc',return_value=fixture.FRIDAY),patch('app.services.whatsapp_sender_service.requests.post',return_value=self.accepted()) as post:
            stop=Stop();stop.set()
            run_executor_batch(lambda:Session(self.engine),stop)
            post.assert_not_called()
            run_executor_batch(lambda:Session(self.engine),limit=1)
            post.assert_called_once()
        self.db.expire_all()
        self.assertEqual(self.db.get(Occurrence,self.oid).status,'EXECUTADO')

    def test_runtime_revoked_consent_and_e12c_fail_closed(self):
        self.scheduled()
        from app.services.whatsapp_autorizacao import revoke_internal
        from app.services.whatsapp_comunicacao import coordinate_configured
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.db.execute(text('UPDATE whatsapp_runtime SET active=false WHERE id=1'));self.db.commit()
            self.assertEqual(self.execute().status,'BLOQUEADO')
            post.assert_not_called()
        # A different due occurrence, with runtime restored but E12C revoked.
        self.db.execute(text('UPDATE whatsapp_runtime SET active=true WHERE id=1'));self.db.commit()
        coordinate_configured(self.db,(self.phone,));self.w.authorized(self.db,**self.scope)
        revoke_internal(self.db,self.a,origin='ENCERRAMENTO',reason='ENCERRAMENTO',actor=self.actor)
        self.db.commit()
        self.oid=self.rows()[1].id
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            self.assertEqual(self.execute(fixture.FRIDAY+timedelta(days=7)).status,'CANCELADO')
            post.assert_not_called()

    def test_stop_after_claim_and_human_retry_are_blocked(self):
        self.scheduled()
        with patch('app.services.whatsapp_convite_envio.deliver',side_effect=SystemExit):
            with self.assertRaises(SystemExit):self.execute()
        row=self.db.get(Occurrence,self.oid)
        from app.services.whatsapp_stop import process
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            process(self.db,'weekly-stop-'+str(self.oid),'123',self.phone,'PARAR',None)
            self.db.commit()
            from app.services.whatsapp_convite_envio import deliver
            grant=self.db.scalar(select(Grant).where(Grant.instituicao_id==self.institution))
            with self.assertRaises(ValueError):deliver(self.db,row.conversa_id,self.scope,explicit_retry=True)
            self.db.rollback()
            with self.assertRaises(CheckinInvalid):deliver(self.db,row.conversa_id,WeeklyExecution(self.oid,self.institution,grant.id,1))
            post.assert_not_called()
        self.db.rollback()

    def test_revoke_grant_between_transport_transactions(self):
        self.scheduled()
        from sqlalchemy import event
        revoked=[]
        def on_commit(db):
            if revoked:return
            with Session(self.engine) as other:
                prepared=other.scalar(select(Attempt.id).join(Conversation).where(
                    Conversation.acompanhamento_whatsapp_id==self.aid,Attempt.estado=='PREPARADO'))
                if prepared:
                    other.add(Grant(instituicao_id=self.institution,usuario_id=self.actor,habilitado=False,motivo='Synthetic revoke in race'))
                    other.commit();revoked.append(True)
        event.listen(self.db,'after_commit',on_commit)
        try:
            with patch('app.services.whatsapp_sender_service.requests.post') as post:
                row=self.execute();post.assert_not_called()
                self.assertEqual(row.status,'PROCESSANDO')
            self.assertEqual(revoked,[True])
        finally:event.remove(self.db,'after_commit',on_commit)

    def test_recovery_after_acceptance_before_agenda_commit(self):
        self.scheduled()
        with patch('app.services.whatsapp_agenda.reconcile_occurrence',side_effect=SystemExit),patch('app.services.whatsapp_sender_service.requests.post',return_value=self.accepted()) as post:
            with self.assertRaises(SystemExit):self.execute()
            post.assert_called_once()
        self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post') as post:
            reconcile_occurrence(self.db,self.oid)
            self.assertEqual(self.db.get(Occurrence,self.oid).status,'EXECUTADO')
            post.assert_not_called()

    def test_execution_flag_reflects_runtime_and_institution_grant(self):
        self.scheduled()
        self.assertTrue(automation_active(self.db,self.a))
        self.db.execute(text('UPDATE whatsapp_runtime SET active=false WHERE id=1'));self.db.commit()
        self.assertFalse(automation_active(self.db,self.a))
        self.db.execute(text('UPDATE whatsapp_runtime SET active=true WHERE id=1'));self.db.commit()
        self.db.add(Grant(instituicao_id=self.institution,usuario_id=self.actor,habilitado=False,motivo='Synthetic disabled institution'))
        self.db.commit()
        self.assertFalse(automation_active(self.db,self.a))

    def test_grant_and_revocation_audited_without_credential(self):
        # Synthetic fixture admin with an active institutional root; no live identities.
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:i"),{'i':self.actor});self.db.commit()
        first=set_executor_grant(self.db,institution=self.institution,actor=self.actor,enabled=True,reason='Synthetic institutional approval')
        self.db.commit()
        self.assertEqual(set_executor_grant(self.db,institution=self.institution,actor=self.actor,enabled=True,reason='Synthetic approval retry').id,first.id)
        self.db.rollback()
        second=set_executor_grant(self.db,institution=self.institution,actor=self.actor,enabled=False,reason='Synthetic institutional revocation')
        self.db.commit();self.assertGreater(second.id,first.id)
        self.assertEqual(first.identidade,'EXECUTOR_SEMANAL_MENTAL')
        self.assertFalse(second.habilitado)
        self.db.execute(text('UPDATE usuario_instituicao_acessos SET ativo=false WHERE usuario_id=:u AND instituicao_id=:i'),{'u':self.actor,'i':self.institutions[1]});self.db.commit()
        with self.assertRaises(CheckinInvalid):
            set_executor_grant(self.db,institution=self.institutions[1],actor=self.actor,enabled=True,reason='Synthetic wrong institution')
        self.db.rollback()


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ExecutorMigrationTests(unittest.TestCase):
    schema_revision='mh_agenda_v1'
    setUpClass=classmethod(fixture.AgendaMigrationTests.setUpClass.__func__)
    tearDownClass=classmethod(fixture.AgendaMigrationTests.tearDownClass.__func__)
    tearDown=fixture.AgendaMigrationTests.tearDown
    command_grant=fixture.AgendaMigrationTests.command_grant
    path=fixture.AgendaMigrationTests.path
    setUp=fixture.AgendaMigrationTests.setUp

    def test_additive_transactional_upgrade_and_defaults(self):
        from alembic import command
        from test_m0_baseline import config
        before=self.db.execute(text('SELECT row_to_json(a)::text FROM acompanhamentos_whatsapp a ORDER BY id')).scalars().all()
        self.db.rollback()
        with self.engine.connect() as c:
            with self.assertRaisesRegex(RuntimeError,'synthetic rollback'):
                with c.begin():
                    command.upgrade(config(c),'mh_executor_v1')
                    raise RuntimeError('synthetic rollback')
        self.assertNotIn('whatsapp_executor_habilitacoes',inspect(self.engine).get_table_names())
        with self.engine.begin() as c:command.upgrade(config(c),'mh_executor_v1')
        self.assertEqual(self.db.scalar(text('SELECT version_num FROM alembic_version')),'mh_executor_v1')
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM whatsapp_executor_habilitacoes')),0)
        self.assertEqual(before,self.db.execute(text('SELECT row_to_json(a)::text FROM acompanhamentos_whatsapp a ORDER BY id')).scalars().all())
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM whatsapp_agenda_checkins')),0)
        self.assertTrue(any(x['name']=='ix_wagc_executor' for x in inspect(self.engine).get_indexes('whatsapp_agenda_checkins')))


class ExecutorLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disabled_lifespan_has_no_task_or_database_access(self):
        from app.services.whatsapp_agenda import executor_lifespan
        with patch.dict(os.environ,{'WHATSAPP_WEEKLY_EXECUTOR_ENABLED':'false'}),patch('app.services.whatsapp_agenda.run_executor_batch') as batch:
            async with executor_lifespan(None):pass
            batch.assert_not_called()

    async def test_shutdown_drains_current_batch_and_starts_no_second_cycle(self):
        import asyncio
        from app.services.whatsapp_agenda import executor_lifespan
        started=Stop();finished=Stop()
        def work(factory,stop):
            started.set()
            if not stop.wait(5):raise AssertionError('shutdown did not signal stop')
            finished.set()
        with patch.dict(os.environ,{'WHATSAPP_WEEKLY_EXECUTOR_ENABLED':'true'}),patch('app.services.whatsapp_agenda.run_executor_batch',side_effect=work) as batch:
            async with executor_lifespan(None):
                self.assertTrue(await asyncio.to_thread(started.wait,5))
            self.assertTrue(finished.is_set());batch.assert_called_once()
