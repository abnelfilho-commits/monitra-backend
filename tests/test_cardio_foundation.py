"""Synthetic patient membership and diagnosis authorization regression."""
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import unittest
from datetime import date
from types import SimpleNamespace
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.models import (Clinica, Paciente, Profissional, ProfissionalModulo, Usuario,
                        ModuloClinico, PacienteModulo, Diagnostico, OcupacaoProfissional)
from app.services.patient_line_service import list_patients, link_patient
from app.services.care_lines.access import authorized_patient
from app.routers.diagnosticos import criar_diagnostico, listar_diagnosticos_paciente, scoped_record
from app.schemas.diagnostico import DiagnosticoCreate


class FoundationTests(unittest.TestCase):
    def setUp(self):
        from sqlalchemy.pool import StaticPool
        self.engine = create_engine('sqlite:///:memory:', poolclass=StaticPool, connect_args={'check_same_thread': False})
        for model in (Clinica, OcupacaoProfissional, Profissional, Usuario, Paciente,
                      ModuloClinico, PacienteModulo, ProfissionalModulo, Diagnostico):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([Clinica(id=i, nome='Synthetic') for i in (1, 2)])
        self.db.add(Profissional(id=1, nome='Synthetic', clinica_id=1, ativo=True))
        self.db.add_all([ModuloClinico(id=i, nome=str(i), slug=str(i), ativo=True) for i in (1, 2)])
        self.db.add_all([Paciente(id=i, nome=str(i), clinica_id=1 if i != 4 else 2, ativo=True)
                         for i in (1, 2, 3, 4)])
        for pid, mid in ((1,1), (2,2), (3,1), (3,2), (4,2)):
            self.db.add(PacienteModulo(paciente_id=pid, modulo_id=mid, ativo=True))
        self.db.add_all([ProfissionalModulo(profissional_id=1, modulo_id=i) for i in (1,2)])
        self.db.commit()
        self.user = SimpleNamespace(id=1, perfil='PROFISSIONAL', profissional_id=1, clinica_id=1)

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def test_membership_without_clinical_records(self):
        self.assertEqual([p.id for p in list_patients(self.db,self.user,'NEURO')], [1,3])
        self.assertEqual([p.id for p in list_patients(self.db,self.user,'CARDIO')], [2,3])

    def test_patient_creation_is_atomic_and_clinic_is_server_scoped(self):
        from app.routers.pacientes import criar_paciente
        from app.schemas.paciente import PacienteCreate
        result = criar_paciente(PacienteCreate(nome='New synthetic',data_nascimento=date(2000,1,1),modulo_id=2,clinica_id=2),
                                self.db,self.user)
        self.assertEqual(result['clinica_id'],1)
        self.assertEqual(self.db.query(PacienteModulo).filter_by(
            paciente_id=result['id'],modulo_id=2,ativo=True).count(),1)

    def test_idempotent_second_line_keeps_patient_identity(self):
        first = link_patient(self.db,self.user,1,'CARDIO')
        self.assertEqual(first, link_patient(self.db,self.user,1,'CARDIO'))
        self.assertEqual(self.db.query(Paciente).count(),4)
        self.assertEqual(self.db.query(PacienteModulo).filter_by(paciente_id=1,modulo_id=2).count(),1)

    def test_clinic_and_professional_scope(self):
        with self.assertRaises(HTTPException):
            link_patient(self.db,self.user,4,'CARDIO')
        self.db.query(ProfissionalModulo).filter_by(modulo_id=2).delete()
        self.db.commit()
        with self.assertRaises(HTTPException):
            list_patients(self.db,self.user,'CARDIO')

    def test_inactive_membership_and_patient(self):
        self.db.query(PacienteModulo).filter_by(paciente_id=2).update({'ativo':False})
        self.db.query(Paciente).filter_by(id=3).update({'ativo':False})
        self.db.commit()
        self.assertEqual(list_patients(self.db,self.user,'CARDIO'),[])

    def test_diagnoses_are_line_scoped_and_legacy_not_inferred(self):
        records = []
        for line in ('NEURO','CARDIO'):
            payload = DiagnosticoCreate(paciente_id=3,care_line=line,descricao_clinica='Synthetic',
                                        data_diagnostico=date(2026,1,1),medico_nome='Synthetic')
            records.append(criar_diagnostico(payload,self.db,self.user))
        legacy = Diagnostico(paciente_id=3,descricao_clinica='Legacy',
                            data_diagnostico=date(2020,1,1),medico_nome='Synthetic')
        from sqlalchemy.exc import IntegrityError
        with self.assertRaises(IntegrityError):
            self.db.add(legacy);self.db.commit()
        self.db.rollback()
        self.assertEqual([r.modulo_id for r in records],[1,2])
        self.assertEqual([r.id for r in listar_diagnosticos_paciente(3,'CARDIO',self.db,self.user)],
                         [records[1].id])
        for identity in (records[0].id,):
            with self.assertRaises(HTTPException):
                scoped_record(self.db,self.user,identity,'CARDIO',True)
        self.assertIsNone(legacy.modulo_id)

    def test_wrong_patient_line_rejected(self):
        with self.assertRaises(HTTPException):
            authorized_patient(self.db,self.user,1,'CARDIO',True)

    def test_responsible_token_cannot_be_used_as_user_token(self):
        from unittest.mock import patch
        from app.core.deps import get_usuario_atual
        with patch('app.core.deps.jwt.decode', return_value={'sub':'1','tipo':'responsavel'}):
            with self.assertRaises(HTTPException) as raised:
                get_usuario_atual('synthetic',self.db)
        self.assertEqual(raised.exception.status_code,401)


class DiagnosisHttpTests(unittest.TestCase):
    setUp = FoundationTests.setUp
    tearDown = FoundationTests.tearDown

    def request(self, method, path, payload=None, authenticated=True):
        import asyncio
        import json
        from urllib.parse import urlsplit
        from fastapi import FastAPI
        from app.database import get_db
        from app.core.deps import get_usuario_atual
        from app.routers.diagnosticos import router
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: self.db
        if authenticated:
            app.dependency_overrides[get_usuario_atual] = lambda: self.user
        async def execute():
            messages = []
            async def receive():
                return {'type': 'http.request', 'body': json.dumps(payload).encode(), 'more_body': False}
            async def send(message):
                messages.append(message)
            parsed = urlsplit(path)
            await app({'type':'http','http_version':'1.1','method':method,'scheme':'http',
                       'path':parsed.path,'query_string':parsed.query.encode(),'root_path':'',
                       'headers':[(b'content-type',b'application/json')]}, receive, send)
            status = next(m['status'] for m in messages if m['type']=='http.response.start')
            body = b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
            return status, json.loads(body)
        return asyncio.run(execute())

    def test_create_list_and_mutations_are_line_scoped(self):
        identities = {}
        for line in ('NEURO', 'CARDIO'):
            status, body = self.request('POST','/diagnosticos',
                {'paciente_id':3,'care_line':line,'descricao_clinica':'Synthetic',
                 'data_diagnostico':'2026-01-01','medico_nome':'Synthetic'})
            self.assertEqual(status,201,body)
            identities[line] = body['id']
        status, body = self.request('GET','/diagnosticos/paciente/3?care_line=CARDIO')
        self.assertEqual(status,200)
        self.assertEqual([item['id'] for item in body],[identities['CARDIO']])
        for method, suffix, payload in (('GET','',None),('PUT','',{'observacoes':'Synthetic'}),
                                       ('PATCH','/cancelar',None),('PATCH','/revisar',None)):
            path = '/diagnosticos/'+str(identities['NEURO'])+suffix+'?care_line=CARDIO'
            self.assertEqual(self.request(method,path,payload)[0],404)
        self.assertEqual(self.db.get(Diagnostico,identities['NEURO']).status,'ATIVO')

    def test_auth_clinic_line_and_write_role_are_required(self):
        path = '/diagnosticos/paciente/3?care_line=NEURO'
        self.assertEqual(self.request('GET',path,authenticated=False)[0],401)
        self.assertEqual(self.request('GET','/diagnosticos/paciente/3')[0],422)
        self.user.clinica_id = 2
        self.assertIn(self.request('GET',path)[0],(403,404))
        self.user.clinica_id = 1
        self.user.perfil = 'SUPORTE'
        self.assertEqual(self.request('POST','/diagnosticos',
            {'paciente_id':3,'care_line':'NEURO','descricao_clinica':'Synthetic',
             'data_diagnostico':'2026-01-01','medico_nome':'Synthetic'})[0],403)
