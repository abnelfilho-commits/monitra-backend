"""Synthetic disposable PostgreSQL only; no HML data."""
import os
import unittest
from datetime import date
from sqlalchemy import text
import test_capacidade_gestao as capacity
from app.services.institucional import PROFESSIONAL_DISPLAY_SQL, InstitucionalErro
from app.schemas.institucional import ProfissionalInstituicaoListResponse

@unittest.skipUnless(os.getenv('G1_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class CapacityNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capacity.CapacityManagementTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):
        capacity.CapacityManagementTests.tearDownClass.__func__(cls)
    setUp = capacity.CapacityManagementTests.setUp
    tearDown = capacity.CapacityManagementTests.tearDown

    def outputs(self):
        listing=self.s.professional_links_with_names(self.db,instituicao_id=self.a.id,actor_id=self.actor)
        result=self.s.consolidate_capacity(self.db,instituicao_id=self.a.id,reference_date=date(2026,6,1),actor_id=self.actor)
        return listing,result

    def person(self, social):
        identity=self.db.execute(text("INSERT INTO pessoas(nome_completo,nome_social) VALUES ('Nome completo sintético',:social) RETURNING id"),{'social':social}).scalar()
        self.db.execute(text('UPDATE profissionais SET pessoa_id=:p WHERE id=:id'),{'p':identity,'id':self.pr})

    def assert_name(self, expected):
        listing,result=self.outputs()
        self.assertEqual(listing[0]['profissional_nome'],expected)
        self.assertEqual(result['vinculos'][0]['profissional_nome'],expected)
        self.assertEqual(ProfissionalInstituicaoListResponse.model_validate(listing[0]).ocupacao_nome,'Ocupação sintética')
        self.assertEqual(result['totais']['vinculos_sem_capacidade'],1)

    def test_social_priority(self):
        self.person('Nome social sintético');self.assert_name('Nome social sintético')
    def test_full_name_without_social(self):
        self.person(None);self.assert_name('Nome completo sintético')
    def test_unassociated_legacy(self):
        self.assert_name('Sintético')
    def test_empty_names_fallback_expression(self):
        # Current constraints prohibit blank names in stored Pessoa rows.
        for social,full,expected in [('  ','Completo','Completo'),('','', 'Legado'),(None,None,'Legado'),(' Social ','Completo','Social')]:
            actual=self.db.execute(text(f"SELECT {PROFESSIONAL_DISPLAY_SQL} FROM (SELECT CAST(:s AS text) AS nome_social, CAST(:f AS text) AS nome_completo) pe CROSS JOIN (SELECT 'Legado'::text AS nome) p"),{'s':social,'f':full}).scalar()
            self.assertEqual(actual,expected)
    def test_listing_keeps_historical_link_and_institution_scope(self):
        self.db.execute(text('UPDATE profissional_instituicoes SET ativo=false WHERE id=:id'),{'id':self.capacity_link.id})
        listing,result=self.outputs();self.assertEqual(len(listing),1);self.assertFalse(listing[0]['ativo']);self.assertEqual(result['vinculos'],[])
        self.assertEqual(self.s.professional_links_with_names(self.db,instituicao_id=self.b.id,actor_id=self.actor),[])
    def test_admin_required(self):
        self.db.execute(text("UPDATE usuarios SET perfil='PROFISSIONAL' WHERE id=:id"),{'id':self.actor})
        with self.assertRaises(InstitucionalErro):self.outputs()
    def test_http_list_names_only_and_authorization(self):
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.routers.vinculos_institucionais import router
        from app.database import get_db
        from app.core.deps import get_usuario_atual
        self.person('Nome social sintético')
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor,perfil='ADMIN')
        client=TestClient(app);path='/admin/vinculos-institucionais/profissionais'
        response=client.get(path,params={'instituicao_id':self.a.id})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()[0]['profissional_nome'],'Nome social sintético')
        self.assertEqual(client.get(path,params={'instituicao_id':self.b.id}).json(),[])
        detail=client.get(f'{path}/{self.capacity_link.id}')
        self.assertEqual(detail.status_code,200,detail.text)
        self.assertNotIn('profissional_nome',detail.json())
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor,perfil='GESTOR')
        self.assertEqual(client.get(path,params={'instituicao_id':self.a.id}).status_code,403)
