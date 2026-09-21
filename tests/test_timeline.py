"""Synthetic read-only source tests; no operational database access."""
import ast
import os
import unittest
from dataclasses import replace
from datetime import date, datetime, time, timezone, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.services.timeline.models import *
from app.services.timeline_service import TimelineService
from app.services.care_lines import NEURO, CARDIO, CareLineRegistry, CareLineDefinition
from app.services.care_lines.exceptions import CareLineNotFound
from app.services.timeline import sources

D = date(2026, 1, 10)


def event(source=SourceType.DIAGNOSIS, id=1, **kwargs):
    values = dict(source_type=source, source_id=id, patient_id=10, care_line=None,
        care_line_association=CareLineAssociation.UNASSIGNED, event_type=EventType.DIAGNOSIS,
        title='synthetic', reference_date=D, temporal_precision=TemporalPrecision.DATE)
    values.update(kwargs)
    return TimelineEvent(**values)


class ContractTests(unittest.TestCase):
    def test_optional_and_identity(self):
        a = event()
        b = event(SourceType.GENERIC_INTERVENTION)
        self.assertNotEqual((a.source_type,a.source_id),(b.source_type,b.source_id))
        self.assertIsNone(a.reference_time)
        self.assertIsNone(a.actor)
        self.assertIsNone(a.summary)

    def test_metadata_isolated(self):
        original = {'items':[]}
        a, b = event(metadata=original), event(metadata=original)
        a.metadata['items'].append(1)
        self.assertEqual(original, b.metadata)
        self.assertEqual(b.metadata, {'items':[]})

    def test_precision_validation(self):
        with self.assertRaises(ValueError):
            event(reference_time=time(10))
        with self.assertRaises(ValueError):
            event(reference_date=None)
        with self.assertRaises(TypeError):
            event(care_line='NEURO')

    def test_required_identity_validation(self):
        for args in ({'source_id':0}, {'patient_id':True}, {'created_at':'today'}):
            with self.assertRaises((ValueError, TypeError)):
                event(**args)

    def test_query_validation(self):
        for args in ({'scope':'CARE_LINE'}, {'requested_care_line':'NEURO'},
                     {'mode':'BOUNDED'}, {'limit':1}):
            with self.assertRaises(ValueError):
                TimelineQuery(10, **args)

    def test_ordering_and_timezone_preservation(self):
        offset = timezone(timedelta(hours=-4))
        timed = event(id=2, reference_time=time(9,tzinfo=offset), temporal_precision='DATETIME')
        later = event(id=3, reference_time=time(10), temporal_precision='DATETIME')
        fallback = event(id=4, reference_date=None, temporal_precision=None,
                         created_at=datetime(2026,1,10,23))
        day = event(id=1)
        result = sorted([fallback,day,timed,later], key=event_order_key)
        self.assertEqual([e.source_id for e in result], [3,2,1,4])
        self.assertEqual(timed.reference_time.utcoffset(), timedelta(hours=-4))
        self.assertIsNone(fallback.created_at.tzinfo)

    def test_tie_break_and_no_date(self):
        result = sorted([event(id=2), event(id=1), event(SourceType.CARDIO_INTERVENTION),
                         event(id=3, reference_date=None, temporal_precision=None)], key=event_order_key)
        self.assertEqual([(e.source_type.value,e.source_id) for e in result],
            [('CARDIO_INTERVENTION',1),('DIAGNOSIS',1),('DIAGNOSIS',2),('DIAGNOSIS',3)])

    def test_python39_and_no_clinical_calculation(self):
        root = Path(__file__).resolve().parents[1] / 'app/services/timeline'
        for path in root.rglob('*.py'):
            source = path.read_text()
            ast.parse(source, feature_version=(3,9))
            for forbidden in ('calcular_score', 'classificar_risco', 'ClinicalReadingService',
                              'gerar_eventos_clinicos', 'calcular_tendencia'):
                self.assertNotIn(forbidden, source)


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        self.db = Session(self.engine)
        schemas = {
            'formularios_modulo':'id INTEGER, modulo_id INTEGER, tipo TEXT, ativo BOOLEAN',
            'registros_longitudinais':'id INTEGER, paciente_id INTEGER, modulo_id INTEGER, formulario_id INTEGER, data_registro TEXT, criado_em TEXT, origem TEXT, criado_por_usuario_id INTEGER, criado_por_responsavel_id INTEGER, observacoes TEXT',
            'campos_formulario':'id INTEGER, formulario_id INTEGER, nome_campo TEXT',
            'respostas_registro':'registro_id INTEGER, campo_id INTEGER, valor_texto TEXT, valor_numero NUMERIC, valor_booleano BOOLEAN, valor_data TEXT, valor_hora TEXT, valor_json TEXT',
            'intervencoes':'id INTEGER, modulo_id INTEGER, paciente_id INTEGER, profissional_id INTEGER, tipo TEXT, descricao TEXT, data_intervencao TEXT, created_at TEXT',
            'intervencoes_cardiometabolicas':'modulo_id INTEGER, id INTEGER, paciente_id INTEGER, tipo TEXT, descricao TEXT, prioridade TEXT, created_at TEXT',
            'avaliacoes_clinicas':'id INTEGER, paciente_id INTEGER, modulo_id INTEGER, registro_id INTEGER, instrumento TEXT, score NUMERIC, classificacao TEXT, interpretacao TEXT, profissional_id INTEGER, status TEXT, executado_em TEXT, created_at TEXT',
            'pts':'id INTEGER, modulo_id INTEGER, paciente_id INTEGER',
            'agenda_cuidados':'id INTEGER, pts_id INTEGER, profissional_id INTEGER',
            'sessoes_assistenciais':'id INTEGER, paciente_id INTEGER, agenda_cuidado_id INTEGER, profissional_id INTEGER, data_realizacao TEXT, hora_fim_real TEXT, created_at TEXT, numero_sessao INTEGER, registro_longitudinal_id INTEGER, status TEXT',
            'diagnosticos':'modulo_id INTEGER, id INTEGER, paciente_id INTEGER, data_diagnostico TEXT, created_at TEXT, descricao_clinica TEXT, medico_nome TEXT, cid TEXT, status TEXT',
        }
        for table, columns in schemas.items():
            self.db.execute(text('CREATE TABLE '+table+' ('+columns+')'))
        for id, module, kind in ((1,1,'REGISTRO_DIARIO'),(2,2,'REGISTRO_DIARIO'),
                                  (3,1,'ASSESSMENT'),(4,1,'LONGITUDINAL'),(5,99,'REGISTRO_DIARIO')):
            self.insert('formularios_modulo', id=id, modulo_id=module, tipo=kind, ativo=False)
            self.insert('registros_longitudinais', id=id, paciente_id=10, modulo_id=module,
                        formulario_id=id, data_registro='2026-01-10', criado_em='2026-02-01T12:00:00', origem='PROFISSIONAL')
        self.insert('intervencoes', modulo_id=1, id=1, paciente_id=10, tipo='test', descricao='authored', data_intervencao='2026-01-10T11:00:00')
        self.insert('intervencoes_cardiometabolicas', modulo_id=2, id=1, paciente_id=10, tipo='test', descricao='authored cardio', prioridade='alta', created_at='2026-01-10T12:00:00')
        self.insert('avaliacoes_clinicas', id=1, paciente_id=10, modulo_id=1, registro_id=3, instrumento='MCHAT', score=2, interpretacao='persisted', status='CONCLUIDA')
        self.insert('pts', id=1, modulo_id=2, paciente_id=10)
        self.insert('agenda_cuidados', id=1, pts_id=1)
        self.insert('sessoes_assistenciais', id=1, paciente_id=10, agenda_cuidado_id=1,
                    status='REALIZADA', data_realizacao='2026-01-11', hora_fim_real='10:30:00')
        self.insert('diagnosticos', modulo_id=1, id=1, paciente_id=10, data_diagnostico='2026-01-09', medico_nome='synthetic', status='ATIVO')
        self.db.commit()

    def insert(self, table, **values):
        self.db.execute(text('INSERT INTO '+table+' ('+','.join(values)+') VALUES ('+
                             ','.join(':'+key for key in values)+')'), values)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_daily_classification_and_inactive_history(self):
        result = sources.daily_records(self.db,10,CareLineRegistry())
        self.assertEqual({e.source_id for e in result},{1,2,5})
        self.assertTrue(all(e.reference_time is None for e in result))
        self.assertEqual(result[0].reference_date,D)

    def test_form_module_mismatch_excluded(self):
        self.db.execute(text('UPDATE registros_longitudinais SET modulo_id=2 WHERE id=1'))
        self.assertNotIn(1,[e.source_id for e in sources.daily_records(self.db,10,CareLineRegistry())])

    def test_patient_scope_and_unknown_module(self):
        result = TimelineService.get_events(self.db,TimelineQuery(10))
        self.assertEqual(len(result),8)
        self.assertEqual(len({(e.source_type,e.source_id) for e in result}),8)
        self.assertFalse(any(e.care_line_association==CareLineAssociation.UNASSIGNED for e in result))
        self.assertFalse(any(e.care_line_association==CareLineAssociation.TRANSVERSAL for e in result))
        unknown = next(e for e in result if e.source_type==SourceType.LONGITUDINAL_RECORD and e.source_id==5)
        self.assertIsNone(unknown.care_line)
        self.assertEqual(unknown.metadata['module_id'],99)
        self.assertEqual(unknown.care_line_association,CareLineAssociation.EXPLICIT)

    def test_no_active_link_required_for_historical_line(self):
        registry = CareLineRegistry([replace(NEURO,active=False),CARDIO])
        result = TimelineService.get_events(self.db,TimelineQuery(10,scope='CARE_LINE',requested_care_line='NEURO'),registry=registry)
        self.assertEqual({e.event_type for e in result},{EventType.DAILY_RECORD,EventType.ASSESSMENT,EventType.INTERVENTION,EventType.DIAGNOSIS})

    def test_other_patient_and_noncompleted_sources_excluded(self):
        self.insert('diagnosticos',id=2,paciente_id=11,data_diagnostico='2026-01-01',status='ATIVO')
        self.insert('diagnosticos',id=3,paciente_id=10,data_diagnostico='2026-01-01',status='CANCELADO')
        self.insert('sessoes_assistenciais',id=2,paciente_id=10,status='AGENDADA')
        self.assertEqual(len(TimelineService.get_events(self.db,TimelineQuery(10))),8)

    def test_care_line_scope(self):
        result = TimelineService.get_events(self.db,TimelineQuery(10,scope='CARE_LINE',requested_care_line='CARDIO'))
        self.assertEqual({e.source_type for e in result}, {SourceType.LONGITUDINAL_RECORD,SourceType.CARDIO_INTERVENTION,SourceType.ASSISTENTIAL_SESSION})
        self.assertTrue(all(e.care_line==CARDIO for e in result))
        with self.assertRaises(CareLineNotFound):
            TimelineService.get_events(self.db,TimelineQuery(10,scope='CARE_LINE',requested_care_line='missing'))

    def test_explicit_generic_module_and_unknown_identity(self):
        self.insert('intervencoes',id=2,paciente_id=10,modulo_id=1,tipo='authored',
                    descricao='new',data_intervencao='2026-01-10T13:45:00')
        self.insert('intervencoes',id=3,paciente_id=10,modulo_id=999,tipo='authored',
                    descricao='unknown',data_intervencao='2026-01-10T13:45:00')
        patient=TimelineService.get_events(self.db,TimelineQuery(10))
        generic=[e for e in patient if e.source_type==SourceType.GENERIC_INTERVENTION]
        self.assertEqual(len(generic),3)
        known=next(e for e in generic if e.source_id==2)
        self.assertEqual(known.care_line,NEURO)
        self.assertEqual(known.care_line_association,CareLineAssociation.EXPLICIT)
        self.assertEqual(known.reference_date.isoformat(),'2026-01-10')
        self.assertEqual(known.reference_time.isoformat(),'13:45:00')
        unknown=next(e for e in generic if e.source_id==3)
        self.assertIsNone(unknown.care_line)
        self.assertEqual(unknown.care_line_association,CareLineAssociation.EXPLICIT)
        self.assertEqual(unknown.metadata['module_id'],999)
        scoped=TimelineService.get_events(self.db,TimelineQuery(10,scope='CARE_LINE',requested_care_line='NEURO'))
        self.assertEqual([e.source_id for e in scoped if e.source_type==SourceType.GENERIC_INTERVENTION],[2, 1])

    def test_bounded_is_global_prefix(self):
        full = TimelineService.get_events(self.db,TimelineQuery(10))
        bounded = TimelineService.get_events(self.db,TimelineQuery(10,mode='BOUNDED',limit=2))
        self.assertEqual(bounded,full[:2])

    def test_session_unassigned_without_canonical_relation(self):
        self.db.execute(text('UPDATE pts SET paciente_id=11'))
        result = sources.sessions(self.db,10,CareLineRegistry())[0]
        self.assertEqual(result.care_line_association,CareLineAssociation.UNASSIGNED)
        self.assertIsNone(result.care_line)

    def test_cardio_missing_interpretation_not_fabricated(self):
        result = TimelineService.get_events(self.db,TimelineQuery(10,scope='CARE_LINE',requested_care_line='CARDIO'))
        daily = next(e for e in result if e.event_type==EventType.DAILY_RECORD)
        self.assertIsNone(daily.summary)
        for field in ('risk','score','protocol','trend','imc'):
            self.assertNotIn(field,daily.metadata)
        intervention = next(e for e in result if e.source_type==SourceType.CARDIO_INTERVENTION)
        self.assertIsNone(intervention.reference_date)
        self.assertIsNone(intervention.temporal_precision)
        self.assertIsNotNone(intervention.created_at)

    def test_answers_scoped_and_duplicates_preserved(self):
        self.insert('campos_formulario',id=1,formulario_id=2,nome_campo='peso')
        self.insert('campos_formulario',id=2,formulario_id=1,nome_campo='foreign')
        for value in (100,101):
            self.insert('respostas_registro',registro_id=2,campo_id=1,valor_numero=value)
        self.insert('respostas_registro',registro_id=2,campo_id=2,valor_numero=999)
        result = sources.daily_records(self.db,10,CareLineRegistry())
        answers = next(e for e in result if e.source_id==2).metadata['answers']
        self.assertEqual(len(answers),2)
        self.assertEqual({a['name'] for a in answers},{'peso'})

    def test_future_line_registration_without_core_edit(self):
        future = replace(NEURO,code='FUTURE',slug='future',module_id=99)
        registry = CareLineRegistry([NEURO,CARDIO,future])
        result = TimelineService.get_events(self.db,TimelineQuery(10,scope='CARE_LINE',requested_care_line='FUTURE'),registry=registry)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0].care_line,future)

    def test_cross_patient_source_and_duplicate_identity_rejected(self):
        for records in ([event(patient_id=11)],[event(),event()]):
            with self.assertRaises(ValueError):
                TimelineService.get_events(None,TimelineQuery(10),sources=[lambda *args:records])


class LegacyTests(unittest.TestCase):
    def fake_db(self):
        def execute(sql, params):
            sql = str(sql)
            if 'FROM registros_longitudinais rl' in sql:
                data = [SimpleNamespace(id=id,paciente_id=10,data_registro=D,
                    criado_em=datetime(2026,2,1),origem='RESPONSAVEL',observacao='authored',
                    sono_qualidade=4,irritabilidade=2,crise_sensorial=2,tempo_tela='MENOS_1H',
                    seletividade_alimentar='LEVE',aceitou_alimento_novo=False) for id in (1,3)]
            elif 'FROM intervencoes' in sql:
                data = [SimpleNamespace(id=1,paciente_id=10,data_intervencao=datetime(2026,1,1),
                    created_at=datetime(2026,1,2),descricao='intervention',profissional_id=9)]
            else:
                data = [SimpleNamespace(id=1,registro_id=3,instrumento='MCHAT',score=2,
                    classificacao='persisted',created_at=datetime(2026,1,3))]
            return SimpleNamespace(fetchall=lambda:data)
        return SimpleNamespace(execute=execute)

    def test_report_full_count_and_legacy_dates(self):
        with patch('app.services.timeline_service.TimelineEventService.obter_eventos_paciente',return_value=[]):
            result = TimelineService.get_timeline(self.fake_db(),10)
        self.assertEqual(len(result),4)  # Includes legacy misclassified assessment record.
        self.assertEqual(sum(e['tipo_evento']=='REGISTRO_DIARIO' for e in result),2)
        self.assertEqual(result[0]['data'],'2026-02-01T00:00:00+00:00')
        self.assertNotIn('sono_qualidade',result[0])

    def test_neuro_shape_and_endpoint_facade(self):
        from app.routers.timeline import obter_timeline_paciente
        with patch('app.services.timeline_service.TimelineEventService.obter_eventos_paciente',return_value=[]):
            with patch("app.routers.timeline.authorized_patient"):
                result = obter_timeline_paciente(10,self.fake_db(),SimpleNamespace(id=1))
        self.assertEqual(len(result),4)
        self.assertEqual(result[0]['sono_qualidade'],'4')
        self.assertEqual(result[0]['crise_sensorial'],True)
        self.assertEqual(result[0]['origem'],'RESPONSAVEL')
        self.assertEqual(result[0]['id'],1)

    def test_report_provider_requires_line_and_period(self):
        from app.services.report_engine.providers.timeline_provider import TimelineProvider
        from datetime import date
        context = SimpleNamespace(db=self.fake_db(), subject_id=10, module='NEURO',
            period_start=date(2026,1,1), period_end=date(2026,2,1))
        with patch.object(TimelineService, 'get_events', return_value=[]) as source:
            result = TimelineProvider().collect(context)
        self.assertEqual(source.call_args.args[1].requested_care_line, 'NEURO')
        self.assertEqual(result.metadata['total_events'], 0)

    def test_neuro_http_facade(self):
        import asyncio
        import json
        from fastapi import FastAPI
        from app.database import get_db
        from app.routers.timeline import router
        app = FastAPI()
        app.include_router(router)
        from app.core.deps import get_usuario_atual
        app.dependency_overrides[get_usuario_atual] = lambda: SimpleNamespace(id=1)
        app.dependency_overrides[get_db] = self.fake_db
        async def request():
            messages = []
            async def receive():
                return {'type':'http.request', 'body':b'', 'more_body':False}
            async def send(message):
                messages.append(message)
            scope = {'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                     'method':'GET','scheme':'http','path':'/timeline/pacientes/10',
                     'raw_path':b'/timeline/pacientes/10','query_string':b'',
                     'headers':[], 'client':('127.0.0.1',1),'server':('test',80),'root_path':''}
            await app(scope,receive,send)
            self.assertEqual(next(m['status'] for m in messages if m['type']=='http.response.start'),200)
            return json.loads(b''.join(m.get('body',b'') for m in messages))
        with patch('app.services.timeline_service.TimelineEventService.obter_eventos_paciente',return_value=[]):
            with patch('app.routers.timeline.authorized_patient'):
                result = asyncio.run(request())
        self.assertEqual(len(result),4)
        self.assertEqual(result[0]['tipo_evento'],'REGISTRO_DIARIO')
        self.assertEqual(result[0]['sono_qualidade'],'4')
