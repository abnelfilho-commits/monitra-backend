"""Agenda management on disposable PostgreSQL 18. All external HTTP forbidden."""
import os
import unittest
from datetime import date, time, timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from sqlalchemy import select, text, inspect, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError, DBAPIError
from app.models.whatsapp_agenda import WhatsAppAgendaCheckin as Occurrence, WhatsAppAgendaEvento as Event
from app.models.whatsapp_contextual import AcompanhamentoWhatsApp as Follow
from app.schemas.whatsapp_mental import WhatsAppProgramacao
from app.services.whatsapp_agenda import slots, horizon
from app.services.whatsapp_programacao import configure, ZONE
from app.services.checkin_bem_estar import CheckinInvalid
import test_whatsapp_programacao as foundation

FRIDAY = foundation.FRIDAY
NOW = FRIDAY - timedelta(minutes=5)


class CalendarTests(unittest.TestCase):
    def test_calendar_limit_and_leap_day(self):
        self.assertEqual(horizon(date(2028, 2, 29)), date(2029, 2, 28))
        self.assertEqual(horizon(date(2026, 10, 30)), date(2027, 10, 30))

    def test_inclusive_end_local_date_and_strict_future(self):
        self.assertEqual(slots(4, time(19), date(2026, 10, 30), NOW), [FRIDAY])
        self.assertEqual(slots(4, time(19), date(2026, 10, 30), FRIDAY), [])
        self.assertEqual(slots(4, time(23, 30), date(2026, 10, 30), FRIDAY), [FRIDAY + timedelta(hours=4, minutes=30)])
        values = slots(4, time(19), date(2027, 10, 30), NOW)
        self.assertEqual(len(values), 53)
        self.assertTrue(all(b-a == timedelta(days=7) for a,b in zip(values, values[1:])))


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class AgendaTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.ScheduleTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.ScheduleTests.tearDownClass.__func__)
    tearDown = foundation.ScheduleTests.tearDown
    command_grant = foundation.ScheduleTests.command_grant
    counts = foundation.ScheduleTests.counts
    path = foundation.ScheduleTests.path
    config = foundation.ScheduleTests.config
    request = foundation.ScheduleTests.request

    def setUp(self):
        foundation.ScheduleTests.setUp(self)
        clock = patch('app.services.whatsapp_mental.now_utc', return_value=NOW)
        clock.start(); self.addCleanup(clock.stop)

    def payload(self, **changes):
        return dict(dict(dia_semana=4, horario_local='19:00', programacao_ativa=True,
            programacao_data_fim='2026-11-20', versao_esperada=0), **changes)

    def save(self, **changes):
        return self.request(payload=self.payload(**changes))

    def rows(self):
        self.db.expire_all()
        return list(self.db.scalars(select(Occurrence).where(Occurrence.acompanhamento_id == self.aid).order_by(Occurrence.previsto_em)))

    def audit_count(self):
        return self.db.scalar(select(func.count()).select_from(Event).where(Event.acompanhamento_id == self.aid))

    def test_create_contract_no_sends_idempotence_and_pagination(self):
        first = self.save(); self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()['programacao_versao'], 1)
        self.assertFalse(first.json()['execucao_automatica_ativa'])
        rows = self.rows(); self.assertEqual(len(rows), 4)
        self.assertEqual({r.status for r in rows}, {'AGENDADO'})
        before = self.audit_count()
        repeat = self.save(versao_esperada=1)
        self.assertEqual(repeat.status_code, 200, repeat.text)
        self.assertEqual(repeat.json(), first.json())
        with patch('app.services.whatsapp_mental.now_utc',return_value=FRIDAY+timedelta(days=30)):
            self.assertEqual(self.save(versao_esperada=1).json(), first.json())
        self.assertEqual(self.audit_count(), before)
        self.assertEqual(self.save().status_code, 409)
        page = self.request('GET', suffix='/agenda').json()
        self.assertEqual(len(page['itens']), 4); self.assertEqual(page['impedimentos'], [])
        from app.services.whatsapp_agenda import read
        p = read(self.db, self.scope, limit=2)
        p2 = read(self.db, self.scope, limit=2, offset=p['proximo_offset'])
        self.assertFalse({r['id'] for r in p['itens']} & {r['id'] for r in p2['itens']})
        self.assertIsNone(p2['proximo_offset'])
        self.assertEqual(self.counts(), (0,0,0))
        for table in ('whatsapp_solicitacoes_manuais','whatsapp_convite_envios'):
            self.assertEqual(self.db.scalar(text('SELECT count(*) FROM '+table)), 0)
        self.assertTrue(all(r.conversa_id is None and r.processamento_iniciado_em is None and r.processado_em is None for r in rows))
        self.assertNotIn(self.aid, self.w.eligible_ids(self.db)); self.db.rollback()
        response = self.request('POST', suffix='/disparar')
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(response.json()['detail']['code'], 'WEEKLY_EXECUTION_NOT_ENABLED')

    def test_legacy_configuration_not_converted_or_overwritten(self):
        self.assertEqual(self.request(payload=dict(dia_semana=4,horario_local='19:00',
            programacao_ativa=True,versao_esperada=0)).status_code,409)
        self.assertEqual(self.request().status_code,200)
        self.assertEqual(self.rows(),[])
        self.assertEqual(self.a.programacao_versao,0); self.assertIsNone(self.a.programacao_data_fim)
        self.assertEqual(self.save().status_code,200)
        self.assertEqual(self.request(payload=dict(dia_semana=2,horario_local='12:00',programacao_ativa=True)).status_code,409)
        self.assertEqual(self.save(programacao_data_fim=None,versao_esperada=1).status_code,409)
        result=self.request(payload=dict(dia_semana=2,horario_local='12:00',programacao_ativa=True,versao_esperada=1))
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['programacao_data_fim'],'2026-11-20')

    def test_end_limits_and_validation_atomicity(self):
        for end in ('2027-10-31','2026-10-29'):
            self.assertEqual(self.save(programacao_data_fim=end).status_code,409)
        self.assertEqual(self.rows(),[])
        self.assertEqual(self.save(programacao_data_fim='not-a-date').status_code,422)
        self.assertEqual(self.save(versao_esperada=True).status_code,422)
        self.assertEqual(self.save(programacao_data_fim='2027-10-30').status_code,200)
        self.assertEqual(len(self.rows()),53)

    def test_reprogram_pause_resume_reuse_and_history(self):
        self.save(); original={r.previsto_em:r.id for r in self.rows()}
        self.assertEqual(self.save(horario_local='20:00',versao_esperada=1).status_code,200)
        self.assertEqual(sum(r.status=='CANCELADO' for r in self.rows()),4)
        self.assertEqual(self.save(versao_esperada=2).status_code,200)
        self.assertEqual({r.previsto_em:r.id for r in self.rows() if r.status=='AGENDADO'},original)
        self.assertEqual(self.save(programacao_ativa=False,versao_esperada=3).status_code,200)
        self.assertEqual({r.status for r in self.rows()},{'BLOQUEADO','CANCELADO'})
        self.assertEqual(self.a.status,'ATIVO'); self.assertIsNone(self.a.proximo_envio_em)
        past=self.rows()[0]; snapshot=(past.id,past.status,past.programacao_versao,past.atualizado_em)
        with patch('app.services.whatsapp_mental.now_utc',return_value=FRIDAY+timedelta(days=1)):
            result=self.save(versao_esperada=4)
        self.assertEqual(result.status_code,200,result.text)
        self.db.refresh(past)
        self.assertEqual((past.id,past.status,past.programacao_versao,past.atualizado_em),snapshot)
        self.assertEqual(sum(r.status=='AGENDADO' for r in self.rows()),3)
        self.assertGreater(self.audit_count(),20)
        self.assertFalse(any(r.status in ('PERDIDO','PROCESSANDO','EXECUTADO') for r in self.rows()))

    def test_claimed_occurrence_not_reused(self):
        self.save(); row=self.rows()[0]
        row.status='PROCESSANDO'; row.processamento_iniciado_em=NOW; self.db.commit()
        self.save(horario_local='20:00',versao_esperada=1)
        self.save(versao_esperada=2)
        self.db.refresh(row)
        self.assertEqual(row.status,'PROCESSANDO'); self.assertEqual(row.programacao_versao,1)

    def test_isolation_read_write_and_invalid_pagination(self):
        self.save()
        for change in (dict(person=self.person+100000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.request(payload=self.payload(versao_esperada=1),**change).status_code,403)
            self.assertEqual(self.request('GET',suffix='/agenda',**change).status_code,403)
        self.assertEqual(len(self.rows()),4)

    def test_revoke_close_and_pause_invalidate_without_deleting_history(self):
        self.save()
        self.w.lifecycle(self.db,'pausar',**self.scope); self.db.commit()
        self.assertEqual({r.status for r in self.rows()},{'BLOQUEADO'})
        self.w.lifecycle(self.db,'reativar',**self.scope); self.db.commit()
        self.assertEqual({r.status for r in self.rows()},{'BLOQUEADO'})
        self.w.lifecycle(self.db,'encerrar',**self.scope); self.db.commit()
        self.assertEqual({r.status for r in self.rows()},{'CANCELADO'})
        self.assertEqual(self.save(versao_esperada=1).status_code,409)
        self.assertEqual(len(self.rows()),4)

    def test_authorization_revocation_and_preventive_barrier(self):
        self.save()
        from app.services.whatsapp_autorizacao import revoke_internal
        from app.services.whatsapp_comunicacao import coordinate_configured
        coordinate_configured(self.db,(self.phone,)); self.w.authorized(self.db,**self.scope)
        revoke_internal(self.db,self.a,origin='ENCERRAMENTO',reason='ENCERRAMENTO',actor=self.actor)
        self.db.commit()
        self.assertEqual({r.status for r in self.rows()},{'CANCELADO'})
        self.assertEqual(self.save(versao_esperada=1,horario_local='20:00').status_code,200)
        self.assertFalse(any(r.status=='AGENDADO' for r in self.rows()))
        self.assertIn('PRIOR_WHATSAPP_AUTHORIZATION_REVOKED',self.request('GET',suffix='/agenda').json()['impedimentos'])
        # Changing destination also cancels plans made while already revoked.
        self.w.configure(self.db,'55659'+str(self.open+100000).zfill(8),**self.scope)
        self.db.commit()
        self.assertEqual({r.status for r in self.rows()},{'CANCELADO'})

    def test_concurrent_configuration_one_version_wins(self):
        self.db.rollback()
        gate=Barrier(2)
        def write(hour):
            with Session(self.engine) as db:
                gate.wait(timeout=10)
                try:
                    result=configure(db,WhatsAppProgramacao(**self.payload(horario_local=hour)),**self.scope)
                    db.commit(); return result.programacao_versao
                except CheckinInvalid as exc:
                    db.rollback(); return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(write,('19:00','20:00')))
        self.assertCountEqual(results,[1,'SCHEDULE_VERSION_CONFLICT'])
        self.assertEqual(len(self.rows()),4)

    def test_constraints_audit_immutable_and_model_parity(self):
        self.save(); row=self.rows()[0]
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.add(Occurrence(acompanhamento_id=self.aid,previsto_em=row.previsto_em,status='AGENDADO',programacao_versao=1,motivo_estado='TEST'))
            self.db.flush()
        for statement in ('UPDATE whatsapp_agenda_eventos SET motivo=motivo', 'DELETE FROM whatsapp_agenda_eventos', 'TRUNCATE whatsapp_agenda_eventos'):
            with self.assertRaises(DBAPIError),self.db.begin_nested(): self.db.execute(text(statement))
        with self.assertRaises(IntegrityError),self.db.begin_nested():
            self.db.execute(text('UPDATE whatsapp_agenda_checkins SET conversa_id=2147483647 WHERE id=:id'),{'id':row.id})
        for model in (Occurrence,Event):
            physical={c['name']:c for c in inspect(self.engine).get_columns(model.__tablename__)}
            self.assertEqual(set(physical),set(model.__table__.c.keys()))
            for col in model.__table__.c:
                self.assertEqual(col.nullable,physical[col.name]['nullable'])
                self.assertEqual(str(col.type.compile(dialect=self.engine.dialect)),str(physical[col.name]['type'].compile(dialect=self.engine.dialect)))


# Real authenticated PARAR ingress and the existing manual dispatcher regressions.
if os.getenv('M0_TEST_POSTGRES_URL'):
    os.environ['DATABASE_URL'] = os.environ['M0_TEST_POSTGRES_URL']
import test_whatsapp_stop as stop_fixture
import test_whatsapp_manual as manual_fixture


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class AgendaStopTests(unittest.TestCase):
    setUpClass = classmethod(stop_fixture.StopTests.setUpClass.__func__)
    cleanup = classmethod(stop_fixture.StopTests.cleanup.__func__)
    snapshot = stop_fixture.StopTests.snapshot
    command_grant = stop_fixture.StopTests.command_grant
    path = stop_fixture.StopTests.path
    proof = stop_fixture.StopTests.proof
    incoming = stop_fixture.StopTests.incoming
    legacy = stop_fixture.StopTests.legacy

    def setUp(self):
        stop_fixture.StopTests.setUp(self)
        self.follow = self.db.get(Follow, self.db.get(stop_fixture.Conversation,self.cid).acompanhamento_whatsapp_id)
        local = self.now.astimezone(ZONE)
        configure(self.db,WhatsAppProgramacao(dia_semana=4,horario_local='19:00',programacao_ativa=True,
            programacao_data_fim=local.date()+timedelta(days=28),versao_esperada=0),**self.scope)
        self.db.commit()

    def test_contextual_stop_blocks_future_and_replay_is_idempotent(self):
        reference=self.proof()
        self.incoming(ref=reference)
        rows=list(self.db.scalars(select(Occurrence).where(Occurrence.acompanhamento_id==self.follow.id)))
        self.assertTrue(rows); self.assertEqual({r.status for r in rows},{'BLOQUEADO'})
        before=self.db.scalar(select(func.count()).select_from(Event))
        self.incoming(mid=self.mid,ref=reference)
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Event)),before)

    def test_preventive_stop_effective_barrier_without_cross_context_updates(self):
        from app.services.whatsapp_agenda import read
        self.legacy()
        before=self.db.scalar(select(func.count()).select_from(Event))
        self.incoming()
        self.assertEqual(self.db.scalar(select(func.count()).select_from(Event)),before)
        result=read(self.db,self.scope)
        self.assertIn('WHATSAPP_INTERROMPIDO',result['impedimentos'])
        self.assertFalse(result['execucao_automatica_ativa'])


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class AgendaManualTests(unittest.TestCase):
    create_prior_authorization = False
    setUpClass = classmethod(manual_fixture.ManualTests.setUpClass.__func__)
    cleanup = classmethod(manual_fixture.ManualTests.cleanup.__func__)
    snapshot = manual_fixture.ManualTests.snapshot
    command_grant = manual_fixture.ManualTests.command_grant
    path = manual_fixture.ManualTests.path
    setUp = manual_fixture.ManualTests.setUp
    response = manual_fixture.ManualTests.response
    allowed = manual_fixture.ManualTests.allowed
    invoke = manual_fixture.ManualTests.invoke

    def test_manual_and_replay_preserve_all_agenda_rows_and_schedule(self):
        from app.services.whatsapp_programacao import ZONE
        self.allowed()
        configure(self.db,WhatsAppProgramacao(dia_semana=4,horario_local='19:00',programacao_ativa=True,
            programacao_data_fim=self.now.astimezone(ZONE).date()+timedelta(days=28),versao_esperada=0),**self.scope)
        self.db.commit()
        def snapshot(db):
            result=[]
            for table in ('whatsapp_agenda_checkins','whatsapp_agenda_eventos'):
                result.append(db.execute(text('SELECT row_to_json(t)::text FROM '+table+' t ORDER BY id')).scalars().all())
            result.append(db.execute(text('SELECT proximo_envio_em, programacao_versao, programacao_data_fim FROM acompanhamentos_whatsapp WHERE id=:id'),{'id':self.aid}).one())
            return result
        before=snapshot(self.db); self.db.rollback()
        with patch('app.services.whatsapp_sender_service.requests.post',return_value=self.response()) as post:
            result=self.invoke(); self.assertEqual(result['estado'],'ACEITO')
            self.assertEqual(self.invoke(),result); post.assert_called_once()
        self.assertEqual(snapshot(self.db),before)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class AgendaMigrationTests(unittest.TestCase):
    schema_revision = 'mh_weekly_config_v1'
    setUpClass = classmethod(foundation.ScheduleTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.ScheduleTests.tearDownClass.__func__)
    tearDown = foundation.ScheduleTests.tearDown
    command_grant = foundation.ScheduleTests.command_grant
    path = foundation.ScheduleTests.path

    def setUp(self):
        foundation.foundation.MentalWhatsAppTests.setUp(self)
        self.aid=self.db.execute(text("""INSERT INTO acompanhamentos_whatsapp
            (contexto_assistencial_id,paciente_id,telefone,criado_por_usuario_id,
             dia_semana,horario_local,programacao_ativa,configurado_por_usuario_id,proximo_envio_em)
            SELECT id,paciente_id,'5511999999999',:actor,4,'19:00',true,:actor,clock_timestamp()+interval '7 days'
            FROM contextos_assistenciais WHERE id=:context RETURNING id"""),{'actor':self.actor,'context':self.open}).scalar_one()
        self.db.commit()

    def test_upgrade_preserves_active_legacy_preference_without_conversion(self):
        from alembic import command
        from test_m0_baseline import config
        before=dict(self.db.execute(text('SELECT * FROM acompanhamentos_whatsapp WHERE id=:id'),{'id':self.aid}).mappings().one())
        self.db.rollback()
        with self.engine.begin() as connection:
            command.upgrade(config(connection),'mh_agenda_v1')
        after=dict(self.db.execute(text('SELECT * FROM acompanhamentos_whatsapp WHERE id=:id'),{'id':self.aid}).mappings().one())
        self.assertIsNone(after.pop('programacao_data_fim'))
        self.assertEqual(after.pop('programacao_versao'),0)
        self.assertEqual(before,after)
        for table in ('whatsapp_agenda_checkins','whatsapp_agenda_eventos'):
            self.assertEqual(self.db.scalar(text('SELECT count(*) FROM '+table)),0)
        self.assertEqual(self.db.scalar(text('SELECT version_num FROM alembic_version')),'mh_agenda_v1')
        fks=inspect(self.engine).get_foreign_keys('whatsapp_agenda_checkins')
        self.assertTrue(any(f['constrained_columns']==['conversa_id','acompanhamento_id']
            and f['referred_columns']==['id','acompanhamento_whatsapp_id'] for f in fks))
        # The new tables retain the E14B writer fence even without a runtime-active gate.
        with self.engine.connect() as connection:
            with self.assertRaises(DBAPIError):
                connection.exec_driver_sql("SET LOCAL integra.whatsapp_protocol = ''")
                connection.exec_driver_sql("INSERT INTO whatsapp_agenda_eventos(acompanhamento_id,programacao_versao,origem,motivo) VALUES (1,1,'TEST','TEST')")
            connection.rollback()
