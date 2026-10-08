"""Applicability precedence, real consumers, HTTP and physical migration."""
import json
import unittest
import os
from urllib.parse import urlsplit, parse_qsl
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException
import test_planejamento_mental as foundation
from app.models.atividade_terapeutica import AtividadeTerapeutica, AtividadeModulo
from app.services.atividade_aplicabilidade import activity_applies
from app.services.care_plan_service import CarePlanService


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ActivityLinesTests(unittest.TestCase):
    schema_revision = 'head'
    setUpClass = classmethod(foundation.PlanningTests.setUpClass.__func__)
    tearDownClass = classmethod(foundation.PlanningTests.tearDownClass.__func__)
    setUp = foundation.PlanningTests.setUp
    tearDown = foundation.PlanningTests.tearDown
    command_grant = foundation.PlanningTests.command_grant
    path = foundation.PlanningTests.path
    request = foundation.PlanningTests.request
    create = foundation.PlanningTests.create
    def catalog_setup(self):
        from app.routers.atividades_terapeuticas import router
        from app.core.deps import get_usuario_atual
        self.app.include_router(router)
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(id=self.actor,perfil='ADMIN')
        self.db.execute(text("INSERT INTO modulos_clinicos(id,nome,slug,ativo) VALUES(2,'Cardio','cardiometabolico',true) ON CONFLICT(id) DO NOTHING"));self.db.commit()

    def http(self,method,path,payload=None):
        u=urlsplit(path)
        return self.client.request(method,'/atividades-terapeuticas'+u.path,params=dict(parse_qsl(u.query)),body=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})

    def test_create_multiline_same_id_all_lines_and_unique(self):
        self.catalog_setup()
        r=self.http('POST','/',dict(nome='Multiline',modulo_ids=[1,2,3]));self.assertEqual(r.status_code,200,r.text)
        a=r.json();self.assertIsNone(a['modulo_id']);self.assertEqual(a['modulo_ids'],[1,2,3])
        for module in [1,2,3]:
            rows=self.http('GET',f'/?modulo_id={module}').json()
            self.assertEqual(sum(x['id']==a['id'] for x in rows),1)
        with self.assertRaises(IntegrityError):
            with self.db.begin_nested():
                self.db.add(AtividadeModulo(atividade_id=a['id'],modulo_id=1));self.db.flush()
        single=self.http('POST','/',dict(nome='Single',modulo_ids=[2])).json()
        self.assertEqual((single['modulo_id'],single['modulo_ids']),(2,[2]))

    def test_edit_precedence_and_both_consumers(self):
        self.catalog_setup()
        self.db.execute(text('UPDATE atividades_terapeuticas SET modulo_id=1 WHERE id=:id'),dict(id=self.activity));self.db.commit()
        self.db.execute(text("UPDATE profissionais SET ocupacao_id=:o WHERE id=:p"),dict(o=self.occupation,p=self.executor));self.db.commit()
        service=CarePlanService()
        # Keep all existing executor/clinic checks; provide a synthetic compatible legacy patient.
        plan=SimpleNamespace(paciente_id=9)
        original=service.row
        from app.models import Paciente
        def row(db,model,identity):
            return SimpleNamespace(clinica_id=None) if model is Paciente else original(db,model,identity)
        def legacy_accepts(module):
            with patch.object(service,'assigned',return_value=SimpleNamespace(module_id=module)),patch.object(service,'row',side_effect=row):
                return service.catalog(self.db,plan,self.activity,self.occupation,self.executor)
        legacy_accepts(1)
        for lines in [[1],[1,3],[3]]:
            r=self.http('PUT',f'/{self.activity}/linhas',dict(modulo_ids=lines));self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['modulo_id'],1)
            self.assertEqual(activity_applies(self.db,self.activity,1),1 in lines)
            if 1 in lines:legacy_accepts(1)
            else:
                with self.assertRaises(HTTPException):legacy_accepts(1)
            response=self.request('POST',self.suffix,self.payload)
            self.assertEqual(response.status_code,201 if 3 in lines else 422,response.text)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM atividade_ocupacao WHERE atividade_id=:a'),dict(a=self.activity)),1)
        self.db.execute(text('UPDATE atividades_terapeuticas SET modulo_id=NULL WHERE id=:id'),dict(id=self.activity));self.db.commit()
        self.http('PUT',f'/{self.activity}/linhas',dict(modulo_ids=[1,3]));legacy_accepts(1)
        self.assertEqual(self.request('POST',self.suffix,self.payload).status_code,201)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM sessoes_assistenciais')),0)

    def test_no_association_no_legacy_no_leak_and_validation_security(self):
        self.catalog_setup()
        self.db.execute(text('UPDATE atividades_terapeuticas SET modulo_id=NULL WHERE id=:id'),dict(id=self.activity));self.db.commit()
        self.assertNotIn(self.activity,[x['id'] for x in self.http('GET','/?modulo_id=3').json()])
        for values in [[],[1,1],[9999]]:
            self.assertEqual(self.http('PUT',f'/{self.activity}/linhas',dict(modulo_ids=values)).status_code,422)
        self.assertEqual(self.http('PUT','/999999/linhas',dict(modulo_ids=[3])).status_code,404)
        from app.core.deps import get_usuario_atual
        self.app.dependency_overrides[get_usuario_atual]=lambda:SimpleNamespace(perfil='PROFISSIONAL')
        self.assertEqual(self.http('PUT',f'/{self.activity}/linhas',dict(modulo_ids=[3])).status_code,403)
        self.app.dependency_overrides.pop(get_usuario_atual)
        self.assertEqual(self.http('GET','/linhas').status_code,401)
        self.assertEqual(self.http('PUT',f'/{self.activity}/linhas',dict(modulo_ids=[3])).status_code,401)

    def test_migration_backfill_and_roundtrip(self):
        from uuid import uuid4
        from sqlalchemy import create_engine,inspect
        from alembic import command
        from test_m0_baseline import config
        name='activity_lines_'+uuid4().hex
        with self.admin.connect() as c:c.exec_driver_sql('CREATE DATABASE '+name)
        engine=create_engine(self.engine.url.set(database=name))
        try:
            with engine.begin() as c:
                command.upgrade(config(c),'w3_cbi_v1')
                c.execute(text("INSERT INTO atividades_terapeuticas(nome,modulo_id) VALUES('Mental',3),('Unclassified',NULL)"))
                before=c.execute(text('SELECT id,modulo_id FROM atividades_terapeuticas ORDER BY id')).all()
                command.upgrade(config(c),'w3_atividade_linhas_v1')
                self.assertEqual(c.execute(text('SELECT id,modulo_id FROM atividades_terapeuticas ORDER BY id')).all(),before)
                self.assertEqual(c.execute(text('SELECT atividade_id,modulo_id FROM atividade_modulos ORDER BY atividade_id')).all(),[r for r in before if r.modulo_id is not None])
                self.assertEqual(inspect(c).get_pk_constraint('atividade_modulos')['constrained_columns'],['atividade_id','modulo_id'])
                self.assertIn('ix_atividade_modulos_modulo_atividade',[i['name'] for i in inspect(c).get_indexes('atividade_modulos')])
                columns=inspect(c).get_columns('atividade_modulos')
                self.assertEqual([(x['name'],str(x['type']),x['nullable'],x['default']) for x in columns], [('atividade_id','INTEGER',False,None),('modulo_id','INTEGER',False,None)])
                fks=inspect(c).get_foreign_keys('atividade_modulos')
                self.assertEqual({(tuple(f['constrained_columns']),f['referred_table'],f['options']['ondelete']) for f in fks}, {(('atividade_id',),'atividades_terapeuticas','CASCADE'),(('modulo_id',),'modulos_clinicos','RESTRICT')})
                self.assertTrue(c.execute(text("SELECT bool_and(indisvalid AND indisready) FROM pg_index WHERE indrelid='atividade_modulos'::regclass")).scalar())
                self.assertTrue(c.execute(text("SELECT bool_and(convalidated) FROM pg_constraint WHERE conrelid='atividade_modulos'::regclass")).scalar())
                command.downgrade(config(c),'w3_cbi_v1')
                command.upgrade(config(c),'head')
        finally:
            engine.dispose()
            with self.admin.connect() as c:c.exec_driver_sql('DROP DATABASE '+name+' WITH (FORCE)')
