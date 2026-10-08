import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from sqlalchemy import text
from sqlalchemy.orm import Session
import test_planejamento_mental as base


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class MentalSessionTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(base.PlanningTests.setUpClass.__func__)
    tearDownClass=classmethod(base.PlanningTests.tearDownClass.__func__)
    tearDown=base.PlanningTests.tearDown
    command_grant=base.PlanningTests.command_grant
    path=base.PlanningTests.path
    request=base.PlanningTests.request
    create=base.PlanningTests.create

    def setUp(self):
        base.PlanningTests.setUp(self)
        self.payload.update(data_inicio='2026-11-01', data_fim='2027-04-30')
        r=self.request('POST',self.suffix,self.payload)
        self.assertEqual(r.status_code,201,r.text)
        self.planning=r.json()['id']
        self.schedule=f'{self.suffix}/{self.planning}/cronograma'
        self.scope=dict(actor=self.actor,institution=self.institutions[0],person=self.person,context=self.open)

    def generate(self):
        r=self.request('POST',self.schedule)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()

    def action(self,session,action):
        return self.request('POST',f'{self.suffix}/{self.planning}/sessoes/{session}/estado',dict(acao=action))

    def test_generate_52_persist_idempotent_and_protected(self):
        r=self.request('GET',self.schedule);self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(len(r.json()['proposta']),52)
        self.assertEqual(r.json()['quantidade_materializada'],0)
        a=self.generate();b=self.generate()
        self.assertEqual(a['sessoes'],b['sessoes']);self.assertEqual(a['quantidade_materializada'],52)
        self.assertEqual((a['pessoa_id'],a['contexto_assistencial_id'],a['pts_id'],a['objetivo_id']),(self.person,self.open,self.plan,self.objective))
        for i,s in enumerate(a['sessoes'],1):
            self.assertEqual((s['numero_sessao'],s['profissional_id'],s['duracao_minutos'],s['status']),(i,self.executor,50,'AGENDADA'))
            self.assertLessEqual(s['data_agendada'],'2027-04-30');self.assertIsNone(s['hora_inicio']);self.assertIsNone(s['registro_longitudinal_id'])
        self.assertEqual(self.request('PUT',f'{self.suffix}/{self.planning}',self.payload).status_code,409)
        with patch.object(self.db,'commit',side_effect=AssertionError('GET commit')):
            self.assertEqual(self.request('GET',self.schedule).json()['quantidade_materializada'],52)

    def test_realization_one_longitudinal_record_and_timeline(self):
        before=self.client.get(self.path()).json()
        s=self.generate()['sessoes'][0]['id']
        self.assertEqual(self.action(s,'finalizar').status_code,422)
        self.assertEqual(self.action(s,'confirmar').status_code,200)
        self.assertEqual(self.action(s,'iniciar').status_code,200)
        self.assertEqual(self.action(s,'finalizar').status_code,422)
        endpoint=f'{self.suffix}/{self.planning}/sessoes/{s}/atendimento'
        self.assertEqual(self.request('POST',endpoint,dict(narrativa=' ')).status_code,422)
        r=self.request('POST',endpoint,dict(narrativa='Atendimento sintético',proximos_passos=['Acompanhar']))
        self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.request('POST',endpoint,dict(narrativa='Duplicado')).status_code,409)
        self.assertEqual(self.action(s,'finalizar').status_code,200)
        journey=self.client.get(self.path()).json()
        self.assertEqual(len(journey['sessoes']),1)
        result=journey['sessoes'][0]
        self.assertEqual((result['status'],result['narrativa'],result['autor_usuario_id']),('REALIZADA','Atendimento sintético',self.actor))
        row=self.db.execute(text('SELECT contexto_assistencial_id,modulo_id,criado_por_usuario_id FROM registros_longitudinais WHERE id=:r'),dict(r=result['registro_longitudinal_id'])).one()
        self.assertEqual(tuple(row),(self.open,3,self.actor))
        self.assertEqual(journey['bem_estar'],before['bem_estar']);self.assertEqual(journey['intervencoes'],before['intervencoes'])
        self.assertEqual(journey['clinical_reading'],before['clinical_reading'])

    def test_wrong_scope_and_ancestry(self):
        for scope in [dict(person=self.person+999),dict(context=self.contexts[1]),dict(institution=self.institutions[1])]:
            self.assertEqual(self.request('GET',self.schedule,**scope).status_code,404)
            self.assertEqual(self.request('POST',self.schedule,**scope).status_code,403)
        self.assertEqual(self.request('POST',self.schedule.replace(f'/{self.objective}/planejamentos','/999999/planejamentos')).status_code,403)
        s=self.generate()['sessoes'][0]['id']
        self.assertEqual(self.action(s+99999,'confirmar').status_code,403)
        from app.services.session_service import SessionService
        from types import SimpleNamespace
        from fastapi import HTTPException
        with self.assertRaises(HTTPException):SessionService().context(self.db,s,SimpleNamespace(perfil='ADMIN'))

    def test_no_grant_no_admin_bypass(self):
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),dict(id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']));self.db.commit()
        self.assertEqual(self.request('GET',self.schedule).status_code,200)
        self.assertEqual(self.request('POST',self.schedule).status_code,403)
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:id"),dict(id=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),dict(id=self.grant_ids[self.open,'ASSISTENCIAL_LER']));self.db.commit()
        self.assertEqual(self.request('POST',self.schedule).status_code,403)
        self.assertEqual(self.request('GET',self.schedule).status_code,404)

    def test_concurrent_generation_exactly_52(self):
        from app.services.sessoes_mentais import SessoesMentaisService
        barrier=Barrier(2);self.db.commit()
        def worker(_):
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                result=SessoesMentaisService().generate(db,self.scope,self.plan,self.objective,self.planning)
                db.commit();return result.quantidade_materializada
        with ThreadPoolExecutor(2) as pool:self.assertEqual(list(pool.map(worker,range(2))),[52,52])
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM sessoes_assistenciais WHERE agenda_cuidado_id=:a'),dict(a=self.planning)),52)

    def test_concurrent_attendance_creates_one_record(self):
        from app.services.sessoes_mentais import SessoesMentaisService
        from app.schemas.sessoes_mentais import AtendimentoMental
        from app.services.pts_mental import PTSConflict
        identity=self.generate()['sessoes'][0]['id']
        self.assertEqual(self.action(identity,'confirmar').status_code,200)
        self.assertEqual(self.action(identity,'iniciar').status_code,200)
        barrier=Barrier(2)
        def worker(_):
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                try:
                    SessoesMentaisService().mutate(db,self.scope,self.plan,self.objective,self.planning,identity,attendance=AtendimentoMental(narrativa='Synthetic attendance'))
                    db.commit();return 'SAVED'
                except PTSConflict:
                    db.rollback();return 'CONFLICT'
        with ThreadPoolExecutor(2) as pool:self.assertCountEqual(list(pool.map(worker,range(2))),['SAVED','CONFLICT'])
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM registros_longitudinais WHERE contexto_assistencial_id=:c'),dict(c=self.open)),1)

    def test_executor_rechecked_and_rollback(self):
        self.db.execute(text('UPDATE profissional_instituicoes SET ativo=false WHERE id=:id'),dict(id=self.links[0]))
        self.assertIn(self.request('POST',self.schedule).status_code,(403,422))
        self.db.rollback()
        from app.services.scheduling_service import SchedulingService
        original=SchedulingService.confirmar_cronograma
        def fail(*a,**kw):original(*a,**kw);raise RuntimeError('synthetic')
        with patch.object(SchedulingService,'confirmar_cronograma',side_effect=fail):
            self.assertEqual(self.request('POST',self.schedule).status_code,500)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM sessoes_assistenciais WHERE agenda_cuidado_id=:a'),dict(a=self.planning)),0)


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class AttendanceCatalogueTests(unittest.TestCase):
    from test_saude_mental import CatalogueMigrationTests as Foundation
    setUp=Foundation.setUp
    tearDown=Foundation.tearDown

    def test_catalogue_roundtrip_and_record_guard(self):
        from alembic import command
        from test_m0_baseline import config
        with self.engine.begin() as c:
            command.upgrade(config(c),'head')
            form=c.exec_driver_sql("SELECT id FROM formularios_modulo WHERE modulo_id=3 AND codigo='ATENDIMENTO_SESSAO' AND ativo AND tipo='LONGITUDINAL'").scalar_one()
            self.assertEqual(c.execute(text('SELECT nome_campo,obrigatorio FROM campos_formulario WHERE formulario_id=:f ORDER BY ordem'),dict(f=form)).all(),[('narrativa_atendimento',True),('proximos_passos',False)])
            command.downgrade(config(c),'w3_atividade_linhas_v1')
            command.upgrade(config(c),'head')
            form=c.exec_driver_sql("SELECT id FROM formularios_modulo WHERE modulo_id=3 AND codigo='ATENDIMENTO_SESSAO'").scalar_one()
            patient=c.exec_driver_sql("INSERT INTO pacientes(nome) VALUES ('Synthetic') RETURNING id").scalar_one()
            c.execute(text("INSERT INTO registros_longitudinais(paciente_id,modulo_id,formulario_id,origem,data_registro) VALUES(:p,3,:f,'PROFISSIONAL',CURRENT_DATE)"),dict(p=patient,f=form))
        with self.assertRaisesRegex(RuntimeError,'MENTAL_ATTENDANCE_RECORDS_PRESENT'):
            with self.engine.begin() as c:command.downgrade(config(c),'w3_atividade_linhas_v1')


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL required')
class OperationalSessionTests(unittest.TestCase):
    schema_revision='head'
    setUpClass=classmethod(MentalSessionTests.setUpClass.__func__)
    tearDownClass=classmethod(MentalSessionTests.tearDownClass.__func__)
    tearDown=MentalSessionTests.tearDown
    command_grant=MentalSessionTests.command_grant
    path=MentalSessionTests.path
    request=MentalSessionTests.request
    create=MentalSessionTests.create
    generate=MentalSessionTests.generate

    def setUp(self):
        MentalSessionTests.setUp(self)
        from app.routers.sessoes_assistenciais import router
        self.app.include_router(router)

    def reviewed(self):
        proposal=self.request('GET',self.schedule).json()['proposta']
        return dict(cronograma=[dict(numero=s['numero'],data=s['data'],hora_inicio='09:00',hora_fim='09:50') for s in proposal])

    def shared(self, method, path, payload=None):
        import json
        return self.client.request(method,'/sessoes-assistenciais'+path,
            body=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})

    def test_review_confirm_agenda_session_attendance_timeline(self):
        payload=self.reviewed()
        payload['cronograma'][0]['hora_inicio']='10:00';payload['cronograma'][0]['hora_fim']='10:50'
        result=self.request('POST',self.schedule,payload)
        self.assertEqual(result.status_code,200,result.text)
        identity=result.json()['sessoes'][0]['id']
        self.assertEqual(result.json()['sessoes'][0]['hora_inicio'],'10:00:00')
        self.assertEqual(self.request('POST',self.schedule,payload).json(),result.json())
        with patch.object(self.db,'commit',side_effect=AssertionError('GET committed')):
            agenda=self.shared('GET','/minhas');self.assertEqual(agenda.status_code,200,agenda.text)
            self.assertIn(identity,[s['id'] for s in agenda.json()])
            detail=self.shared('GET',f'/{identity}');self.assertEqual(detail.status_code,200,detail.text)
        self.assertEqual(detail.json()['pessoa']['id'],self.person)
        self.assertEqual(detail.json()['contexto']['id'],self.open)
        self.assertIsNone(detail.json()['paciente'])
        for action in ('confirmar','iniciar'):
            response=self.shared('POST',f'/{identity}/{action}');self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.shared('POST',f'/{identity}/finalizar').status_code,422)
        response=self.shared('POST',f'/{identity}/registrar-atendimento',dict(narrativa='Atendimento contextual revisado',proximos_passos=['Acompanhar']))
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.shared('POST',f'/{identity}/registrar-atendimento',dict(narrativa='Duplicado')).status_code,409)
        self.assertEqual(self.shared('POST',f'/{identity}/finalizar').status_code,200)
        refreshed=self.shared('GET',f'/{identity}').json()
        self.assertEqual(refreshed['sessao']['status'],'REALIZADA')
        self.assertEqual(refreshed['autor_usuario_id'],self.actor)
        self.assertEqual(len(self.client.get(self.path()).json()['sessoes']),1)

    def test_invalid_review_no_writes_and_conflicting_replay(self):
        for change in (dict(hora_fim='09:10'),dict(hora_inicio=''),dict(data='2020-01-01')):
            payload=self.reviewed();payload['cronograma'][0].update(change)
            self.assertEqual(self.request('POST',self.schedule,payload).status_code,422)
        payload=self.reviewed();payload['cronograma'].pop()
        self.assertEqual(self.request('POST',self.schedule,payload).status_code,422)
        self.assertEqual(self.db.scalar(text('SELECT count(*) FROM sessoes_assistenciais WHERE agenda_cuidado_id=:a'),dict(a=self.planning)),0)
        payload=self.reviewed();self.assertEqual(self.request('POST',self.schedule,payload).status_code,200)
        payload['cronograma'][0].update(hora_inicio='10:00',hora_fim='10:50')
        self.assertEqual(self.request('POST',self.schedule,payload).status_code,409)

    def test_assignment_and_admin_do_not_bypass_w1b(self):
        identity=self.generate()['sessoes'][0]['id']
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),dict(id=self.grant_ids[self.open,'ASSISTENCIAL_REGISTRAR']));self.db.commit()
        self.assertEqual(self.shared('GET',f'/{identity}').json()['pode_registrar'],False)
        self.assertEqual(self.shared('POST',f'/{identity}/confirmar').status_code,403)
        self.db.execute(text("UPDATE usuarios SET perfil='ADMIN' WHERE id=:id"),dict(id=self.actor))
        self.db.execute(text('DELETE FROM concessoes_assistenciais WHERE id=:id'),dict(id=self.grant_ids[self.open,'ASSISTENCIAL_LER']));self.db.commit()
        self.assertEqual(self.shared('GET','/minhas').json(),[])
        self.assertEqual(self.shared('GET',f'/{identity}').status_code,404)
        self.assertEqual(self.shared('POST',f'/{identity}/iniciar').status_code,403)

    def test_personal_agenda_requires_assignment_and_active_line(self):
        identity=self.generate()['sessoes'][0]['id']
        self.assertIn(identity,[s['id'] for s in self.shared('GET','/minhas').json()])
        self.db.execute(text('UPDATE contexto_assistencial_linhas SET ativo=false WHERE contexto_assistencial_id=:c AND modulo_id=3'),dict(c=self.open));self.db.commit()
        self.assertEqual(self.shared('GET','/minhas').json(),[])
        self.assertEqual(self.shared('GET',f'/{identity}').status_code,404)

    def test_concurrent_reviewed_confirmation_preserves_times(self):
        from app.services.sessoes_mentais import SessoesMentaisService
        from app.schemas.sessoes_mentais import ConfirmarCronogramaMental
        payload=ConfirmarCronogramaMental(**self.reviewed())
        barrier=Barrier(2);self.db.commit()
        def worker(_):
            with Session(self.engine) as db:
                barrier.wait(timeout=10)
                result=SessoesMentaisService().generate(db,self.scope,self.plan,self.objective,self.planning,payload.cronograma)
                db.commit();return [(s.id,str(s.hora_inicio),str(s.hora_fim)) for s in result.sessoes]
        with ThreadPoolExecutor(2) as pool:
            first,second=list(pool.map(worker,range(2)))
        self.assertEqual(first,second);self.assertEqual(len(first),52)
        self.assertEqual(first[0][1:],('09:00:00','09:50:00'))
