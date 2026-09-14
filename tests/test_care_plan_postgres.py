"""Opt-in PostgreSQL tests. Creates/drops only a UUID-named synthetic schema.

Run against a disposable PostgreSQL container, never an application database.
"""
import os
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi import HTTPException
from test_care_plan import seed, DAY
from app.database import Base
from app.models import PTS, Paciente, PTSObjetivo, AgendaCuidado
from app.schemas.pts import PTSCreate
from app.services.care_plan_service import CarePlanService
from app.services.scheduling_service import SchedulingService

URL = os.environ.get('CARE_PLAN_TEST_POSTGRES_URL')


@unittest.skipUnless(URL, 'Requires disposable PostgreSQL via CARE_PLAN_TEST_POSTGRES_URL')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        self.schema='care_plan_test_'+uuid.uuid4().hex
        self.admin=create_engine(URL)
        with self.admin.begin() as conn:
            conn.execute(text('CREATE SCHEMA '+self.schema))
        self.engine=create_engine(URL,connect_args={'options':'-c search_path='+self.schema},
                                  isolation_level='READ COMMITTED')
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db: seed(db)
        self.user=SimpleNamespace(id=50,perfil='PROFISSIONAL',clinica_id=1)

    def tearDown(self):
        self.engine.dispose()
        with self.admin.begin() as conn:
            conn.execute(text('DROP SCHEMA '+self.schema+' CASCADE'))
        self.admin.dispose()

    def race(self, operations):
        barrier=threading.Barrier(len(operations))
        def worker(operation):
            with Session(self.engine,autoflush=False) as db:
                barrier.wait(timeout=10)
                try:
                    operation(CarePlanService(),db)
                    return 'ok'
                except HTTPException as exc:
                    return exc.status_code
        with ThreadPoolExecutor(max_workers=len(operations)) as pool:
            results=list(pool.map(worker,operations))
        self.assertEqual(sorted(map(str,results)),['400','ok'])
        with Session(self.engine) as db:
            self.assertEqual(db.query(PTS).filter_by(paciente_id=10,modulo_id=1,status='ATIVO').count(),1)

    def test_concurrent_create(self):
        def create(service,db):
            service.create(db,PTSCreate(paciente_id=10,modulo_id=1,data_inicio=DAY),self.user)
        self.race([create,create])

    def test_concurrent_reopen(self):
        with Session(self.engine) as db:
            rows=[PTS(paciente_id=10,modulo_id=1,data_inicio=DAY,status='ENCERRADO') for _ in range(2)]
            db.add_all(rows); db.commit(); ids=[r.id for r in rows]
        self.race([lambda s,d:s.set_closed(d,ids[0],self.user,False),
                   lambda s,d:s.set_closed(d,ids[1],self.user,False)])

    def test_create_against_reopen(self):
        with Session(self.engine) as db:
            row=PTS(paciente_id=10,modulo_id=1,data_inicio=DAY,status='ENCERRADO')
            db.add(row); db.commit(); identity=row.id
        self.race([lambda s,d:s.create(d,PTSCreate(paciente_id=10,modulo_id=1,data_inicio=DAY),self.user),
                   lambda s,d:s.set_closed(d,identity,self.user,False)])

    def test_lock_blocks_until_holder_commits(self):
        started=threading.Event()
        with Session(self.engine) as holder:
            holder.query(Paciente).filter_by(id=10).with_for_update().one()
            def create():
                with Session(self.engine) as db:
                    started.set()
                    CarePlanService().create(db,PTSCreate(paciente_id=10,modulo_id=1,data_inicio=DAY),self.user)
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(create)
                self.assertTrue(started.wait(5))
                # Observe the actual PostgreSQL waiter, not elapsed-time assumptions.
                import time
                waiting=False
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    with self.admin.connect() as conn:
                        waiting=bool(conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE wait_event_type='Lock' AND query LIKE '%pacientes%FOR UPDATE%'")).scalar())
                    if waiting: break
                    time.sleep(.02)
                self.assertTrue(waiting)
                self.assertFalse(future.done())
                holder.commit()
                future.result(timeout=5)

    def test_agenda_lock_prevents_delete_racing_confirmation(self):
        service=CarePlanService()
        with Session(self.engine) as db:
            pts=service.create(db,PTSCreate(paciente_id=10,modulo_id=1,data_inicio=DAY),self.user)
            obj=PTSObjetivo(pts_id=pts.id,descricao='Synthetic'); db.add(obj); db.flush()
            agenda=AgendaCuidado(pts_id=pts.id,objetivo_id=obj.id,atividade_id=1,ocupacao_id=1,
                profissional_id=70,frequencia_semanal=1,duracao_minutos=30,quantidade_sessoes=1,data_inicio=DAY)
            db.add(agenda); db.commit(); identity=agenda.id
        with Session(self.engine) as holder:
            agenda=service.scheduling_agenda(holder,identity,self.user)
            def delete():
                with Session(self.engine) as db:
                    try: service.delete_agenda(db,identity,self.user)
                    except HTTPException as exc: return exc.status_code
            with ThreadPoolExecutor(max_workers=1) as pool:
                future=pool.submit(delete)
                SchedulingService.confirmar_cronograma(holder,agenda,[SimpleNamespace(numero=1,data=DAY)])
                self.assertEqual(future.result(timeout=5),409)
        with Session(self.engine) as db:
            self.assertIsNotNone(db.get(AgendaCuidado,identity))
