"""Weekly configuration on disposable PostgreSQL; no external transport."""
import json
import os
import unittest
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qsl
from sqlalchemy import text, inspect
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError
from app.schemas.whatsapp_mental import WhatsAppProgramacao
from app.services.whatsapp_programacao import next_occurrence, due_in_window
import test_whatsapp_mental as foundation

UTC = timezone.utc
FRIDAY = datetime(2026, 10, 30, 23, tzinfo=UTC)  # Friday 19:00 Cuiaba


class CalculationTests(unittest.TestCase):
    def test_future_and_date_rollover(self):
        self.assertEqual(next_occurrence(4, time(19), FRIDAY - timedelta(minutes=1)), FRIDAY)
        self.assertEqual(next_occurrence(4, time(23, 30), FRIDAY), datetime(2026,10,31,3,30,tzinfo=UTC))
        self.assertEqual(next_occurrence(4, time(19), FRIDAY), FRIDAY + timedelta(days=7))

    def test_tolerance_boundaries_and_no_backlog(self):
        for delta, expected in [(timedelta(0), FRIDAY), (timedelta(hours=2), FRIDAY),
                                (timedelta(hours=2,microseconds=1), FRIDAY+timedelta(days=7)),
                                (timedelta(days=18), FRIDAY+timedelta(days=21))]:
            with self.subTest(delta=delta):
                self.assertEqual(next_occurrence(4,time(19),FRIDAY+delta,allow_late=True), expected)
        for minutes in (5,90,120):
            self.assertEqual(next_occurrence(4,time(19),FRIDAY+timedelta(minutes=minutes)),FRIDAY+timedelta(days=7))

    def test_temporal_eligibility_only(self):
        f=SimpleNamespace(programacao_ativa=True,dia_semana=4,proximo_envio_em=FRIDAY)
        for delta,expected in [(-1,False),(0,True),(7200,True),(7201,False)]:
            self.assertEqual(due_in_window(f,FRIDAY+timedelta(seconds=delta)),expected)
        f.programacao_ativa=False
        self.assertFalse(due_in_window(f,FRIDAY))
        with self.assertRaises(ValueError): next_occurrence(4,time(19),datetime(2026,10,30))

    def test_payload_no_timezone_impersonation_or_coercion(self):
        base=dict(dia_semana=4,horario_local='19:00',programacao_ativa=True)
        for changes in ({'dia_semana':7},{'dia_semana':-1},{'dia_semana':True},
                        {'horario_local':'19:00-04:00'},{'horario_local':'19:00:01'},
                        {'horario_local':3600},{'programacao_ativa':'false'},
                        {'configurado_por_usuario_id':1},{'proximo_envio_em':'2026-01-01'}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                WhatsAppProgramacao(**dict(base,**changes))


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ScheduleTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.MentalWhatsAppTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.MentalWhatsAppTests.tearDownClass.__func__)
    tearDown=foundation.MentalWhatsAppTests.tearDown
    command_grant=foundation.MentalWhatsAppTests.command_grant
    counts=foundation.MentalWhatsAppTests.counts
    path=foundation.MentalWhatsAppTests.path
    config=foundation.MentalWhatsAppTests.config

    def setUp(self):
        foundation.MentalWhatsAppTests.setUp(self)
        guard=patch('requests.sessions.Session.request',side_effect=AssertionError('No external HTTP'))
        guard.start();self.addCleanup(guard.stop)
        self.a=self.config()

    def request(self, method='PUT', payload=None, suffix='/programacao', **changes):
        url=urlsplit(self.path(**changes))
        return self.client.request(method,url.path+'/whatsapp'+suffix,params=dict(parse_qsl(url.query)),
            body=json.dumps(payload or dict(dia_semana=4,horario_local='19:00',programacao_ativa=True)).encode(),
            headers={'Content-Type':'application/json'})

    def test_config_get_idempotent_pause_resume_and_change(self):
        with patch('app.services.whatsapp_mental.now_utc',return_value=FRIDAY-timedelta(minutes=5)):
            response=self.request()
        self.assertEqual(response.status_code,200,response.text)
        d=response.json();self.assertEqual(d['dia_semana'],4)
        self.assertEqual(d['configurado_por_usuario_id'],self.actor)
        self.assertEqual(datetime.fromisoformat(d['proximo_envio_em'].replace('Z','+00:00')),FRIDAY)
        with patch('app.services.whatsapp_mental.now_utc',return_value=FRIDAY+timedelta(days=3)):
            self.assertEqual(self.request().json()['proximo_envio_em'],d['proximo_envio_em'])
            paused=self.request(payload=dict(dia_semana=4,horario_local='19:00',programacao_ativa=False)).json()
            self.assertIsNone(paused['proximo_envio_em']);self.assertEqual(paused['status'],'ATIVO')
            self.assertEqual((paused['dia_semana'],paused['horario_local']),(4,'19:00:00'))
            resumed=self.request().json()
            self.assertEqual(datetime.fromisoformat(resumed['proximo_envio_em'].replace('Z','+00:00')),FRIDAY+timedelta(days=7))
            changed=self.request(payload=dict(dia_semana=4,horario_local='23:30',programacao_ativa=True)).json()
        self.assertEqual(datetime.fromisoformat(changed['proximo_envio_em'].replace('Z','+00:00')),datetime(2026,11,7,3,30,tzinfo=UTC))
        self.assertEqual(self.request('GET',suffix='').json()['horario_local'],'23:30:00')
        self.assertEqual(self.counts(),(0,0,0))

    def test_explicit_save_after_destination_change_restores_missing_date(self):
        self.request()
        self.w.configure(self.db,'55659'+str(self.open+100000).zfill(8),**self.scope)
        self.db.commit()
        self.db.refresh(self.a);self.assertIsNone(self.a.proximo_envio_em)
        with patch('app.services.whatsapp_mental.now_utc',return_value=FRIDAY+timedelta(days=3)):
            response=self.request()
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(datetime.fromisoformat(response.json()['proximo_envio_em'].replace('Z','+00:00')),FRIDAY+timedelta(days=7))

    def test_no_automatic_execution_for_active_or_paused_preferences(self):
        for active in (True,False):
            self.request(payload=dict(dia_semana=4,horario_local='19:00',programacao_ativa=active))
            self.assertNotIn(self.aid,self.w.eligible_ids(self.db));self.db.rollback()
            response=self.request('POST',suffix='/disparar')
            self.assertEqual(response.status_code,409,response.text)
            self.assertEqual(response.json()['detail']['code'],'WEEKLY_EXECUTION_NOT_ENABLED')
            self.assertEqual(self.db.scalar(text('SELECT count(*) FROM whatsapp_conversas_contextuais WHERE acompanhamento_whatsapp_id=:i'),dict(i=self.aid)),0)

    def test_pause_does_not_cancel_manual_conversation_or_mutate_followup(self):
        self.request()
        before=(self.a.dia_semana,self.a.horario_local,self.a.programacao_ativa,self.a.proximo_envio_em)
        conversation=self.w.prepare(self.db,self.aid,manual=True);self.db.commit()
        self.db.refresh(self.a)
        self.assertEqual(before,(self.a.dia_semana,self.a.horario_local,self.a.programacao_ativa,self.a.proximo_envio_em))
        self.request(payload=dict(dia_semana=4,horario_local='19:00',programacao_ativa=False))
        self.db.refresh(conversation)
        self.assertEqual(conversation.status,'AGUARDANDO_ACEITE')
        self.assertEqual(self.a.status,'ATIVO');self.assertEqual(self.a.consentimento_status,'PENDENTE')

    def test_contextual_permission_and_isolation(self):
        for change in (dict(person=self.person+100000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.request(**change).status_code,403)
        for sql,i in [('DELETE FROM concessoes_assistenciais WHERE id=:i',self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']),
                      ('DELETE FROM contexto_profissionais WHERE id=:i',self.participations[self.open]),
                      ('UPDATE profissional_instituicoes SET ativo=false WHERE id=:i',self.links[0]),
                      ('UPDATE usuarios SET ativo=false WHERE id=:i',self.actor)]:
            self.db.execute(text(sql),dict(i=i))
            self.assertEqual(self.request().status_code,403)
        self.db.refresh(self.a);self.assertIsNone(self.a.dia_semana)
        self.assertFalse(self.a.programacao_ativa)

    def test_database_constraints_and_inactive_default(self):
        self.assertFalse(self.a.programacao_ativa);self.assertIsNone(self.a.dia_semana)
        for sql in ('dia_semana=8', 'programacao_ativa=true', "dia_semana=4,horario_local='19:00',configurado_por_usuario_id=2147483647"):
            with self.assertRaises(IntegrityError),self.db.begin_nested():
                self.db.execute(text('UPDATE acompanhamentos_whatsapp SET '+sql+' WHERE id=:i'),dict(i=self.aid))
        columns={c['name']:c for c in inspect(self.engine).get_columns('acompanhamentos_whatsapp')}
        self.assertFalse(columns['programacao_ativa']['nullable'])
        self.assertEqual(str(columns['horario_local']['type']),'TIME')

    def test_revoked_does_not_configure(self):
        self.a.consentimento_status='REVOGADO';self.db.commit()
        self.assertEqual(self.request().status_code,409)
        self.db.refresh(self.a);self.assertIsNone(self.a.dia_semana)
