"""C1.2: synthetic data only, disposable PostgreSQL guarded by G1 fixture."""
import unittest
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
import test_institucional as institutional
from app.models.institucional import ProfissionalInstituicao, CapacidadeProfissional
from app.schemas.institucional import CapacidadeProfissionalRequest
from app.services.institucional import InstitucionalErro
from app.routers.vinculos_institucionais import router
from app.core.permissoes import exigir_admin
from app.database import get_db
from types import SimpleNamespace


class CapacityContracts(unittest.TestCase):
    def test_invalid_payloads(self):
        for change in ({'minutos_semanais': 0}, {'minutos_semanais': -1}, {'minutos_semanais': True},
                       {'minutos_semanais': 1.5}, {'minutos_semanais': 2147483648}, {'ativo': False},
                       {'data_fim': '2025-12-31'}, {'motivo': ' '}, {'instituicao_id': 2}):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                CapacidadeProfissionalRequest.model_validate(dict(minutos_semanais=120,
                    data_inicio='2026-01-01', motivo='Teste', **{}) | change)


@unittest.skipUnless(os.getenv('G1_TEST_POSTGRES_URL'), 'Requires disposable G1 PostgreSQL')
class CapacityManagementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        institutional.InstitutionalPostgresTests.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        institutional.InstitutionalPostgresTests.tearDownClass.__func__(cls)

    link = institutional.InstitutionalPostgresTests.link

    def tearDown(self):
        self.db.close()
        if self.tx.is_active:
            self.tx.rollback()
        self.conn.close()

    def setUp(self):
        institutional.InstitutionalPostgresTests.setUp(self)
        self.capacity_link = self.s.create(self.db, ProfissionalInstituicao,
            dict(profissional_id=self.pr, instituicao_id=self.a.id, ocupacao_id=self.oc,
                 data_inicio=date(2026,1,1), data_fim=date(2026,12,31)), actor_id=self.actor, motivo='Synthetic')
        self.ids = dict(instituicao_id=self.a.id, vinculo_id=self.capacity_link.id, actor_id=self.actor,
                        reference_date=date(2026,6,1))

    def create_capacity(self, **changes):
        payload = dict(minutos_semanais=120, data_inicio=date(2026,1,1), data_fim=date(2026,12,31))
        payload.update(changes)
        return self.s.manage_capacity(self.db, **self.ids, motivo='Synthetic', operation='CREATE_CAPACITY', payload=payload)

    def events(self):
        return self.db.execute(text("SELECT operacao FROM institucional_operacoes WHERE instituicao_id=:i AND tipo_alvo='CAPACIDADE_PROFISSIONAL' ORDER BY id"), {'i':self.a.id}).scalars().all()

    def test_capacity_lifecycle_audit_and_idempotence(self):
        row=self.create_capacity(); self.assertTrue(row['vigente'])
        self.assertEqual(self.create_capacity()['id'],row['id']); self.assertEqual(len(self.events()),1)
        args=dict(self.ids, motivo='Synthetic', identity=row['id'])
        closed=self.s.manage_capacity(self.db, **args, operation='CLOSE_CAPACITY',end=date(2026,5,31))
        self.assertFalse(closed['vigente']); self.assertEqual(closed['estado'],'ENCERRADO')
        self.s.manage_capacity(self.db, **args, operation='CLOSE_CAPACITY',end=date(2026,5,31))
        self.s.manage_capacity(self.db, **args, operation='INVALIDATE_CAPACITY')
        self.s.manage_capacity(self.db, **args, operation='INVALIDATE_CAPACITY')
        self.assertEqual(self.events(),['CREATE_CAPACITY','CLOSE_CAPACITY','INVALIDATE_CAPACITY'])
        self.assertEqual(len(self.s.capacities(self.db,**self.ids)),1)
        self.assertEqual(self.db.query(CapacidadeProfissional).filter_by(id=row['id']).count(),1)

    def test_capacity_overlap_boundaries_parent_and_reason(self):
        self.create_capacity(data_fim=date(2026,6,1))
        for change in ({'data_inicio':date(2026,6,1)}, {'data_inicio':date(2025,12,31)}, {'data_fim':None}):
            with self.assertRaises(InstitucionalErro):self.create_capacity(**change)
        self.create_capacity(data_inicio=date(2026,6,2))
        with self.assertRaises(InstitucionalErro):
            self.s.manage_capacity(self.db,**self.ids,motivo=' ',operation='INVALIDATE_CAPACITY',identity=1)

    def test_capacity_authority_and_institution_scope(self):
        self.create_capacity()
        for override in ({'instituicao_id':self.b.id},{'actor_id':999999}):
            with self.assertRaises(InstitucionalErro):self.s.capacities(self.db,**(self.ids|override))
        self.db.execute(text("UPDATE usuarios SET perfil='GESTOR' WHERE id=:id"),{'id':self.actor})
        with self.assertRaises(InstitucionalErro):self.create_capacity()
        with self.assertRaises(InstitucionalErro):self.s.capacities(self.db,**self.ids)

    def test_capacity_effective_parent_and_status(self):
        self.create_capacity()
        for ref,expected in ((date(2025,12,31),False),(date(2026,1,1),True),(date(2026,12,31),True),(date(2027,1,1),False)):
            self.assertEqual(self.s.capacities(self.db,**(self.ids|{'reference_date':ref}))[0]['vigente'],expected)
        for table,identity in (('instituicoes',self.a.id),('profissionais',self.pr),('profissional_instituicoes',self.capacity_link.id)):
            self.db.execute(text(f'UPDATE {table} SET ativo=false WHERE id=:id'),{'id':identity})
            self.assertFalse(self.s.capacities(self.db,**self.ids)[0]['vigente'])
            with self.assertRaises(InstitucionalErro):self.create_capacity()
            self.db.execute(text(f'UPDATE {table} SET ativo=true WHERE id=:id'),{'id':identity})

    def test_capacity_blocks_parent_truncation_and_invalidation(self):
        row=self.create_capacity()
        with self.assertRaises(InstitucionalErro):self.s.close(self.db,ProfissionalInstituicao,self.capacity_link.id,date(2026,5,1),actor_id=self.actor,motivo='Synthetic')
        with self.assertRaises(InstitucionalErro):self.s.invalidate(self.db,ProfissionalInstituicao,self.capacity_link.id,actor_id=self.actor,motivo='Synthetic')
        self.s.manage_capacity(self.db,**self.ids,motivo='Synthetic',identity=row['id'],operation='INVALIDATE_CAPACITY')
        self.s.invalidate(self.db,ProfissionalInstituicao,self.capacity_link.id,actor_id=self.actor,motivo='Synthetic')

    def test_capacity_no_clinical_grants(self):
        from app.models.permissao_assistencial import ConcessaoAssistencial, ContextoProfissional
        from app.services.autorizacao_contextual import AutorizacaoContextualService
        tables=[ConcessaoAssistencial.__tablename__, ContextoProfissional.__tablename__]
        before={t:self.db.execute(text(f'SELECT count(*) FROM {t}')).scalar() for t in tables}
        self.create_capacity()
        self.assertEqual(before,{t:self.db.execute(text(f'SELECT count(*) FROM {t}')).scalar() for t in tables})
        for capability in ('ASSISTENCIAL_LER','ASSISTENCIAL_REGISTRAR'):
            query=AutorizacaoContextualService().authorized_context_query(actor_id=self.actor,capability=capability,instituicao_id=self.a.id)
            self.assertEqual(self.db.execute(query).all(),[])

    def test_capacity_http_contract_and_scope(self):
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[exigir_admin]=lambda:SimpleNamespace(id=self.actor)
        # Service owns no commit; prevent HTTP commit of the fixture outer transaction.
        client=TestClient(app)
        base=f'/admin/vinculos-institucionais/profissionais/{self.capacity_link.id}/capacidades'
        params={'instituicao_id':self.a.id,'data_referencia':'2026-06-01'}
        response=client.post(base,params=params,json={'minutos_semanais':120,'data_inicio':'2026-01-01','data_fim':'2026-12-31','motivo':'Synthetic'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['vigente'])
        self.assertEqual(len(client.get(base,params=params).json()),1)
        identity=response.json()['id']
        closed=client.post(base+f'/{identity}/close',params=params,json={'data_fim':'2026-05-31','motivo':'Synthetic'})
        self.assertEqual(closed.status_code,200,closed.text)
        self.assertFalse(closed.json()['vigente'])
        invalid=client.post(base+f'/{identity}/invalidate',params=params,json={'motivo':'Synthetic'})
        self.assertEqual(invalid.status_code,200,invalid.text)
        self.assertEqual(invalid.json()['estado'],'INVALIDADO')
        self.assertEqual(client.get(base,params={'instituicao_id':self.b.id}).status_code,404)

    def test_capacity_concurrent_duplicate(self):
        self.db.execute(text('UPDATE usuarios SET email=:e WHERE id=:i'),{'e':uuid4().hex+'@synthetic.invalid','i':self.actor})
        self.db.flush(); self.tx.commit()
        ids=dict(self.ids)
        def worker(minutes):
            with Session(self.engine) as db:
                try:
                    row=self.s.manage_capacity(db,**ids,motivo='Concurrent',operation='CREATE_CAPACITY',payload={
                        'minutos_semanais':minutes,'data_inicio':date(2026,1,1),'data_fim':date(2026,12,31)})
                    db.commit();return row['id']
                except InstitucionalErro as exc:db.rollback();return exc.code
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(worker,[120,120]))
        self.assertEqual(results[0],results[1])
        self.assertEqual(worker(121),'PERIOD_CONFLICT')
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM capacidades_profissionais WHERE profissional_instituicao_id=:i'),{'i':ids['vinculo_id']}).scalar(),1)

    def test_capacity_rollback_preserves_atomicity(self):
        with self.db.begin_nested() as savepoint:
            self.create_capacity()
            self.assertEqual(len(self.events()),1)
            savepoint.rollback()
        self.assertEqual(self.s.capacities(self.db,**self.ids),[])
        self.assertEqual(self.events(),[])

    def test_capacity_cannot_reopen_or_cross_link(self):
        row=self.create_capacity(data_fim=date(2026,6,30))
        with self.assertRaises(InstitucionalErro):
            self.s.manage_capacity(self.db,**self.ids,motivo='Synthetic',identity=row['id'],
                operation='CLOSE_CAPACITY',end=date(2026,7,1))
        with self.assertRaises(InstitucionalErro):
            self.s.manage_capacity(self.db,**(self.ids|{'instituicao_id':self.b.id}),motivo='Synthetic',
                identity=row['id'],operation='INVALIDATE_CAPACITY')
        self.assertEqual(self.events(),['CREATE_CAPACITY'])

    def test_capacity_schema_matches_existing_migration(self):
        import importlib.util
        from pathlib import Path
        path=Path('alembic_canonical/versions/capacidade_reconciliacao_v1.py')
        spec=importlib.util.spec_from_file_location('capacity_schema',path)
        migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
        migration.validate_capacity(self.conn)
        self.assertEqual(set(CapacidadeProfissional.__table__.columns.keys()),
            {'id','profissional_instituicao_id','minutos_semanais','data_inicio','data_fim','ativo','criado_em','atualizado_em'})


    def test_capacity_http_denies_non_admin(self):
        from app.core.deps import get_usuario_atual
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor,perfil='GESTOR')
        client=TestClient(app)
        base=f'/admin/vinculos-institucionais/profissionais/{self.capacity_link.id}/capacidades'
        self.assertEqual(client.get(base,params={'instituicao_id':self.a.id}).status_code,403)
        self.assertEqual(client.post(base,params={'instituicao_id':self.a.id},json={
            'minutos_semanais':120,'data_inicio':'2026-01-01','motivo':'Synthetic'}).status_code,403)
        self.assertEqual(self.events(),[])
