"""Additive, lossless assessment evidence at the authorized journey boundary."""
import json
import os
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import urlsplit, parse_qsl
from unittest.mock import patch
from sqlalchemy import text
import test_checkin_bem_estar as foundation
from app.services.cbi_contract import FIELDS
from app.services.clinical_reading.providers.assessment_evidence import assessment_evidence


class EvidenceTests(unittest.TestCase):
    def test_empty_and_deterministic_lossless_history(self):
        args=dict(pessoa_id=1,contexto_assistencial_id=2,instituicao_id=3)
        empty=assessment_evidence(**args,applications={})
        self.assertEqual(set(empty),{'phq9','gad7','cbi'})
        self.assertTrue(all(v==dict(applications=[],latest=None) for v in empty.values()))
        result=dict(instrumento='PHQ9',score=3,metadata=dict(contexto_assistencial_id=2,respostas={'phq9_9':'3'}),alertas=['canonical'])
        def row(i):return SimpleNamespace(id=i,registro_id=i+10,data_hora=datetime(2026,1,1,tzinfo=timezone.utc),registrador_usuario_id=4,registrador_profissional_id=5,resultado=result)
        evidence=assessment_evidence(**args,applications={'phq9':[row(1),row(2)]})['phq9']
        self.assertEqual([x['application_id'] for x in evidence['applications']],[2,1])
        self.assertEqual(evidence['latest']['result'],result)
        result['alertas'].clear()
        self.assertEqual(evidence['latest']['result']['alertas'],['canonical'])
        evidence['applications'][0]['result']['alertas'].clear()
        self.assertEqual(evidence['latest']['result']['alertas'],['canonical'])
        for change in ({'instrumento':'GAD7'},{'metadata':{'contexto_assistencial_id':99}}):
            invalid=row(3);invalid.resultado={**result,**change}
            with self.assertRaises(ValueError):assessment_evidence(**args,applications={'phq9':[invalid]})


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL required')
class EvidenceHTTPTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.CheckinTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.CheckinTests.tearDownClass.__func__)
    setUp=foundation.CheckinTests.setUp
    tearDown=foundation.CheckinTests.tearDown
    command_grant=foundation.CheckinTests.command_grant
    path=foundation.CheckinTests.path
    payload=foundation.CheckinTests.payload
    post=foundation.CheckinTests.post

    def assessment(self,instrument):
        fields=[x[0] for x in FIELDS] if instrument=='cbi' else [f'{instrument}_{i}' for i in range(1,10 if instrument=='phq9' else 8)]
        u=urlsplit(self.path())
        response=self.client.request('POST',u.path+'/'+instrument,params=dict(parse_qsl(u.query)),body=json.dumps({'respostas':dict.fromkeys(fields,'1')}).encode(),headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,201,response.text)
        return response.json()

    def test_persisted_results_provenance_and_checkin_reading_unchanged(self):
        for count in range(3):
            with self.subTest(checkins=count):
                if count:self.assertEqual(self.post().status_code,201)
                before=self.client.get(self.path()).json()
                created={key:self.assessment(key) for key in ('phq9','gad7','cbi')}
                with patch.object(self.db,'commit',side_effect=AssertionError('GET commit')), patch.object(self.db,'flush',side_effect=AssertionError('GET flush')):
                    response=self.client.get(self.path())
                self.assertEqual(response.status_code,200,response.text)
                after=response.json()
                self.assertEqual(before['bem_estar'],after['bem_estar'])
                old,new=deepcopy(before['clinical_reading']),deepcopy(after['clinical_reading'])
                old['evidence'].pop('assessments');evidence=new['evidence'].pop('assessments')
                self.assertEqual(old,new)
                for key,item in created.items():
                    latest=evidence[key]['latest']
                    self.assertEqual(len(evidence[key]['applications']),count+1)
                    self.assertEqual(latest['result'],item['resultado'])
                    self.assertEqual(latest['application_id'],item['id'])
                    self.assertEqual(latest['record_id'],item['registro_id'])
                    self.assertEqual(latest['author']['usuario_id'],self.actor)
                    self.assertEqual(latest['contexto_assistencial_id'],self.open)
                    self.assertEqual(latest['pessoa_id'],self.person)
                    self.assertEqual(latest['instituicao_id'],self.institution)
                self.assertEqual(evidence['phq9']['latest']['score_max'],27)
                self.assertEqual(evidence['gad7']['latest']['score_max'],21)
                self.assertEqual(len(evidence['cbi']['latest']['result']['dominios']),3)
                self.assertNotIn('score',evidence['cbi']['latest']['result'])
                self.assertNotIn('score_max',evidence['cbi']['latest'])

    def test_scope_and_read_authorization_remain_mandatory(self):
        self.assessment('phq9')
        for scope in (dict(person=self.person+100000),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.client.get(self.path(**scope)).status_code,404)
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:u"),dict(u=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:g'),dict(g=self.grant_ids[self.open,'ASSISTENCIAL_LER']))
        self.db.commit()
        self.assertEqual(self.client.get(self.path()).status_code,404)

    def isolated_instrument(self,key):
        before=self.client.get(self.path()).json()['clinical_reading']
        self.assertTrue(all(not v['applications'] and v['latest'] is None for v in before['evidence']['assessments'].values()))
        created=self.assessment(key)
        with patch('app.services.phq9.executar_avaliacao_clinica',side_effect=AssertionError('recalculation')), patch('app.services.gad7.executar_avaliacao_clinica',side_effect=AssertionError('recalculation')), patch('app.services.cbi.executar_avaliacao_clinica',side_effect=AssertionError('recalculation')):
            after=self.client.get(self.path()).json()['clinical_reading']
        evidence=after['evidence'].pop('assessments');before['evidence'].pop('assessments')
        self.assertEqual(before,after)
        self.assertEqual(evidence[key]['latest']['result'],created['resultado'])
        self.assertTrue(all(not value['applications'] for name,value in evidence.items() if name!=key))
        if key=='phq9':
            self.assertEqual(evidence[key]['latest']['result']['metadata']['respostas']['phq9_9'],'1')
            self.assertTrue(evidence[key]['latest']['result']['alertas'])

    def test_only_phq9(self):self.isolated_instrument('phq9')
    def test_only_gad7(self):self.isolated_instrument('gad7')
    def test_only_cbi(self):self.isolated_instrument('cbi')

    def test_other_context_and_foreign_respondent_never_enter_evidence(self):
        item=self.assessment('phq9')
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=self.closed))
        self.db.commit()
        other=self.client.get(self.path(context=self.closed))
        self.assertEqual(other.status_code,200,other.text)
        self.assertEqual(other.json()['clinical_reading']['evidence']['assessments']['phq9']['applications'],[])
        person=self.db.execute(text("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic foreign respondent') RETURNING id")).scalar_one()
        self.db.execute(text('UPDATE registro_proveniencias SET respondente_pessoa_id=:p WHERE registro_id=:r'),dict(p=person,r=item['registro_id']))
        self.db.commit()
        response=self.client.get(self.path())
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['clinical_reading']['evidence']['assessments']['phq9']['applications'],[])

    def test_inactive_line_does_not_expose_reading(self):
        self.assessment('cbi')
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c'),dict(c=self.open))
        self.db.commit()
        self.assertIsNone(self.client.get(self.path()).json()['clinical_reading'])
