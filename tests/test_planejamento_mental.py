"""Contextual quantitative planning: real PostgreSQL + existing W1B fixtures."""
import os
import unittest
from datetime import date,timedelta
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text
import test_pts_mental as foundation
from app.services.planning_occurrences import planned_quantity
from app.services.scheduling_engine import SchedulingEngine
from app.services.scheduling_models import PlanejamentoAssistencial


class QuantityTests(unittest.TestCase):
    def test_short_long_and_same_day_match_canonical_schedule(self):
        for start,end in [(date(2026,11,1),date(2027,4,30)),(date(2026,1,1),date(2026,1,1)),(date(2026,1,1),date(2026,1,3)),(date(2026,1,1),date(2029,12,31))]:
            for f in (1,2,3,7,10):
                q=planned_quantity(start,end,f,50)['quantidade_sessoes']
                dates=SchedulingEngine.generate_sessions(PlanejamentoAssistencial(start,q+1,f,50))
                self.assertGreater(q,0);self.assertLessEqual(dates[q-1].data_agendada,end);self.assertGreater(dates[q].data_agendada,end)
    def test_override_and_invalid_period(self):
        start=date(2026,11,1);end=date(2027,4,30)
        self.assertEqual(planned_quantity(start,end,2,50)['quantidade_sessoes'],52)
        self.assertEqual(planned_quantity(start,end,2,50,4)['quantidade_sessoes'],4)
        for args in [(end,start,2,50,None),(start,end,0,50,None),(start,end,2,50,0),(start,end,2,50,53)]:
            with self.assertRaises(ValueError):planned_quantity(*args)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'),'Disposable PostgreSQL required')
class PlanningTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(foundation.PTSMentalTests.setUpClass.__func__)
    tearDownClass=classmethod(foundation.PTSMentalTests.tearDownClass.__func__)
    tearDown=foundation.PTSMentalTests.tearDown
    command_grant=foundation.PTSMentalTests.command_grant
    path=foundation.PTSMentalTests.path
    request=foundation.PTSMentalTests.request
    create=foundation.PTSMentalTests.create

    def setUp(self):
        foundation.PTSMentalTests.setUp(self)
        self.db.execute(text("INSERT INTO modulos_clinicos(id,nome,slug,ativo) VALUES (1,'Synthetic Neuro','synthetic_neuro',true) ON CONFLICT(id) DO NOTHING"));self.db.commit()
        plan=self.create();self.plan=plan['id']
        self.objective=self.request('POST',f"/{self.plan}/objetivos",dict(descricao='Synthetic goal')).json()['objetivos'][0]['id']
        self.suffix=f'/{self.plan}/objetivos/{self.objective}/planejamentos'
        self.executor,self.occupation=self.db.execute(text('SELECT profissional_id,ocupacao_id FROM profissional_instituicoes WHERE id=:id'),dict(id=self.links[0])).one()
        self.activity=self.db.execute(text("INSERT INTO atividades_terapeuticas(nome,modulo_id,ativo) VALUES ('Synthetic psychotherapy',3,true) RETURNING id")).scalar_one()
        self.db.execute(text('INSERT INTO atividade_ocupacao(atividade_id,ocupacao_id) VALUES (:a,:o)'),dict(a=self.activity,o=self.occupation));self.db.commit()
        start=date.today()+timedelta(days=1)
        self.payload=dict(atividade_id=self.activity,ocupacao_id=self.occupation,profissional_id=self.executor,frequencia_semanal=2,duracao_minutos=50,data_inicio=str(start),data_fim=str(start+timedelta(days=30)))

    def test_create_read_edit_and_no_sessions_or_legacy_leak(self):
        before=self.client.get(self.path()).json()['clinical_reading']
        r=self.request('POST',self.suffix,self.payload);self.assertEqual(r.status_code,201,r.text)
        saved=r.json();self.assertEqual(saved['quantidade_sessoes'],9);self.assertEqual(saved['status'],'PLANEJADO')
        with patch.object(self.db,'commit',side_effect=AssertionError('read commit')):
            self.assertEqual(self.request('GET',self.suffix).json()[0]['id'],saved['id'])
        r=self.request('PUT',self.suffix+f"/{saved['id']}",dict(self.payload,quantidade_sessoes=4,observacoes='Updated'))
        self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['quantidade_sessoes'],4)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM sessoes_assistenciais')),0)
        self.assertEqual(self.client.get(self.path()).json()['clinical_reading'],before)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM vw_dimensionamento_ocupacao')),0)
        from app.services.care_plan_service import CarePlanService
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):CarePlanService().list_agendas(self.db,self.objective,SimpleNamespace(perfil='ADMIN'))

    def test_eligibility_and_catalog(self):
        r=self.request('GET','/catalogo-planejamento');self.assertEqual(r.status_code,200,r.text)
        self.assertIn(self.activity,[a['id'] for a in r.json()['atividades']])
        for sql in ["UPDATE profissional_instituicoes SET ativo=false WHERE id=:id", "UPDATE profissional_instituicoes SET data_fim=CURRENT_DATE WHERE id=:id"]:
            self.db.execute(text(sql),dict(id=self.links[0]))
            self.assertIn(self.request('POST',self.suffix,self.payload).status_code,(403,422))
            self.db.rollback()
        for values in [dict(ocupacao_id=999999),dict(profissional_id=999999),dict(atividade_id=999999)]:
            self.assertEqual(self.request('POST',self.suffix,dict(self.payload,**values)).status_code,422)
        self.db.execute(text('UPDATE atividades_terapeuticas SET modulo_id=1 WHERE id=:id'),dict(id=self.activity))
        self.assertEqual(self.request('POST',self.suffix,self.payload).status_code,422)

    def test_other_institution_executor_and_active_role(self):
        person=self.db.scalar(text("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic foreign executor') RETURNING id"))
        professional=self.db.scalar(text("INSERT INTO profissionais(nome,pessoa_id,ativo) VALUES ('Synthetic foreign executor',:p,true) RETURNING id"),dict(p=person))
        self.db.execute(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2020-01-01')"),dict(p=professional,i=self.institutions[1],o=self.occupation));self.db.commit()
        self.assertEqual(self.request('POST',self.suffix,dict(self.payload,profissional_id=professional)).status_code,422)
        self.assertNotIn(professional,[p['profissional_id'] for p in self.request('GET','/catalogo-planejamento').json()['executores']])

    def test_catalog_maintenance_profiles_and_mental_activity(self):
        from app.routers.atividades_terapeuticas import router
        from app.core.deps import get_usuario_atual
        self.app.include_router(router)
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(perfil='ADMIN')
        import json
        response=self.client.request('POST','/atividades-terapeuticas/',body=json.dumps(dict(nome='Synthetic new mental activity',modulo_id=3,duracao_minutos=50)).encode(),headers={'Content-Type':'application/json'})
        self.assertEqual(response.status_code,200,response.text)
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(perfil='PROFISSIONAL')
        response=self.client.get('/atividades-terapeuticas/',params={'modulo_id':3})
        self.assertEqual(response.status_code,200,response.text)
        self.assertIn('Synthetic new mental activity',[a['nome'] for a in response.json()])
        from app.routers.atividades_terapeuticas import maintain_catalog
        for role in ('ADMIN','ADMINISTRADOR','ADMIN_CLINICA','SUPORTE'):
            self.assertEqual(maintain_catalog(SimpleNamespace(perfil=role)).perfil,role)

    def test_scope_ancestry_and_other_objective(self):
        saved=self.request('POST',self.suffix,self.payload).json()
        for scope in (dict(person=self.person+999),dict(context=self.contexts[1]),dict(institution=self.institutions[1])):
            self.assertEqual(self.request('GET',self.suffix,**scope).status_code,404)
            self.assertEqual(self.request('PUT',self.suffix+f"/{saved['id']}",self.payload,**scope).status_code,403)
        other=self.request('POST',f'/{self.plan}/objetivos',dict(descricao='Other goal')).json()['objetivos'][-1]['id']
        self.assertEqual(self.request('PUT',f"/{self.plan}/objetivos/{other}/planejamentos/{saved['id']}",self.payload).status_code,403)
        self.assertEqual(self.request('POST',f'/999999/objetivos/{self.objective}/planejamentos',self.payload).status_code,403)
        self.db.execute(text('UPDATE pts SET modulo_id=1,contexto_assistencial_id=NULL WHERE id=:id'),dict(id=self.plan));self.db.commit()
        self.assertEqual(self.request('GET',self.suffix).status_code,404)

    def test_authorization_and_admin_no_bypass(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),dict(id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']));self.db.commit()
        self.assertEqual(self.request('GET',self.suffix).status_code,200)
        self.assertEqual(self.request('POST',self.suffix,self.payload).status_code,403)
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:id"),dict(id=self.actor));self.db.commit()
        self.assertEqual(self.request('POST',self.suffix,self.payload).status_code,403)
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),dict(id=self.grant_ids[self.open,'ASSISTENCIAL_LER']));self.db.commit()
        self.assertEqual(self.request('GET',self.suffix).status_code,404)

    def test_invalid_quantity_and_rollback(self):
        for changes in [dict(quantidade_sessoes=9999),dict(quantidade_sessoes=0),dict(data_fim='2000-01-01'),dict(frequencia_semanal=0)]:
            r=self.request('POST',self.suffix,dict(self.payload,**changes));self.assertEqual(r.status_code,422,r.text)
        with patch('app.services.planejamento_mental.PlanningService.outputs',side_effect=RuntimeError('Synthetic serialization error')):
            self.assertEqual(self.request('POST',self.suffix,self.payload).status_code,500)
        self.assertEqual(self.request('GET',self.suffix).json(),[])
        self.assertEqual(self.request('POST',self.suffix,dict(self.payload,clinica_id=1)).status_code,422)


class CatalogSecurityTests(unittest.TestCase):
    def test_all_catalog_endpoints_require_auth_and_maintenance_role(self):
        from fastapi import FastAPI
        from app.routers.atividades_terapeuticas import router
        from app.core.deps import get_usuario_atual
        from app.database import get_db
        from test_whatsapp_security import LocalClient
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:None
        client=LocalClient(app)
        routes=[('GET','/'),('POST','/'),('GET','/ocupacoes-profissionais'),('POST','/ocupacoes-profissionais'),('GET','/1/ocupacoes'),('POST','/1/ocupacoes'),('DELETE','/1/ocupacoes/1')]
        for method,path in routes:self.assertEqual(client.request(method,'/atividades-terapeuticas'+path).status_code,401)
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(perfil='PROFISSIONAL')
        for method,path in routes:
            if method!='GET':self.assertEqual(client.request(method,'/atividades-terapeuticas'+path).status_code,403)
