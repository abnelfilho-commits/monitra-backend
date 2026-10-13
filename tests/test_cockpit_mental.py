"""Actual PostgreSQL, HTTP, contextual authorization and batch query regression."""
import os
import json
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from types import SimpleNamespace
from sqlalchemy import text, event
import test_planejamento_mental as planning
import test_checkin_bem_estar as checkin
import test_assessment_evidence as assessments
from app.core.deps import get_usuario_atual
from app.services.cockpit_mental import CockpitMentalService, TZ


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL 18 required')
class CockpitTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(planning.PlanningTests.setUpClass.__func__)
    tearDownClass=classmethod(planning.PlanningTests.tearDownClass.__func__)
    tearDown=planning.PlanningTests.tearDown
    command_grant=planning.PlanningTests.command_grant
    path=planning.PlanningTests.path
    request=planning.PlanningTests.request
    create=planning.PlanningTests.create
    assessment=assessments.EvidenceHTTPTests.assessment

    def setUp(self):
        planning.PlanningTests.setUp(self)
        r=self.request('POST',self.suffix,self.payload)
        self.assertEqual(r.status_code,201,r.text)
        self.agenda=r.json()['id']
        self.patient=self.db.scalar(text('SELECT paciente_id FROM pts WHERE id=:i'),dict(i=self.plan))
        self.day=datetime.now(TZ).date()
        self.number=0

    def cockpit(self, **params):
        r=self.client.get('/saude-mental/cockpit/profissional',params=params)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def session(self, offset=0, status='AGENDADA', realized=None, agenda=None):
        self.number+=1
        i=self.db.scalar(text("INSERT INTO sessoes_assistenciais(agenda_cuidado_id,paciente_id,profissional_id,numero_sessao,data_agendada,hora_inicio,hora_fim,duracao_minutos,status,data_realizacao) VALUES (:a,:p,:u,:n,:d,'09:00','09:50',50,:s,:r) RETURNING id"),dict(a=agenda or self.agenda,p=self.patient,u=self.executor,n=self.number,d=self.day+timedelta(days=offset),s=status,r=realized))
        self.db.commit();return i

    def wellbeing(self, help='SIM', hour=None, mood='BOM'):
        payload=checkin.CheckinTests.payload(self)
        payload['respostas'].update(pedido_ajuda=help,humor=mood,evento_relevante='SIM',evento_descricao='PRIVATE_NARRATIVE')
        response=self.client.request('POST',f'/saude-mental/pessoas/{self.person}/contextos/{self.open}/check-ins',params={'instituicao_id':self.institution},body=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,201,response.text)
        identity=response.json()['id']
        if hour:
            self.db.execute(text('UPDATE registros_longitudinais SET criado_em=:h WHERE id=:i'),dict(i=identity,h=hour));self.db.commit()
        return identity

    def second_institution(self):
        c=self.contexts[1];i=self.institutions[1]
        self.db.execute(text('UPDATE contextos_assistenciais SET data_inicio=\'2021-01-01\',data_fim=NULL WHERE id=:c'),dict(c=c))
        self.db.execute(text('UPDATE usuario_instituicao_acessos SET ativo=true WHERE id=:r'),dict(r=self.roots[1]))
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id,ativo) VALUES (:c,3,true)'),dict(c=c))
        self.db.execute(text("INSERT INTO contexto_profissionais(instituicao_id,contexto_assistencial_id,profissional_instituicao_id,data_inicio,criado_por_usuario_id,motivo_criacao) VALUES (:i,:c,:l,CURRENT_DATE,:u,'Synthetic')"),dict(i=i,c=c,l=self.links[1],u=self.actor))
        self.db.execute(text("INSERT INTO concessoes_assistenciais(usuario_instituicao_acesso_id,instituicao_id,capacidade,escopo_tipo,contexto_assistencial_id,concedido_por_usuario_id,motivo_concessao) VALUES (:r,:i,'ASSISTENCIAL_LER','CONTEXTO',:c,:u,'Synthetic')"),dict(r=self.roots[1],i=i,c=c,u=self.actor))
        self.db.commit();return c

    def test_counts_date_of_realization_limits_and_personal_agenda(self):
        today=self.session();self.session();self.session(2);self.session(3)
        done=self.session(-3,'REALIZADA',self.day)
        self.session(2,'REALIZADA',self.day+timedelta(days=2))
        r=self.cockpit(limit=1)
        self.assertEqual(r['resumo'],dict(pessoas_em_acompanhamento=1,atendimentos_hoje=2,realizados_hoje=1,proximos_atendimentos=2))
        self.assertEqual(r['agenda_hoje'][0]['sessao_id'],today)
        self.assertTrue(r['metadados']['tem_mais']['agenda_hoje'])
        self.assertEqual(r['resumo'],self.cockpit(limit=100)['resumo'])
        self.assertIn(done,[e['referencia_id'] for e in self.cockpit()['atividade_recente'] if e['tipo']=='SESSAO'])

    def test_multi_institution_distinct_person_restrictive_filter(self):
        other=self.second_institution()
        self.assertEqual(self.cockpit()['resumo']['pessoas_em_acompanhamento'],1)
        self.assertEqual(self.cockpit(instituicao_id=self.institutions[1])['resumo']['pessoas_em_acompanhamento'],1)
        self.assertEqual(self.cockpit(instituicao_id=2147483647)['resumo']['pessoas_em_acompanhamento'],0)
        self.wellbeing()
        self.assertEqual(self.cockpit(instituicao_id=self.institutions[1])['pessoas_para_acompanhamento'],[])
        self.db.execute(text('UPDATE contextos_assistenciais SET ativo=false WHERE id=:c'),dict(c=other));self.db.commit()
        self.assertEqual(self.cockpit(instituicao_id=self.institutions[1])['resumo']['pessoas_em_acompanhamento'],0)

    def test_reasons_group_contexts_without_arbitrary_selection(self):
        other=self.second_institution()
        first=self.wellbeing()
        second=self.wellbeing()
        self.db.execute(text('UPDATE registros_longitudinais SET contexto_assistencial_id=:c WHERE id=:i'),dict(c=other,i=second));self.db.commit()
        people=self.cockpit()['pessoas_para_acompanhamento']
        self.assertEqual(len(people),1)
        reasons=people[0]['motivos']
        self.assertEqual({m['contexto_assistencial_id'] for m in reasons},{self.open,other})
        self.assertEqual({m['instituicao_id'] for m in reasons},set(self.institutions[:2]))
        self.assertEqual([m['referencia_id'] for m in reasons],[second,first])

    def test_revoked_grant_participation_and_inactive_context(self):
        self.session();self.wellbeing()
        for sql in ['DELETE FROM concessoes_assistenciais WHERE contexto_assistencial_id=:c',
                    'DELETE FROM contexto_profissionais WHERE contexto_assistencial_id=:c',
                    'UPDATE contextos_assistenciais SET ativo=false WHERE id=:c',
                    'UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c']:
            tx=self.db.begin_nested();self.db.execute(text(sql),dict(c=self.open))
            r=self.cockpit();self.assertEqual(r['resumo']['pessoas_em_acompanhamento'],0)
            self.assertEqual(r['agenda_hoje'],[]);self.assertEqual(r['pessoas_para_acompanhamento'],[])
            self.assertEqual(r['atividade_recente'],[]);tx.rollback()

    def test_legacy_sessions_excluded(self):
        self.session()
        self.db.execute(text('UPDATE pts SET modulo_id=1,contexto_assistencial_id=NULL WHERE id=:i'),dict(i=self.plan));self.db.commit()
        r=self.cockpit()
        self.assertEqual(r['resumo']['atendimentos_hoje'],0)
        self.assertEqual(r['agenda_hoje'],[])

    def test_no_admin_bypass_and_authentication(self):
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.platform_admin)
        r=self.cockpit();self.assertEqual(r['resumo']['pessoas_em_acompanhamento'],0)
        self.assertEqual(r['atividade_recente'],[])
        del self.app.dependency_overrides[get_usuario_atual]
        self.assertEqual(self.client.get('/saude-mental/cockpit/profissional').status_code,401)

    def test_reasons_metadata_only_and_no_parallel_clinical_classification(self):
        self.wellbeing(mood='BOM');self.wellbeing(mood='RUIM')
        self.session(-60)
        a=self.assessment('phq9') # persisted positive item 9 => official alert
        self.assessment('gad7');self.assessment('cbi')
        r=self.cockpit();self.assertEqual(len(r['pessoas_para_acompanhamento']),1)
        reasons=r['pessoas_para_acompanhamento'][0]['motivos']
        self.assertTrue({'APOIO_AUTORREFERIDO','MUDANCA_OBSERVACIONAL','SESSAO_SEM_DESFECHO','INSTRUMENTO_REVISAO'} <= {m['codigo'] for m in reasons})
        instrument=[m for m in reasons if m['codigo']=='INSTRUMENTO_REVISAO']
        self.assertEqual([(m['fonte'],m['referencia_id']) for m in instrument],[('PHQ9',a['id'])])
        self.assertTrue(all(m['contexto_assistencial_id']==self.open and m['instituicao_id']==self.institution for m in reasons))
        rendered=json.dumps(r)
        for forbidden in ('PRIVATE_NARRATIVE','respostas','classificacao','score','diagnostico_automatico'):
            self.assertNotIn(forbidden,rendered)

    def test_cuiaba_window_midnight_and_old_help_not_assumed_pending(self):
        before=datetime.combine(self.day,datetime.min.time()).replace(hour=3,minute=59)
        identity=self.wellbeing(hour=before)
        with patch('app.services.cockpit_mental.now_local',return_value=datetime.combine(self.day,datetime.min.time(),TZ)):
            self.assertEqual(self.cockpit()['metadados']['data_referencia'],str(self.day))
        self.db.execute(text('UPDATE registros_longitudinais SET criado_em=:d WHERE id=:i'),dict(d=before-timedelta(days=30),i=identity));self.db.commit()
        self.assertEqual(self.cockpit()['pessoas_para_acompanhamento'],[])
        self.assertEqual(self.cockpit()['atividade_recente'],[])
        boundary=datetime.combine(self.day-timedelta(days=29),datetime.min.time()).replace(hour=4)
        self.db.execute(text('UPDATE registros_longitudinais SET criado_em=:d WHERE id=:i'),dict(d=boundary-timedelta(seconds=1),i=identity));self.db.commit()
        self.assertEqual(self.cockpit()['atividade_recente'],[])
        self.db.execute(text('UPDATE registros_longitudinais SET criado_em=:d WHERE id=:i'),dict(d=boundary,i=identity));self.db.commit()
        self.assertEqual(self.cockpit()['atividade_recente'][0]['referencia_id'],identity)

    def test_event_ties_stable_and_validators(self):
        stamp=datetime.combine(self.day,datetime.min.time()).replace(hour=12)
        a=self.wellbeing(hour=stamp);b=self.wellbeing(hour=stamp)
        r=self.cockpit(limit=1)
        self.assertEqual(r['atividade_recente'][0]['referencia_id'],max(a,b))
        self.assertTrue(r['metadados']['tem_mais']['atividade_recente'])
        self.assertEqual(r,self.cockpit(limit=1))
        for params in ({'limit':0},{'limit':101},{'data_referencia':'invalid'},{'instituicao_id':0}):
            self.assertEqual(self.client.get('/saude-mental/cockpit/profissional',params=params).status_code,422)

    def test_read_only_query_budget_independent_of_session_count(self):
        def count():
            statements=[]
            def capture(c,cu,s,*args):statements.append(s)
            event.listen(self.engine,'before_cursor_execute',capture)
            try:
                with patch.object(self.db,'commit',side_effect=AssertionError('commit')),patch.object(self.db,'flush',side_effect=AssertionError('flush')):
                    self.cockpit()
            finally:event.remove(self.engine,'before_cursor_execute',capture)
            self.assertTrue(all(s.lstrip().startswith(('SELECT','WITH')) for s in statements))
            return len(statements)
        initial=count()
        for _ in range(20):self.session()
        self.assertEqual(count(),initial)
        self.assertLessEqual(initial,15)

    def test_no_write_capability_keeps_reading_not_action(self):
        self.session()
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:i'),dict(i=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']));self.db.commit()
        self.assertFalse(self.cockpit()['agenda_hoje'][0]['pode_registrar'])
