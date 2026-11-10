"""C1.3-A, synthetic PostgreSQL fixture only. Reuses C1.2's guarded setup."""
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from sqlalchemy import text, event
from fastapi import FastAPI
from fastapi.testclient import TestClient
import test_capacidade_gestao as capacity
from app.models.institucional import ProfissionalInstituicao
from app.services.institucional import InstitucionalErro
from app.routers.vinculos_institucionais import router
from app.database import get_db
from app.core.deps import get_usuario_atual


@unittest.skipUnless(os.getenv('G1_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ConsolidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        capacity.CapacityManagementTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        capacity.CapacityManagementTests.tearDownClass.__func__(cls)

    setUp = capacity.CapacityManagementTests.setUp
    tearDown = capacity.CapacityManagementTests.tearDown
    create_capacity = capacity.CapacityManagementTests.create_capacity

    def read(self, **changes):
        args=dict(instituicao_id=self.a.id, reference_date=date(2026,6,1), actor_id=self.actor)
        args.update(changes)
        return self.s.consolidate_capacity(self.db, **args)

    def add_link(self, occupation, professional=None, institution=None):
        return self.s.create(self.db, ProfissionalInstituicao, dict(
            profissional_id=professional or self.pr, instituicao_id=institution or self.a.id,
            ocupacao_id=occupation, data_inicio=date(2026,1,1), data_fim=date(2026,12,31)),
            actor_id=self.actor, motivo='Synthetic')

    def allocate(self, link, minutes):
        return self.s.manage_capacity(self.db, instituicao_id=link.instituicao_id,vinculo_id=link.id,
            actor_id=self.actor,motivo='Synthetic',operation='CREATE_CAPACITY',reference_date=date(2026,6,1),
            payload=dict(minutos_semanais=minutes,data_inicio=date(2026,1,1),data_fim=date(2026,12,31)))

    def test_empty_and_missing_are_distinct(self):
        missing=self.read()
        self.assertEqual(missing['totais']['vinculos_sem_capacidade'],1)
        self.assertFalse(missing['totais']['informacao_completa'])
        self.assertIsNone(missing['vinculos'][0]['minutos_semanais'])
        empty=self.read(instituicao_id=self.b.id)
        self.assertEqual(empty['vinculos'],[])
        self.assertEqual(empty['ocupacoes'],[])
        self.assertEqual(empty['totais']['horas_semanais'],'0.00')
        self.assertTrue(empty['totais']['informacao_completa'])

    def test_aggregation_distinct_people_and_round_after_sum(self):
        self.create_capacity(minutos_semanais=1)
        other=self.db.execute(text("INSERT INTO ocupacoes_profissionais(nome,ativo) VALUES ('Synthetic other',false) RETURNING id")).scalar()
        self.allocate(self.add_link(other),1)
        professional=self.db.execute(text("INSERT INTO profissionais(nome,ativo) VALUES ('Synthetic',true) RETURNING id")).scalar()
        self.allocate(self.add_link(self.oc,professional),1)
        professional2=self.db.execute(text("INSERT INTO profissionais(nome,ativo) VALUES ('Synthetic missing',true) RETURNING id")).scalar()
        self.add_link(self.oc,professional2)
        result=self.read();t=result['totais']
        self.assertEqual((t['minutos_semanais'],t['horas_semanais']),(3,'0.05'))
        self.assertEqual((t['profissionais_distintos'],t['vinculos_com_capacidade'],t['vinculos_sem_capacidade']),(3,3,1))
        self.assertEqual(len(result['vinculos']),4)
        self.assertEqual(sum(x['profissionais_distintos'] for x in result['ocupacoes']),4)
        filtered=self.read(ocupacao_id=other)
        self.assertFalse(filtered['ocupacoes'][0]['ocupacao_ativa'])
        self.assertEqual(filtered['totais']['minutos_semanais'],1)
        self.assertEqual(filtered['totais']['profissionais_distintos'],1)
        self.assertEqual(self.read(ocupacao_id=999999)['vinculos'],[])

    def test_boundaries_history_and_invalidation(self):
        row=self.create_capacity(data_inicio=date(2026,3,1),data_fim=date(2026,6,1))
        for ref,informed,links in ((date(2025,12,31),0,0),(date(2026,1,1),0,1),
            (date(2026,3,1),1,1),(date(2026,6,1),1,1),(date(2026,6,2),0,1),(date(2027,1,1),0,0)):
            with self.subTest(ref=ref):
                result=self.read(reference_date=ref)
                self.assertEqual(result['totais']['vinculos_com_capacidade'],informed)
                self.assertEqual(len(result['vinculos']),links)
        self.s.manage_capacity(self.db,**self.ids,motivo='Synthetic',identity=row['id'],operation='INVALIDATE_CAPACITY')
        self.assertEqual(self.read()['totais']['vinculos_sem_capacidade'],1)

    def test_open_end_and_parent_inactive(self):
        self.db.execute(text('UPDATE profissional_instituicoes SET data_fim=NULL WHERE id=:id'),{'id':self.capacity_link.id})
        self.create_capacity(data_fim=None)
        self.assertEqual(self.read(reference_date=date(2030,1,1))['totais']['vinculos_com_capacidade'],1)
        for table,identity in (('profissionais',self.pr),('profissional_instituicoes',self.capacity_link.id)):
            self.db.execute(text(f'UPDATE {table} SET ativo=false WHERE id=:id'),{'id':identity})
            self.assertEqual(self.read()['vinculos'],[])
            self.db.execute(text(f'UPDATE {table} SET ativo=true WHERE id=:id'),{'id':identity})
        self.db.execute(text('UPDATE instituicoes SET ativo=false WHERE id=:id'),{'id':self.a.id})
        with self.assertRaises(InstitucionalErro) as exc:self.read()
        self.assertEqual(exc.exception.code,'CAPACITY_INSTITUTION_INACTIVE')

    def test_institution_isolation(self):
        self.create_capacity()
        self.allocate(self.add_link(self.oc,institution=self.b.id),600)
        self.assertEqual(self.read()['totais']['minutos_semanais'],120)
        self.assertEqual(self.read(instituicao_id=self.b.id)['totais']['minutos_semanais'],600)
        with self.assertRaises(InstitucionalErro) as exc:self.read(instituicao_id=999999)
        self.assertEqual(exc.exception.code,'CAPACITY_INSTITUTION_NOT_FOUND')

    def test_authorization_before_disclosure(self):
        for profile in ('GESTOR','PROFISSIONAL'):
            self.db.execute(text('UPDATE usuarios SET perfil=:p WHERE id=:id'),{'p':profile,'id':self.actor})
            with self.assertRaises(InstitucionalErro) as exc:self.read(instituicao_id=999999)
            self.assertEqual(exc.exception.code,'ADMIN_REQUIRED')
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN',ativo=false WHERE id=:id"),{'id':self.actor})
        with self.assertRaises(InstitucionalErro) as exc:self.read()
        self.assertEqual(exc.exception.code,'ADMIN_REQUIRED')

    def test_one_data_selection_no_write(self):
        self.create_capacity();statements=[]
        def capture(conn,cursor,statement,parameters,context,executemany):statements.append(statement)
        event.listen(self.conn,'before_cursor_execute',capture)
        try:self.read()
        finally:event.remove(self.conn,'before_cursor_execute',capture)
        self.assertEqual(len(statements),2)  # persisted ADMIN check + one data snapshot
        self.assertTrue(all(s.lstrip().upper().startswith(('SELECT','WITH')) for s in statements))
        self.assertEqual(sum('WITH eligible' in s for s in statements),1)
        self.assertFalse(self.db.new or self.db.dirty or self.db.deleted)

    def test_integrity_conflict_not_arbitrary_sum(self):
        self.create_capacity()
        row=dict(self.read()['vinculos'][0],instituicao_ativa=True)
        response=MagicMock(); response.mappings.return_value.all.return_value=[row,row]
        with patch.object(self.db,'execute',return_value=response):
            with self.assertRaises(InstitucionalErro) as exc:self.read()
        self.assertEqual(exc.exception.code,'CAPACITY_INTEGRITY_CONFLICT')
        for change in ({'ocupacao_nome':None},{'minutos_semanais':0}):
            response.mappings.return_value.all.return_value=[row|change]
            with patch.object(self.db,'execute',return_value=response):
                with self.assertRaises(InstitucionalErro):self.read()

    def test_http_filters_admin_and_empty(self):
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor,perfil='ADMIN')
        client=TestClient(app);path='/admin/vinculos-institucionais/capacidades/consolidacao'
        params={'instituicao_id':self.b.id,'data_referencia':'2026-06-01'}
        result=client.get(path,params=params)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['vinculos'],[])
        for values in ({'instituicao_id':self.b.id},{'data_referencia':'2026-06-01'},params|{'ocupacao_id':0},params|{'data_referencia':'bad'}):
            self.assertEqual(client.get(path,params=values).status_code,422)
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor,perfil='GESTOR')
        self.assertEqual(client.get(path,params=params).status_code,403)
        app.dependency_overrides.pop(get_usuario_atual)
        self.assertEqual(client.get(path,params=params).status_code,401)
