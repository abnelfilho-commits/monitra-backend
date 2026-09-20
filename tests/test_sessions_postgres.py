"""Opt-in transactions in UUID schemas on a disposable PostgreSQL instance."""
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
import test_care_plan as fixtures
from app.database import Base
from app.models import (PTS,PTSObjetivo,AgendaCuidado,SessaoAssistencial,
    FormularioModulo,CampoFormulario,RegistroLongitudinal,RespostaRegistro)
from app.services.session_service import SessionService
from app.schemas.assistential_session import RegistrarAtendimentoRequest

URL=os.environ.get('SESSION_TEST_POSTGRES_URL')


@unittest.skipUnless(URL,'Requires disposable PostgreSQL via SESSION_TEST_POSTGRES_URL')
class SessionPostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema='session_test_'+uuid.uuid4().hex
        self.admin=create_engine(URL)
        with self.admin.begin() as conn: conn.execute(text('CREATE SCHEMA '+self.schema))
        self.engine=create_engine(URL,connect_args={'options':'-c search_path='+self.schema},isolation_level='READ COMMITTED')
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            fixtures.seed(db)
            pts=PTS(paciente_id=10,modulo_id=1,data_inicio=fixtures.DAY); db.add(pts); db.flush()
            obj=PTSObjetivo(pts_id=pts.id,descricao='Synthetic'); db.add(obj); db.flush()
            agenda=AgendaCuidado(pts_id=pts.id,objetivo_id=obj.id,atividade_id=1,ocupacao_id=1,profissional_id=70,
                frequencia_semanal=1,quantidade_sessoes=1,duracao_minutos=30,data_inicio=fixtures.DAY)
            db.add(agenda); db.flush()
            session=SessaoAssistencial(agenda_cuidado_id=agenda.id,paciente_id=10,profissional_id=70,
                numero_sessao=1,data_agendada=fixtures.DAY,duracao_minutos=30,status='EM_ANDAMENTO')
            db.add(session)
            db.add(FormularioModulo(id=105,modulo_id=1,nome='Synthetic',codigo='ATENDIMENTO_SESSAO',tipo='LONGITUDINAL',ativo=True))
            db.flush()
            db.add(CampoFormulario(id=1050,formulario_id=105,nome_campo='narrativa_atendimento',label='Synthetic',
                tipo_campo='textarea',obrigatorio=True,ativo=True))
            db.commit(); self.identity=session.id
        self.user=SimpleNamespace(id=50,perfil='PROFISSIONAL',clinica_id=1,profissional_id=73)
        self.payload=RegistrarAtendimentoRequest(narrativa='Synthetic',proximos_passos=[])

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as conn: conn.execute(text('DROP SCHEMA '+self.schema+' CASCADE'))
        self.admin.dispose()

    def race(self, actions):
        barrier=threading.Barrier(2)
        def run(action):
            with Session(self.engine,autoflush=False) as db:
                barrier.wait(timeout=5)
                try:
                    if action=='attend': SessionService().attend(db,self.identity,self.user,self.payload)
                    else: SessionService().transition(db,self.identity,self.user,'finalizar')
                    return action,200
                except HTTPException as exc: return action,exc.status_code
        with ThreadPoolExecutor(max_workers=2) as pool: return list(pool.map(run,actions))

    def test_two_attendances_one_record(self):
        results=self.race(['attend','attend'])
        self.assertEqual(sorted(status for _,status in results),[200,409])
        with Session(self.engine) as db:
            self.assertEqual(db.query(RegistroLongitudinal).count(),1)
            self.assertEqual(db.query(RespostaRegistro).count(),1)
            session=db.get(SessaoAssistencial,self.identity)
            record=db.get(RegistroLongitudinal,session.registro_longitudinal_id)
            self.assertEqual(record.criado_por_usuario_id,50)
            self.assertEqual(session.status,'EM_ANDAMENTO')

    def test_attendance_racing_finalize(self):
        results=dict(self.race(['attend','finalize']))
        self.assertEqual(results['finalize'],200)
        self.assertIn(results['attend'],(200,422))
        with Session(self.engine) as db:
            session=db.get(SessaoAssistencial,self.identity)
            self.assertEqual(session.status,'REALIZADA')
            expected=1 if results['attend']==200 else 0
            self.assertEqual(db.query(RegistroLongitudinal).count(),expected)
            self.assertEqual(session.registro_longitudinal_id is not None,bool(expected))

    def test_postgres_rollback_after_responses_and_before_commit(self):
        for checkpoint in (1,2,3,'commit'):
            with Session(self.engine,autoflush=False) as db:
                original=db.flush; count=[0]
                def flush(*args,**kwargs):
                    result=original(*args,**kwargs); count[0]+=1
                    if count[0]==checkpoint: raise RuntimeError('synthetic')
                    return result
                with patch.object(db,'flush',side_effect=flush), patch.object(db,'commit',
                        side_effect=RuntimeError('synthetic') if checkpoint=='commit' else db.commit):
                    with self.assertRaises(RuntimeError): SessionService().attend(db,self.identity,self.user,self.payload)
            with Session(self.engine) as check:
                self.assertEqual(check.query(RegistroLongitudinal).count(),0)
                self.assertEqual(check.query(RespostaRegistro).count(),0)
                self.assertIsNone(check.get(SessaoAssistencial,self.identity).registro_longitudinal_id)

    def test_session_lock_is_held_through_attendance_commit(self):
        import time
        started=threading.Event()
        holder=Session(self.engine)
        holder.query(SessaoAssistencial).filter_by(id=self.identity).with_for_update().one()
        def worker():
            with Session(self.engine) as db:
                started.set()
                SessionService().attend(db,self.identity,self.user,self.payload)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(worker)
            try:
                self.assertTrue(started.wait(5))
                waiting=False; deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    with self.admin.connect() as conn:
                        waiting=bool(conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%sessoes_assistenciais%'")).scalar())
                    if waiting: break
                    time.sleep(.02)
                self.assertTrue(waiting)
                self.assertFalse(future.done())
            finally:
                holder.rollback(); holder.close()
            future.result(timeout=5)
