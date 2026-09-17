"""Synthetic Session/Attendance contracts. Never uses an application database."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from datetime import date
os.environ['DATABASE_URL']='sqlite:///:memory:'
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import (PTS, PTSObjetivo, SessaoAssistencial, FormularioModulo,
    CampoFormulario, RegistroLongitudinal, RespostaRegistro, PacienteModulo, ModuloClinico)
from app.schemas.assistential_session import RegistrarAtendimentoRequest
from app.services.assistential_execution_service import AssistentialExecutionService
import test_care_plan as fixtures
DAY=fixtures.DAY


class SessionFixture(unittest.TestCase):
    setUp = fixtures.CarePlanTests.setUp
    tearDown = fixtures.CarePlanTests.tearDown
    create = fixtures.CarePlanTests.create
    agenda = fixtures.CarePlanTests.agenda
    sessions = fixtures.CarePlanTests.sessions

    def observation_session(self, patient=10, activity=1):
        for model in (FormularioModulo,CampoFormulario,RegistroLongitudinal,RespostaRegistro):
            model.__table__.create(self.engine,checkfirst=True)
        for module, fid in ((1,105),(2,206)):
            if self.db.get(FormularioModulo,fid): continue
            self.db.add(FormularioModulo(id=fid,modulo_id=module,nome='Synthetic',
                codigo='ATENDIMENTO_SESSAO',tipo='LONGITUDINAL',ativo=True))
            self.db.add_all([CampoFormulario(id=fid*10,formulario_id=fid,nome_campo='narrativa_atendimento',
                    label='Narrative',tipo_campo='textarea',ativo=True,obrigatorio=True),
                CampoFormulario(id=fid*10+1,formulario_id=fid,nome_campo='proximos_passos',
                    label='Next',tipo_campo='multiselect',ativo=True,obrigatorio=False)])
        self.db.commit()
        agenda=self.agenda(patient,activity)
        session=self.sessions(agenda)[0]
        session.status='EM_ANDAMENTO'; self.db.commit()
        return session


class ExistingBehaviorTests(SessionFixture):
    def test_patient_sessions_filter_persisted_pts_line(self):
        from app.models import AgendaCuidado
        from app.services.session_service import SessionService
        neuro = self.observation_session(10,1)
        cardio = self.observation_session(20,2)
        self.user.profissional_id = 70
        cardio.paciente_id = 10
        agenda = self.db.get(AgendaCuidado,cardio.agenda_cuidado_id)
        self.db.get(PTS,agenda.pts_id).paciente_id = 10
        self.db.add(PacienteModulo(paciente_id=10,modulo_id=2,ativo=True))
        self.db.commit()
        service = SessionService()
        self.assertEqual([r.id for r in service.patient_sessions(self.db,10,self.user,'NEURO')],[neuro.id])
        self.assertEqual([r.id for r in service.patient_sessions(self.db,10,self.user,'CARDIO')],[cardio.id])

    def test_effective_neuro_payload_response_and_separate_finalize(self):
        session=self.observation_session()
        result=AssistentialExecutionService.registrar_atendimento(self.db,session,
            RegistrarAtendimentoRequest(narrativa='  Synthetic  ',proximos_passos=['x']),usuario=self.user)
        self.assertEqual(set(result),{'success','sessao_id','registro_id','mensagem'})
        self.assertEqual(result['mensagem'],'Atendimento registrado com sucesso.')
        self.assertEqual(session.status,'EM_ANDAMENTO')
        record=self.db.get(RegistroLongitudinal,result['registro_id'])
        self.assertEqual((record.modulo_id,record.formulario_id,record.origem),(1,105,'PROFISSIONAL'))
        self.assertEqual(record.data_registro,date.today())
        text=self.db.query(RespostaRegistro).filter_by(registro_id=record.id,campo_id=1050).one()
        self.assertEqual(text.valor_texto,'Synthetic')
        AssistentialExecutionService.finalizar(self.db,session,usuario=self.user)
        self.assertEqual(session.status,'REALIZADA')


class BoundaryTests(SessionFixture):
    def setUp(self):
        super().setUp()
        from app.services.session_service import SessionService
        self.boundary=SessionService()
        self.user.profissional_id=73  # Different from the assigned professional (70).

    def attend(self, session, **changes):
        values={'narrativa':'Synthetic','proximos_passos':['x']}; values.update(changes)
        return self.boundary.attend(self.db,session.id,self.user,RegistrarAtendimentoRequest(**values))

    def legacy(self, session, **changes):
        from app.schemas.registros_longitudinais import RegistroLongitudinalCreate
        module=self.db.get(PTS,session.agenda_cuidado.pts_id).modulo_id
        fid=105 if module==1 else 206
        values=dict(paciente_id=session.paciente_id,modulo_id=module,formulario_id=fid,
            origem='PROFISSIONAL',data_registro=DAY,
            respostas=[{'campo_id':fid*10,'valor':'Synthetic'}])
        values.update(changes)
        return RegistroLongitudinalCreate(**values)

    def test_cardio_shared_storage_and_distinct_authorship(self):
        session=self.observation_session(20,2)
        session.status='AGENDADA'; self.db.commit()
        self.boundary.transition(self.db,session.id,self.user,'confirmar')
        self.boundary.transition(self.db,session.id,self.user,'iniciar')
        result=self.attend(session)
        record=self.db.get(RegistroLongitudinal,result['registro_id'])
        self.assertEqual((record.modulo_id,record.formulario_id,record.criado_por_usuario_id),(2,206,50))
        self.assertIsNone(record.criado_por_responsavel_id)
        self.assertEqual(session.profissional_id,70)
        self.assertEqual(self.db.query(RespostaRegistro).count(),2)

    def test_sequential_duplicate_does_not_overwrite(self):
        session=self.observation_session(); result=self.attend(session)
        with self.assertRaises(HTTPException) as cm: self.attend(session)
        self.assertEqual(cm.exception.status_code,409)
        self.assertEqual(session.registro_longitudinal_id,result['registro_id'])
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),1)

    def test_four_rollback_checkpoints(self):
        session=self.observation_session()
        for checkpoint in (1,2,3,'commit'):
            real_flush=self.db.flush; calls=[0]
            def flush(*args,**kwargs):
                result=real_flush(*args,**kwargs); calls[0]+=1
                if calls[0]==checkpoint: raise RuntimeError('synthetic failure')
                return result
            with patch.object(self.db,'flush',side_effect=flush), patch.object(self.db,'commit',
                    side_effect=RuntimeError('synthetic commit') if checkpoint=='commit' else self.db.commit):
                with self.assertRaises(RuntimeError): self.attend(session)
            self.db.expire_all()
            self.assertIsNone(session.registro_longitudinal_id,checkpoint)
            self.assertEqual(self.db.query(RegistroLongitudinal).count(),0,checkpoint)
            self.assertEqual(self.db.query(RespostaRegistro).count(),0,checkpoint)
            self.assertEqual(session.status,'EM_ANDAMENTO')

    def test_clinic_acl_admin_and_unassigned_professional(self):
        session=self.observation_session()
        for role in ('PROFISSIONAL','ADMIN_CLINICA'):
            self.user.clinica_id=2; self.user.perfil=role
            with self.assertRaises(HTTPException) as cm: self.attend(session)
            self.assertEqual(cm.exception.status_code,403)
        self.user.perfil='ADMIN'
        self.attend(session)
        self.assertEqual(session.profissional_id,70)

    def test_personal_selection_does_not_grant_cross_clinic_access(self):
        session=self.observation_session(); self.user.profissional_id=70
        self.assertEqual(len(self.boundary.personal_sessions(self.db,self.user)),1)
        self.user.clinica_id=2
        with self.assertRaises(HTTPException): self.boundary.personal_sessions(self.db,self.user)

    def test_patient_and_objective_ancestry_mismatches(self):
        session=self.observation_session(); sid=session.id
        session.paciente_id=20; self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)
        session.paciente_id=10
        obj=self.db.get(PTSObjetivo,session.agenda_cuidado.objetivo_id)
        obj.pts_id=999; self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)
        self.assertIsNone(self.db.get(SessaoAssistencial,sid).registro_longitudinal_id)

    def test_missing_ancestry(self):
        session=self.observation_session(); session.agenda_cuidado_id=999; self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)

    def test_unassigned_safe_read_transition_but_no_attendance(self):
        session=self.observation_session()
        pts=self.db.get(PTS,session.agenda_cuidado.pts_id); pts.modulo_id=None; self.db.commit()
        self.assertIsNone(self.boundary.context(self.db,session.id,self.user)[2])
        with self.assertRaises(HTTPException): self.attend(session)
        result=self.boundary.transition(self.db,session.id,self.user,'finalizar')
        self.assertEqual(result['status'],'REALIZADA')
        self.assertIsNone(pts.modulo_id)

    def test_inactive_current_link_and_closed_pts_preserve_identity(self):
        session=self.observation_session()
        self.db.query(PacienteModulo).filter_by(paciente_id=10).one().ativo=False
        self.db.get(PTS,session.agenda_cuidado.pts_id).status='ENCERRADO'; self.db.commit()
        self.attend(session)
        self.assertEqual(session.status,'EM_ANDAMENTO')

    def test_form_missing_inactive_type_and_duplicate(self):
        session=self.observation_session()
        form=self.db.get(FormularioModulo,105)
        for column,value in (('ativo',False),('tipo','OTHER'),('codigo','OTHER')):
            old=getattr(form,column); setattr(form,column,value); self.db.commit()
            with self.assertRaises(HTTPException): self.attend(session)
            setattr(form,column,old); self.db.commit()
        self.db.add(FormularioModulo(modulo_id=1,nome='Duplicate',codigo='ATENDIMENTO_SESSAO',tipo='LONGITUDINAL',ativo=True))
        self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)
        self.assertEqual(self.db.query(RegistroLongitudinal).count(),0)

    def test_payload_and_field_configuration(self):
        session=self.observation_session()
        with self.assertRaises(HTTPException): self.attend(session,narrativa='  ')
        field=self.db.get(CampoFormulario,1051); field.ativo=False; self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)
        field.ativo=True
        self.db.add(CampoFormulario(formulario_id=105,nome_campo='narrativa_atendimento',label='dup',tipo_campo='textarea',ativo=True)); self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)

    def test_legacy_evolution_realizada_and_context_validation(self):
        session=self.observation_session(); session.status='REALIZADA'; self.db.commit()
        for values in ({'paciente_id':20},{'modulo_id':2},{'formulario_id':206},{'origem':'SISTEMA'},
                       {'respostas':[{'campo_id':2060,'valor':'wrong'}]}):
            with self.assertRaises(HTTPException): self.boundary.attend(self.db,session.id,self.user,self.legacy(session,**values),legacy=True)
        result=self.boundary.attend(self.db,session.id,self.user,self.legacy(session),legacy=True)
        self.assertEqual(result['data_registro'],DAY)
        self.assertEqual(result['respostas'],{'narrativa_atendimento':'Synthetic'})
        self.assertEqual(session.status,'REALIZADA')

    def test_state_machine_finalize_without_attendance_and_no_regeneration(self):
        session=self.observation_session(); session.status='AGENDADA'; self.db.commit()
        for action,status in (('confirmar','CONFIRMADA'),('iniciar','EM_ANDAMENTO'),('finalizar','REALIZADA')):
            result=self.boundary.transition(self.db,session.id,self.user,action)
            self.assertEqual(result['status'],status)
        self.assertIsNone(session.registro_longitudinal_id)
        with self.assertRaises(HTTPException): self.boundary.transition(self.db,session.id,self.user,'reagendar')
        with self.assertRaises(HTTPException): self.attend(session)
        self.assertEqual(self.db.query(SessaoAssistencial).count(),1)

    def test_reagendar_preserves_dates_and_does_not_create_successor(self):
        session=self.observation_session(); session.status='AGENDADA'; self.db.commit()
        result=self.boundary.transition(self.db,session.id,self.user,'reagendar','Synthetic')
        self.assertEqual((result['status'],result['data_agendada']),('REAGENDADA',DAY))
        self.assertEqual(result['motivo_reagendamento'],'Synthetic')
        self.assertEqual(self.db.query(SessaoAssistencial).count(),1)

    def test_missing_or_incompatible_link_rejected(self):
        session=self.observation_session(); session.registro_longitudinal_id=999; self.db.commit()
        with self.assertRaises(HTTPException): self.attend(session)
        session.registro_longitudinal_id=None; self.db.commit()
        result=self.attend(session)
        self.db.get(RegistroLongitudinal,result['registro_id']).modulo_id=2; self.db.commit()
        with self.assertRaises(HTTPException): self.boundary.transition(self.db,session.id,self.user,'finalizar')

    def test_generic_patch_blocks_all_canonical_mutations_and_keeps_unrelated(self):
        from app.routers.registros_longitudinais import atualizar_registro
        from app.schemas.registros_longitudinais import RegistroLongitudinalUpdate
        session=self.observation_session(); rid=self.attend(session)['registro_id']
        original=self.legacy(session).model_dump()
        for changes in ({'paciente_id':20},{'modulo_id':2},{'formulario_id':206},
                        {'respostas':[{'campo_id':1050,'valor':'replacement'}]}):
            values={**original,**changes}
            with self.assertRaises(HTTPException) as cm: atualizar_registro(rid,RegistroLongitudinalUpdate(**values),self.db,self.user)
            self.assertEqual(cm.exception.status_code,409)
            self.db.rollback()
        unrelated=RegistroLongitudinal(paciente_id=10,modulo_id=1,formulario_id=105,origem='PROFISSIONAL',data_registro=DAY)
        self.db.add(unrelated); self.db.commit()
        result=atualizar_registro(unrelated.id,RegistroLongitudinalUpdate(**original),self.db,self.user)
        self.assertEqual(result['respostas']['narrativa_atendimento'],'Synthetic')

    def test_third_line_registration_and_form_only_no_core_branch(self):
        from dataclasses import replace
        from app.services.care_lines import NEURO, CARDIO, CareLineRegistry, CareLineResolver
        from app.services.care_plan_service import CarePlanService
        from app.services.session_service import SessionService
        from app.models import AtividadeTerapeutica, AtividadeOcupacao
        self.observation_session()
        self.db.add(ModuloClinico(id=9,nome='Synthetic',slug='synthetic',ativo=True))
        self.db.add(PacienteModulo(paciente_id=10,modulo_id=9,ativo=True))
        self.db.add(AtividadeTerapeutica(id=9,nome='Synthetic',modulo_id=9,ativo=True))
        self.db.add(AtividadeOcupacao(atividade_id=9,ocupacao_id=1))
        self.db.add(FormularioModulo(id=909,modulo_id=9,nome='Synthetic',codigo='ATENDIMENTO_SESSAO',tipo='LONGITUDINAL',ativo=True))
        self.db.add(CampoFormulario(id=9090,formulario_id=909,nome_campo='narrativa_atendimento',label='Synthetic',tipo_campo='textarea',obrigatorio=True,ativo=True))
        self.db.commit()
        registry=CareLineRegistry([NEURO,CARDIO,replace(NEURO,code='SYNTHETIC',slug='synthetic',module_id=9)])
        self.service=CarePlanService(CareLineResolver(registry))
        self.boundary=SessionService(self.service)
        pts=self.create(10,9)
        obj=self.service.create_objective(self.db,pts.id,fixtures.PTSObjetivoCreate(descricao='Synthetic'),self.user)
        agenda=self.service.create_agenda(self.db,fixtures.AgendaCuidadoCreate(pts_id=pts.id,objetivo_id=obj.id,
            atividade_id=9,ocupacao_id=1,profissional_id=70,frequencia_semanal=1,quantidade_sessoes=1,
            duracao_minutos=30,data_inicio=DAY),self.user)
        session=self.sessions(agenda)[0]
        self.boundary.transition(self.db,session.id,self.user,'confirmar')
        self.boundary.transition(self.db,session.id,self.user,'iniciar')
        result=self.attend(session,proximos_passos=[])
        self.assertEqual(self.db.get(RegistroLongitudinal,result['registro_id']).modulo_id,9)

    def test_patch_cannot_escape_by_switching_to_daily_form(self):
        from app.routers.registros_longitudinais import atualizar_registro
        from app.schemas.registros_longitudinais import RegistroLongitudinalUpdate
        session=self.observation_session(); rid=self.attend(session)['registro_id']
        self.db.add(FormularioModulo(id=777,modulo_id=1,nome='Synthetic daily',codigo='DAILY',tipo='REGISTRO_DIARIO',ativo=True)); self.db.commit()
        payload=RegistroLongitudinalUpdate(**{**self.legacy(session).model_dump(),'formulario_id':777})
        with patch('app.routers.registros_longitudinais.write_legacy_longitudinal') as daily:
            with self.assertRaises(HTTPException) as cm: atualizar_registro(rid,payload,self.db,self.user)
            self.assertEqual(cm.exception.status_code,409)
            daily.assert_not_called()



class HttpTests(SessionFixture):
    def request(self, method, path, payload=None, authenticated=True):
        import asyncio
        import json
        from fastapi import FastAPI
        from app.database import get_db
        from app.core.deps import get_usuario_atual
        from app.routers import sessoes_assistenciais
        app=FastAPI(); app.include_router(sessoes_assistenciais.router)
        app.dependency_overrides[get_db]=lambda:self.db
        if authenticated: app.dependency_overrides[get_usuario_atual]=lambda:self.user
        async def run():
            messages=[]
            async def receive():
                return {'type':'http.request','body':json.dumps(payload).encode(),'more_body':False}
            async def send(message): messages.append(message)
            await app({'type':'http','asgi':{'version':'3.0'},'http_version':'1.1','method':method,
                'scheme':'http','path':path,'raw_path':path.encode(),'query_string':b'',
                'headers':[(b'content-type',b'application/json')], 'client':('127.0.0.1',1),
                'server':('test',80),'root_path':''},receive,send)
            status=next(m['status'] for m in messages if m['type']=='http.response.start')
            body=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
            return status,json.loads(body)
        return asyncio.run(run())

    def operations(self, session):
        root='/sessoes-assistenciais/'+str(session.id)
        return [('GET','/sessoes-assistenciais/minhas',None),
            ('GET','/sessoes-assistenciais/paciente/10',None),('GET',root,None),
            ('POST',root+'/confirmar',None),('POST',root+'/iniciar',None),
            ('POST',root+'/finalizar',None),('POST',root+'/reagendar',{'motivo':'Synthetic'}),
            ('POST',root+'/registrar-atendimento',{'narrativa':'Synthetic','proximos_passos':['x']}),
            ('POST',root+'/registrar-evolucao',{'paciente_id':10,'modulo_id':1,'formulario_id':105,
                'data_registro':DAY.isoformat(),'origem':'PROFISSIONAL','respostas':[{'campo_id':1050,'valor':'Synthetic'}]})]

    def test_all_session_routes_require_authentication(self):
        session=self.observation_session()
        for method,path,payload in self.operations(session):
            status,body=self.request(method,path,payload,False)
            self.assertEqual(status,401,(path,body))

    def test_all_resource_routes_reject_other_clinic(self):
        session=self.observation_session()
        self.user.profissional_id=70; self.user.clinica_id=2
        for method,path,payload in self.operations(session):
            status,body=self.request(method,path,payload)
            self.assertEqual(status,403,(path,body))

    def test_same_clinic_http_attendance_finalize_and_read_shapes(self):
        from app.models import Intervencao, AvaliacaoClinica
        session=self.observation_session()
        for model in (Intervencao,AvaliacaoClinica): model.__table__.create(self.engine,checkfirst=True)
        self.user.profissional_id=70
        root='/sessoes-assistenciais/'+str(session.id)
        status,body=self.request('GET','/sessoes-assistenciais/minhas')
        self.assertEqual(status,200,body); self.assertEqual(body[0]['id'],session.id)
        status,body=self.request('GET','/sessoes-assistenciais/paciente/10')
        self.assertEqual(status,200,body)
        status,body=self.request('POST',root+'/registrar-atendimento',{'narrativa':'Synthetic','proximos_passos':['x']})
        self.assertEqual(status,200,body); self.assertTrue(body['success'])
        status,body=self.request('POST',root+'/finalizar')
        self.assertEqual(status,200,body); self.assertEqual(body['status'],'REALIZADA')
        status,body=self.request('GET',root)
        self.assertEqual(status,200,body)
        self.assertTrue({'sessao','paciente','objetivo','registro_longitudinal','resumo'} <= set(body))

    def test_legacy_http_realizada_and_duplicate(self):
        session=self.observation_session(); session.status='REALIZADA'; self.db.commit()
        method,path,payload=self.operations(session)[-1]
        status,body=self.request(method,path,payload)
        self.assertEqual(status,200,body); self.assertEqual(body['formulario_id'],105)
        status,body=self.request(method,path,payload)
        self.assertEqual(status,409,body)
