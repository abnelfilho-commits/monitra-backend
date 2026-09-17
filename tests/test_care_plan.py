"""Synthetic Care Plan contracts; no application database is used."""
import ast
import os
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from fastapi import FastAPI, HTTPException
import asyncio
import json
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.models import (Clinica, OcupacaoProfissional, Profissional, Usuario, Paciente,
    ModuloClinico, PacienteModulo, PTS, PTSObjetivo, AgendaCuidado,
    AtividadeTerapeutica, AtividadeOcupacao, SessaoAssistencial, ProfissionalModulo)
from app.schemas.pts import PTSCreate, PTSObjetivoCreate, PTSObjetivoUpdate
from app.schemas.agenda_cuidado import AgendaCuidadoCreate, AgendaCuidadoUpdate, AgendaFrequenciaUpdate
from app.services.care_plan_service import CarePlanService
from app.services.care_lines import AmbiguousCareLine, PatientCareLineNotFound, CareLineNotFound
from app.services.scheduling_service import SchedulingService

DAY = date(2026, 1, 10)
MODELS = (Clinica, OcupacaoProfissional, Profissional, Usuario, Paciente,
    ModuloClinico, PacienteModulo, PTS, PTSObjetivo, AtividadeTerapeutica,
    AtividadeOcupacao, AgendaCuidado, SessaoAssistencial, ProfissionalModulo)


def seed(db):
    db.add_all([Clinica(id=1,nome='Synthetic'), Clinica(id=2,nome='Other')])
    db.add_all([OcupacaoProfissional(id=1,nome='A',ativo=True),
                OcupacaoProfissional(id=2,nome='B',ativo=True)])
    db.flush()
    db.add_all([Profissional(id=70,nome='A',clinica_id=1,ocupacao_id=1,ativo=True),
                Profissional(id=71,nome='B',clinica_id=2,ocupacao_id=1,ativo=True),
                Profissional(id=72,nome='C',clinica_id=1,ocupacao_id=2,ativo=True),
                Profissional(id=73,nome='D',clinica_id=1,ocupacao_id=1,ativo=True)])
    db.flush()
    db.add(Usuario(id=50,nome='Synthetic',email='test@example.invalid',senha_hash='unused',clinica_id=1))
    db.add_all([Paciente(id=i,nome='Synthetic',clinica_id=1 if i != 30 else 2,ativo=True) for i in (10,20,30,40)])
    db.add_all([ModuloClinico(id=1,nome='Neuro',slug='neurodesenvolvimento',ativo=True),
                ModuloClinico(id=2,nome='Cardio',slug='cardiometabolico',ativo=True)])
    db.flush()
    for professional in (70, 72, 73):
        for module in (1, 2):
            db.add(ProfissionalModulo(profissional_id=professional, modulo_id=module))
    for pid, module in ((10,1),(20,2),(30,1),(40,1),(40,2)):
        db.add(PacienteModulo(paciente_id=pid,modulo_id=module,ativo=True))
    for i, module in ((1,1),(2,2),(3,None)):
        db.add(AtividadeTerapeutica(id=i,nome='Synthetic',modulo_id=module,ativo=True))
    db.flush()
    for i in (1,2,3):
        db.add(AtividadeOcupacao(atividade_id=i,ocupacao_id=1))
    db.commit()


class CarePlanTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:',poolclass=StaticPool,
                                    connect_args={'check_same_thread':False})
        for model in MODELS:
            model.__table__.create(self.engine)
        self.db=Session(self.engine)
        seed(self.db)
        self.user=SimpleNamespace(id=50,perfil='PROFISSIONAL',clinica_id=1)
        self.service=CarePlanService()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def create(self, pid=10, module=None):
        return self.service.create(self.db,PTSCreate(paciente_id=pid,modulo_id=module,data_inicio=DAY),self.user)

    def agenda(self, pid=10, activity=1):
        pts=self.create(pid)
        obj=self.service.create_objective(self.db,pts.id,PTSObjetivoCreate(descricao='Goal'),self.user)
        payload=AgendaCuidadoCreate(pts_id=pts.id,objetivo_id=obj.id,atividade_id=activity,
            ocupacao_id=1,profissional_id=70,frequencia_semanal=1,duracao_minutos=30,
            quantidade_sessoes=2,data_inicio=DAY)
        return self.service.create_agenda(self.db,payload,self.user)

    def sessions(self, agenda):
        return SchedulingService.confirmar_cronograma(self.db,agenda,
            [SimpleNamespace(numero=1,data=DAY,hora_inicio=None,hora_fim=None)])

    def test_neuro_cardio_and_actor(self):
        self.assertEqual(self.create().modulo_id,1)
        cardio=self.create(20)
        self.assertEqual((cardio.modulo_id,cardio.criado_por_usuario_id),(2,50))

    def test_ambiguity_explicit_lines_and_conflict(self):
        with self.assertRaises(AmbiguousCareLine): self.create(40)
        self.create(40,1); self.create(40,2)
        with self.assertRaises(HTTPException): self.create(40,1)
        self.assertEqual(self.db.query(PTS).count(),2)

    def test_invalid_unlinked_inactive(self):
        for module,error in ((99,CareLineNotFound),(2,PatientCareLineNotFound)):
            with self.assertRaises(error): self.create(10,module)
        self.db.get(ModuloClinico,1).ativo=False; self.db.commit()
        with self.assertRaises(PatientCareLineNotFound): self.create(10,1)

    def test_close_reopen_conflict(self):
        pts=self.create(); pid=pts.id
        self.service.set_closed(self.db,pid,self.user,True)
        self.assertEqual(pts.status,'ENCERRADO'); self.assertEqual(pts.data_fim,date.today())
        other=self.create()
        with self.assertRaises(HTTPException): self.service.set_closed(self.db,pid,self.user,False)
        self.service.set_closed(self.db,other.id,self.user,True)
        self.service.set_closed(self.db,pid,self.user,False)
        self.assertEqual((pts.status,pts.data_fim),('ATIVO',None))

    def test_null_read_no_inference_and_safe_close(self):
        pts=PTS(paciente_id=10,modulo_id=None,data_inicio=DAY)
        self.db.add(pts); self.db.commit(); pid=pts.id
        self.assertEqual(len(self.service.list_plans(self.db,10,self.user)),1)
        self.assertEqual(self.service.list_plans(self.db,10,self.user,1),[])
        with self.assertRaises(HTTPException): self.service.set_closed(self.db,pid,self.user,False)
        with self.assertRaises(HTTPException): self.service.create_objective(self.db,pid,PTSObjetivoCreate(descricao='x'),self.user)
        self.service.set_closed(self.db,pid,self.user,True)
        self.assertIsNone(pts.modulo_id)

    def test_historical_identity_survives_link_deactivation(self):
        pts=self.create(); pid=pts.id
        self.db.query(PacienteModulo).filter_by(paciente_id=10).first().ativo=False
        self.db.commit()
        self.service.set_closed(self.db,pid,self.user,True)
        self.service.set_closed(self.db,pid,self.user,False)
        self.assertEqual(pts.modulo_id,1)

    def test_acl_admin_and_admin_clinica(self):
        for role in ('PROFISSIONAL','ADMIN_CLINICA'):
            self.user.perfil=role
            with self.assertRaises(HTTPException) as cm: self.create(30,1)
            self.assertEqual(cm.exception.status_code,403)
            with self.assertRaises(HTTPException): self.service.list_plans(self.db,30,self.user)
        self.user.perfil='ADMIN'; pts=self.create(30,1)
        self.user.perfil='ADMIN_CLINICA'
        with self.assertRaises(HTTPException): self.service.set_closed(self.db,pts.id,self.user,True)

    def test_objective_fields_and_ancestry_acl(self):
        pts=self.create()
        obj=self.service.create_objective(self.db,pts.id,PTSObjetivoCreate(descricao='Goal',prioridade='ALTA'),self.user)
        payload=PTSObjetivoUpdate(descricao='Revised',status='CONCLUIDO',pts_id=999)
        self.service.update_objective(self.db,obj.id,payload,self.user)
        self.assertEqual((obj.pts_id,obj.descricao,obj.status),(pts.id,'Revised','CONCLUIDO'))
        self.user.clinica_id=2
        with self.assertRaises(HTTPException): self.service.list_objectives(self.db,pts.id,self.user)
        with self.assertRaises(HTTPException): self.service.update_objective(self.db,obj.id,payload,self.user)

    def test_cardio_catalog_and_cross_line(self):
        agenda=self.agenda(20,2)
        pts=self.db.get(PTS,agenda.pts_id)
        for activity,occupation,professional in ((1,1,70),(3,1,70),(2,2,72),(2,1,71),(2,1,72)):
            with self.assertRaises(HTTPException): self.service.catalog(self.db,pts,activity,occupation,professional)
        self.db.get(AtividadeTerapeutica,2).ativo=False; self.db.commit()
        self.assertEqual(len(self.service.list_agendas(self.db,agenda.objetivo_id,self.user)),1)
        with self.assertRaises(HTTPException): self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(observacoes='x'),self.user)

    def test_agenda_mismatched_pts_and_update_professional(self):
        agenda=self.agenda(); other=self.create(20)
        payload=AgendaCuidadoCreate(pts_id=other.id,objetivo_id=agenda.objetivo_id,atividade_id=2,
            ocupacao_id=1,profissional_id=70,frequencia_semanal=1,duracao_minutos=30,data_inicio=DAY)
        with self.assertRaises(HTTPException): self.service.create_agenda(self.db,payload,self.user)
        with self.assertRaises(HTTPException): self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(profissional_id=71),self.user)
        self.assertEqual(agenda.profissional_id,70)
        agenda.pts_id=other.id; self.db.commit()
        with self.assertRaises(HTTPException): self.service.agenda(self.db,agenda.id,self.user)

    def test_sessions_preserved_and_deletion_blocked(self):
        agenda=self.agenda(); session=self.sessions(agenda)[0]
        session.status='REALIZADA'; self.db.commit()
        before=(session.profissional_id,session.data_agendada,session.duracao_minutos,session.status)
        self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(profissional_id=73,duracao_minutos=60,quantidade_sessoes=8),self.user)
        self.service.set_closed(self.db,agenda.pts_id,self.user,True)
        self.db.refresh(session)
        self.assertEqual(before,(session.profissional_id,session.data_agendada,session.duracao_minutos,session.status))
        with self.assertRaises(HTTPException) as cm: self.service.delete_agenda(self.db,agenda.id,self.user)
        self.assertEqual(cm.exception.status_code,409)
        self.assertEqual(self.db.query(SessaoAssistencial).count(),1)
        with self.assertRaises(ValueError): self.sessions(agenda)

    def test_null_session_professional_blocks_reassignment(self):
        agenda=self.agenda(); session=self.sessions(agenda)[0]
        session.profissional_id=None; self.db.commit()
        with self.assertRaises(HTTPException): self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(profissional_id=73),self.user)

    def test_delete_empty_and_frequency_response(self):
        from app.routers.agenda_cuidados import registrar_frequencia
        agenda=self.agenda()
        result=registrar_frequencia(agenda.id,AgendaFrequenciaUpdate(status_execucao='REALIZADO'),self.db,self.user)
        self.assertEqual(result['status_execucao'],'REALIZADO')
        self.assertEqual(result['sessoes_geradas'],0)
        self.assertFalse(result['cronograma_confirmado'])
        self.service.delete_agenda(self.db,agenda.id,self.user)
        self.assertEqual(self.db.query(AgendaCuidado).count(),0)

    def test_failed_commit_rolls_back(self):
        with patch.object(self.db,'commit',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError): self.create()
        self.assertEqual(self.db.query(PTS).count(),0)

    def test_report_legacy_read_unchanged(self):
        from app.services.pts_service import PTSService
        self.create(40,1); self.create(40,2)
        context=PTSService.build_report_context(self.db,40)
        self.assertEqual(context['total_pts'],2)
        self.assertEqual({p['modulo_id'] for p in context['historico']},{1,2})

    def test_http_authentication_all_entry_points(self):
        from app.routers import pts, agenda_cuidados, scheduling
        app=FastAPI()
        for router in (pts.router,agenda_cuidados.router,scheduling.router): app.include_router(router)
        async def request(method, path):
            messages=[]
            async def receive():
                return {'type':'http.request','body':b'{}','more_body':False}
            async def send(message): messages.append(message)
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                'method':method,'scheme':'http','path':path,'raw_path':path.encode(),
                'query_string':b'', 'headers':[(b'content-type',b'application/json')],
                'client':('127.0.0.1',1),'server':('test',80),'root_path':''},receive,send)
            return next(m['status'] for m in messages if m['type']=='http.response.start')
        for route in app.routes:
            if not hasattr(route,'dependant'): continue
            import re
            path=re.sub(r'\{[^}]+\}','1',route.path)
            for method in route.methods:
                self.assertEqual(asyncio.run(request(method,path)),401,(method,path))

    def request(self, method, path, payload=None):
        from app.routers import pts, agenda_cuidados, scheduling
        from app.database import get_db
        from app.core.deps import get_usuario_atual
        app=FastAPI()
        for router in (pts.router,agenda_cuidados.router,scheduling.router): app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_usuario_atual]=lambda:self.user
        async def run():
            messages=[]
            async def receive():
                return {'type':'http.request','body':json.dumps(payload).encode(),'more_body':False}
            async def send(message): messages.append(message)
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1',
                'method':method,'scheme':'http','path':path,'raw_path':path.encode(),
                'query_string':b'', 'headers':[(b'content-type',b'application/json')],
                'client':('127.0.0.1',1),'server':('test',80),'root_path':''},receive,send)
            status=next(m['status'] for m in messages if m['type']=='http.response.start')
            body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
            return status,json.loads(body)
        return asyncio.run(run())

    def test_http_neuro_multiline_payload_and_scheduling(self):
        status,pts=self.request('POST','/pts',{'paciente_id':40,'modulo_id':1,'data_inicio':DAY.isoformat()})
        self.assertEqual(status,200,pts)
        self.assertEqual(pts['modulo_id'],1)
        self.assertTrue({'objetivos','created_at','status','data_fim'} <= set(pts))
        status,obj=self.request('POST','/pts/%s/objetivos'%pts['id'],{'descricao':'Goal','prioridade':'ALTA'})
        self.assertEqual(status,200,obj)
        status,agenda=self.request('POST','/agenda-cuidados/',{'pts_id':pts['id'],'objetivo_id':obj['id'],
            'atividade_id':1,'ocupacao_id':1,'profissional_id':70,'frequencia_semanal':2,
            'duracao_minutos':30,'quantidade_sessoes':2,'data_inicio':DAY.isoformat()})
        self.assertEqual(status,200,agenda)
        aid=agenda['id']
        status,suggestion=self.request('POST','/scheduling/agenda/%s/sugerir'%aid)
        self.assertEqual(status,200,suggestion)
        self.assertEqual(len(suggestion['cronograma']),2)
        status,result=self.request('POST','/scheduling/agenda/%s/confirmar'%aid,
            {'cronograma':[{'numero':1,'data':DAY.isoformat(),'hora_inicio':'09:00:00','hora_fim':'09:30:00'}]})
        self.assertEqual(status,200,result)
        self.assertEqual(result['total'],1)
        status,rows=self.request('GET','/agenda-cuidados/objetivo/%s'%obj['id'])
        self.assertEqual(status,200,rows)
        self.assertTrue(rows[0]['cronograma_confirmado'])
        self.assertEqual(rows[0]['sessoes_geradas'],1)
        status,_=self.request('DELETE','/agenda-cuidados/%s'%aid)
        self.assertEqual(status,409)

    def test_http_cross_clinic_every_resource_family(self):
        agenda=self.agenda(); aid=agenda.id; oid=agenda.objetivo_id; pid=agenda.pts_id
        self.user.clinica_id=2
        cases=[('GET','/pts/paciente/10',None),('PUT','/pts/%s/encerrar'%pid,None),
            ('PUT','/pts/%s/reabrir'%pid,None),('GET','/pts/%s/objetivos'%pid,None),
            ('PUT','/pts/objetivos/%s'%oid,{'descricao':'x'}),
            ('GET','/agenda-cuidados/objetivo/%s'%oid,None),
            ('PUT','/agenda-cuidados/%s'%aid,{'profissional_id':71}),
            ('DELETE','/agenda-cuidados/%s'%aid,None),
            ('POST','/scheduling/agenda/%s/sugerir'%aid,None),
            ('POST','/scheduling/agenda/%s/confirmar'%aid,{'cronograma':[{'numero':1,'data':DAY.isoformat()}]})]
        for method,path,payload in cases:
            status,body=self.request(method,path,payload)
            self.assertEqual(status,403,(path,body))

    def test_scoped_read_ambiguity_and_auto_resolution(self):
        self.create()
        self.assertEqual(len(self.service.list_scoped(self.db,10,self.user)),1)
        with self.assertRaises(AmbiguousCareLine): self.service.list_scoped(self.db,40,self.user)

    def test_session_patient_mismatch_rejected(self):
        agenda=self.agenda(); session=self.sessions(agenda)[0]
        session.paciente_id=20; self.db.commit()
        with self.assertRaises(HTTPException): self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(observacoes='x'),self.user)

    def test_future_line_reuses_core_and_inactive_application_line_rejected(self):
        from dataclasses import replace
        from app.services.care_lines import NEURO, CARDIO, CareLineRegistry, CareLineResolver, CareLineInactive
        future=replace(NEURO,code='FUTURE',slug='future',module_id=9)
        self.db.add(ModuloClinico(id=9,nome='Synthetic',slug='future',ativo=True))
        self.db.add(PacienteModulo(paciente_id=10,modulo_id=9,ativo=True)); self.db.commit()
        self.service=CarePlanService(CareLineResolver(CareLineRegistry([NEURO,CARDIO,future])))
        self.assertEqual(self.create(10,9).modulo_id,9)
        self.service=CarePlanService(CareLineResolver(CareLineRegistry([replace(NEURO,active=False),CARDIO])))
        with self.assertRaises(CareLineInactive): self.create(10,1)

    def test_inactive_link_and_catalog(self):
        agenda=self.agenda()
        self.db.get(OcupacaoProfissional,1).ativo=False; self.db.commit()
        with self.assertRaises(HTTPException): self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(observacoes='x'),self.user)
        self.db.get(OcupacaoProfissional,1).ativo=True
        self.db.get(Profissional,70).ativo=False; self.db.commit()
        with self.assertRaises(HTTPException): self.service.update_agenda(self.db,agenda.id,AgendaCuidadoUpdate(observacoes='x'),self.user)
        link=self.db.query(PacienteModulo).filter_by(paciente_id=20).one()
        link.ativo=False; self.db.commit()
        with self.assertRaises(PatientCareLineNotFound): self.create(20,2)

    def test_python39(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('app/services/care_plan_service.py','app/routers/pts.py','app/routers/agenda_cuidados.py','app/routers/scheduling.py'):
            ast.parse((root/name).read_text(),feature_version=(3,9))
