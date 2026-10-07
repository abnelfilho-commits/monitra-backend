"""Contextual identity and descriptive reading, with real authorized HTTP coverage."""
import os
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import event, text
from app.services.clinical_reading import ClinicalReading, ClinicalReadingService
from app.services.care_lines.registry import MENTAL_HEALTH, NEURO
from app.services.care_lines import CareLineCapabilityNotSupported
from app.services.mental_health_engine import describe_checkins
import test_checkin_bem_estar as foundation


def record(i, **answers):
    return SimpleNamespace(id=i, data_hora=datetime(2026, 1, i, tzinfo=timezone.utc),
                           respondente_pessoa_id=10, respostas=answers)


class ReadingTests(unittest.TestCase):
    def test_exclusive_identity(self):
        self.assertEqual(ClinicalReading(1, NEURO).patient_id, 1)
        r = ClinicalReading(care_line=MENTAL_HEALTH, pessoa_id=10, contexto_assistencial_id=20)
        self.assertIsNone(r.patient_id)
        for ids in ({}, {'pessoa_id': 1}, {'contexto_assistencial_id': 1}, {'patient_id': True},
                    {'patient_id': 0}, {'pessoa_id': -1, 'contexto_assistencial_id': 2},
                    {'pessoa_id': 1, 'contexto_assistencial_id': False},
                    {'patient_id': 1, 'pessoa_id': 1, 'contexto_assistencial_id': 2}):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                ClinicalReading(care_line=MENTAL_HEALTH, **ids)

    def test_contextual_dispatch_without_patient_resolver(self):
        service = ClinicalReadingService()
        with patch.object(service.resolver, 'resolve', side_effect=AssertionError('legacy resolver')):
            r = service.get_contextual_reading(pessoa_id=10, contexto_assistencial_id=20,
                                               care_line=MENTAL_HEALTH.code, checkins=[])
        self.assertIsNone(r.patient_id)
        self.assertEqual((r.pessoa_id, r.contexto_assistencial_id), (10, 20))
        self.assertIs(r.care_line, MENTAL_HEALTH)
        with self.assertRaises(CareLineCapabilityNotSupported):
            service.get_contextual_reading(pessoa_id=10, contexto_assistencial_id=20, care_line='NEURO', checkins=[])
        with self.assertRaises(ValueError):
            service.get_contextual_reading(pessoa_id=99, contexto_assistencial_id=20,
                                           care_line=MENTAL_HEALTH.code, checkins=[record(1)])

    def test_zero_and_one(self):
        r = describe_checkins([])
        self.assertEqual(r['clinical_state']['status'], 'SEM_DADOS')
        self.assertIsNone(r['risk']); self.assertIsNone(r['trend'])
        self.assertEqual(r['metadata']['total_registros'], 0)
        r = describe_checkins([record(1, humor='BOM')])
        self.assertEqual(r['clinical_state']['status'], 'MOMENTO_OBSERVADO')
        self.assertIn('Humor: bom', r['summary'])
        self.assertIn('Ainda não há histórico suficiente', r['summary'])

    def test_dimension_comparisons(self):
        for values, expected in ((['RUIM','REGULAR','BOM'],'MELHORA_OBSERVACIONAL'),
                                 (['BOM','REGULAR','RUIM'],'PIORA_OBSERVACIONAL'),
                                 (['BOM','BOM'],'ESTABILIDADE_OBSERVACIONAL'),
                                 (['RUIM','BOM','REGULAR'],'OSCILACAO')):
            records = [record(i, humor=v) for i,v in enumerate(values,1)]
            r = describe_checkins(list(reversed(records)))
            self.assertEqual(r['evidence']['dimensions']['humor']['state'],expected)
            self.assertIsNone(r['risk']); self.assertIsNone(r['trend'])
            self.assertNotIn('score', r)
            self.assertEqual(r['metadata']['record_ids'], list(range(1,len(values)+1)))
        r = describe_checkins([record(1, ansiedade='EXTREMA'), record(2, ansiedade='POUCA')])
        self.assertEqual(r['evidence']['dimensions']['ansiedade']['state'], 'MELHORA_OBSERVACIONAL')

    def test_opposing_dimensions_never_become_global_trend(self):
        r=describe_checkins([record(1,humor='RUIM',sono='BOM'),record(2,humor='BOM',sono='RUIM')])
        self.assertEqual(r['evidence']['dimensions']['humor']['state'],'MELHORA_OBSERVACIONAL')
        self.assertEqual(r['evidence']['dimensions']['sono']['state'],'PIORA_OBSERVACIONAL')
        self.assertIsNone(r['trend']);self.assertIsNone(r['risk'])

    def test_missing_never_improves_or_bridges(self):
        for missing in (None, 'NAO_SE_APLICA', 'UNKNOWN'):
            r=describe_checkins([record(1,trabalho='RUIM'),record(2,trabalho=missing),record(3,trabalho='BOM')])
            d=r['evidence']['dimensions']['trabalho']
            self.assertEqual(d['state'],'INSUFICIENTE'); self.assertIsNone(d['observations'][1]['value'])
            self.assertEqual(r['clinical_state']['status'],'INSUFICIENTE')

    def test_help_and_event_factual(self):
        r=describe_checkins([record(1,pedido_ajuda='SIM',evento_relevante='SIM',evento_descricao='<synthetic event>')])
        self.assertIn('solicitação explícita de apoio', r['summary'])
        self.assertEqual(len(r['alerts']),1)
        self.assertEqual(r['evidence']['relevant_events'][0]['description'],'<synthetic event>')
        self.assertIn('sem inferência de relação causal',r['summary'])
        self.assertIsNone(r['risk'])
        r=describe_checkins([record(1,pedido_ajuda='SIM'),record(2,pedido_ajuda='NAO')])
        self.assertIn('não há informação de resolução',r['summary'])


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ReadingHTTPTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.CheckinTests.tearDownClass.__func__)
    setUp=foundation.CheckinTests.setUp
    tearDown=foundation.CheckinTests.tearDown
    command_grant=foundation.CheckinTests.command_grant
    path=foundation.CheckinTests.path
    payload=foundation.CheckinTests.payload
    post=foundation.CheckinTests.post

    def test_zero_persisted_records_and_no_write(self):
        queries=[]
        def capture(conn,cursor,statement,params,ctx,many):queries.append(statement)
        event.listen(self.engine,'before_cursor_execute',capture)
        try:
            with patch.object(self.db,'commit',side_effect=AssertionError('GET commit')):
                response=self.client.get(self.path())
        finally:event.remove(self.engine,'before_cursor_execute',capture)
        self.assertEqual(response.status_code,200,response.text)
        r=response.json()['clinical_reading']
        self.assertEqual(r['metadata']['total_registros'],0)
        self.assertEqual(r['clinical_state']['status'],'SEM_DADOS')
        self.assertIsNone(r['patient_id']);self.assertEqual(r['pessoa_id'],self.person)
        self.assertEqual(r['contexto_assistencial_id'],self.open)
        self.assertFalse(any(q.lstrip().upper().startswith(('INSERT','UPDATE','DELETE')) for q in queries))
        self.assertFalse(any('paciente_modulos' in q for q in queries))

    def test_persisted_single_multiple_and_scope(self):
        p=self.payload();p['respostas']['humor']='RUIM'
        self.assertEqual(self.post(p).status_code,201)
        r=self.client.get(self.path()).json()['clinical_reading']
        self.assertEqual(r['clinical_state']['status'],'MOMENTO_OBSERVADO')
        p['respostas']['humor']='BOM';self.assertEqual(self.post(p).status_code,201)
        r=self.client.get(self.path()).json()['clinical_reading']
        self.assertEqual(r['metadata']['total_registros'],2)
        self.assertEqual(r['evidence']['dimensions']['humor']['state'],'MELHORA_OBSERVACIONAL')
        for change in (dict(person=self.person+10000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.client.get(self.path(**change)).status_code,404)
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed));self.db.commit()
        other=self.client.get(self.path(context=self.closed)).json()['clinical_reading']
        self.assertEqual(other['metadata']['total_registros'],0)

    def test_no_read_on_inactive_line_and_no_admin_bypass(self):
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open));self.db.commit()
        self.assertIsNone(self.client.get(self.path()).json()['clinical_reading'])
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE usuario_instituicao_acesso_id=:r'),dict(r=self.roots[0]));self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)
