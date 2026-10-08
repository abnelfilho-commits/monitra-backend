"""Source-bound synthesis: canonical results, no derived clinical judgments."""
import unittest
from copy import deepcopy
from datetime import datetime, timezone, date
from types import SimpleNamespace as Row
from sqlalchemy import text
from app.services.mental_health_engine import describe_checkins, summarize_sources
from app.services.clinical_reading import ClinicalReadingService
from app.services.clinical_reading.providers.assessment_evidence import assessment_evidence
from app.services.clinical_engine.context import AssessmentContext
from app.services.clinical_engine.assessments.phq9_engine import PHQ9Engine
from app.services.clinical_engine.assessments.gad7_engine import GAD7Engine
from app.services.clinical_engine.assessments.cbi_engine import CBIEngine
from app.services.cbi_contract import FIELDS
import test_assessment_evidence as foundation
import json
from urllib.parse import urlsplit, parse_qsl


def application(key, i=1, value='1', item9=None):
    fields=[x[0] for x in FIELDS] if key=='cbi' else [f'{key}_{n}' for n in range(1,10 if key=='phq9' else 8)]
    answers=dict.fromkeys(fields,value)
    if item9 is not None:answers['phq9_9']=item9
    engine={'phq9':PHQ9Engine,'gad7':GAD7Engine,'cbi':CBIEngine}[key]()
    result=engine.executar(AssessmentContext(registro_id=i,instrumento=engine.instrumento,respostas=answers,modulo_id=3,metadata={'contexto_assistencial_id':2}))
    return Row(id=i,registro_id=i,data_hora=datetime(2026,1,i,tzinfo=timezone.utc),registrador_usuario_id=4,registrador_profissional_id=5,resultado=result)


def evidence(**groups):
    return assessment_evidence(pessoa_id=1,contexto_assistencial_id=2,instituicao_id=3,applications=groups)


def checkins():
    return [Row(id=i,data_hora=datetime(2026,1,i,tzinfo=timezone.utc),respondente_pessoa_id=1,respostas={'humor':v,'pedido_ajuda':'SIM'}) for i,v in enumerate(['BOM','RUIM','BOM'],1)]


def clinical_record(**extra):
    return Row(id=1,pessoa_id=1,contexto_assistencial_id=2,modulo_id=3,**extra)


class SummaryTests(unittest.TestCase):
    def reading(self,records=(),assessments=None,diagnoses=(),interventions=()):
        return ClinicalReadingService().get_contextual_reading(pessoa_id=1,contexto_assistencial_id=2,care_line='MENTAL_HEALTH',checkins=records,assessments=assessments,diagnoses=diagnoses,interventions=interventions)

    def test_checkins_only_and_empty_are_byte_identical(self):
        for records in ([],checkins()[:1],checkins()):
            original=describe_checkins(records);reading=self.reading(records)
            self.assertEqual(reading.summary,original['summary'])
            self.assertEqual(reading.clinical_state,original['clinical_state'])
            self.assertEqual(reading.evidence['dimensions'],original['evidence']['dimensions'])
            self.assertEqual(reading.alerts,original['alerts'])

    def test_each_instrument_without_and_with_checkins(self):
        for key,label in [('phq9','PHQ-9'),('gad7','GAD-7'),('cbi','CBI')]:
            for records in ([],checkins()):
                with self.subTest(key=key,checkins=bool(records)):
                    ev=evidence(**{key:[application(key)]});before=deepcopy(ev)
                    reading=self.reading(records,ev)
                    self.assertIn(label,reading.summary)
                    self.assertEqual(ev,before);self.assertEqual(reading.evidence['assessments'],before)
                    self.assertEqual(reading.evidence['dimensions'],describe_checkins(records)['evidence']['dimensions'])
                    self.assertIsNone(reading.risk);self.assertIsNone(reading.trend)
                    self.assertNotIn('Ainda não há Check-ins',reading.summary)
                    self.assertEqual(reading.metadata['total_registros'],len(records))
                    if key=='cbi':
                        for name in ['Burnout Pessoal','Burnout relacionado ao trabalho','Burnout relacionado aos pacientes']:self.assertIn(name,reading.summary)
                        self.assertNotIn('faixa',reading.summary)
                    else:self.assertIn('faixa leve',reading.summary)

    def test_multiple_numeric_comparisons_and_version_incompatibility(self):
        for key,label in [('phq9','PHQ-9'),('gad7','GAD-7'),('cbi','CBI')]:
            old,new=application(key,1,'2'),application(key,2,'1')
            reading=self.reading(assessments=evidence(**{key:[old,new]}))
            self.assertIn('duas aplicações',reading.summary)
            self.assertNotIn('melhora',reading.summary);self.assertNotIn('piora',reading.summary)
            self.assertEqual(reading.metadata['summary_sources'][0]['application_ids'],[2,1])
            new.resultado['versao']='future'
            reading=self.reading(assessments=evidence(**{key:[old,new]}))
            self.assertNotIn('duas aplicações',reading.summary)

    def test_item9_previous_positive_is_not_resolved_by_later_zero(self):
        ev=evidence(phq9=[application('phq9',1,item9='1'),application('phq9',2,item9='0')])
        reading=self.reading(assessments=ev)
        self.assertIn('positiva ao item 9',reading.summary)
        self.assertIn('2026-01-01',reading.summary)
        self.assertIn('Não há informação de resolução',reading.summary)
        self.assertIsNone(reading.risk);self.assertEqual(reading.alerts,[])

    def test_professional_sources_partial_and_hypothesis_not_diagnosis(self):
        d=clinical_record(status='ATIVO',tipo='DIAGNOSTICO',data_diagnostico=date(2026,1,1))
        i=clinical_record(tipo='Psicoeducação',data_intervencao=datetime(2026,1,1,tzinfo=timezone.utc))
        for kwargs,phrase in [(dict(diagnoses=[d]),'diagnóstico ativo'),(dict(interventions=[i]),'Psicoeducação')]:
            reading=self.reading(**kwargs);self.assertIn(phrase,reading.summary)
            self.assertNotIn('Ainda não há Check-ins',reading.summary)
            self.assertEqual(reading.clinical_state['status'],'SEM_DADOS')
        for state,kind in [('CANCELADO','DIAGNOSTICO'),('REVISADO','DIAGNOSTICO'),('ATIVO','HIPOTESE'),('ATIVO','REVISAO')]:
            d.status=state;d.tipo=kind
            self.assertNotIn('diagnóstico ativo',self.reading(diagnoses=[d]).summary)

    def test_complete_journey_preserves_all_non_narrative_fields(self):
        phq=application('phq9',value='1',item9='0')
        phq.resultado=PHQ9Engine().executar(AssessmentContext(registro_id=1,instrumento='PHQ9',modulo_id=3,respostas={**dict.fromkeys([f'phq9_{i}' for i in range(1,10)],'1'),'phq9_1':'0'},metadata={'contexto_assistencial_id':2}))
        gad=application('gad7');gad.resultado=GAD7Engine().executar(AssessmentContext(registro_id=2,instrumento='GAD7',modulo_id=3,respostas={**dict.fromkeys([f'gad7_{i}' for i in range(1,8)],'1'),'gad7_1':'3','gad7_2':'2'},metadata={'contexto_assistencial_id':2}))
        ev=evidence(phq9=[phq],gad7=[gad],cbi=[application('cbi',value='2')])
        d=clinical_record(status='ATIVO',tipo='DIAGNOSTICO',data_diagnostico=date(2026,1,1))
        i=clinical_record(tipo='Psicoeducação',data_intervencao=datetime(2026,1,1,tzinfo=timezone.utc))
        reading=self.reading(checkins(),ev,[d],[i]);base=describe_checkins(checkins())
        for phrase in ['8/27','faixa leve','10/21','faixa moderada','50/100','item 9','diagnóstico ativo','Psicoeducação']:
            self.assertIn(phrase,reading.summary)
        for name in ['risk','trend','clinical_state','alerts','reference_date']:self.assertEqual(getattr(reading,name),base[name])
        for name,value in base['evidence'].items():self.assertEqual(reading.evidence[name],value)
        self.assertEqual([s['source'] for s in reading.metadata['summary_sources']],['WELLBEING_CHECKIN','PHQ9','GAD7','CBI','DIAGNOSIS','INTERVENTION'])
        self.assertLess(len(reading.summary.split()),300)

    def test_provider_rejects_foreign_professional_sources(self):
        for field in ('pessoa_id','contexto_assistencial_id','modulo_id'):
            record=clinical_record();setattr(record,field,999)
            for argument in ('diagnoses','interventions'):
                with self.assertRaises(ValueError):self.reading(**{argument:[record]})


class SummaryHTTPTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.EvidenceHTTPTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.EvidenceHTTPTests.tearDownClass.__func__)
    setUp=foundation.EvidenceHTTPTests.setUp
    tearDown=foundation.EvidenceHTTPTests.tearDown
    path=foundation.EvidenceHTTPTests.path
    command_grant=foundation.EvidenceHTTPTests.command_grant
    assessment=foundation.EvidenceHTTPTests.assessment
    def test_full_authorized_journey_and_context_isolation(self):
        for key in ('phq9','gad7','cbi'):self.assessment(key)
        url=urlsplit(self.path())
        for endpoint,payload in [('diagnosticos',dict(descricao_clinica='Synthetic diagnosis',medico_nome='Synthetic physician',data_diagnostico='2026-01-01')),('intervencoes',dict(tipo='Psicoeducação',descricao='Synthetic intervention',data_intervencao='2026-01-01T10:00:00Z'))]:
            response=self.client.request('POST',url.path+'/'+endpoint,params=dict(parse_qsl(url.query)),body=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
            self.assertEqual(response.status_code,201,response.text)
        response=self.client.get(self.path());self.assertEqual(response.status_code,200,response.text)
        reading=response.json()['clinical_reading']
        for phrase in ['PHQ-9','GAD-7','CBI','diagnóstico ativo','Psicoeducação']:self.assertIn(phrase,reading['summary'])
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed));self.db.commit()
        other=self.client.get(self.path(context=self.closed)).json()['clinical_reading']
        self.assertEqual(other['metadata']['summary_sources'],[])
        for change in (dict(person=self.person+999),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.client.get(self.path(**change)).status_code,404)
