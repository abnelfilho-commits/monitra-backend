"""SEC-003: real HTTP and ACL, committed synthetic fixtures in disposable PG."""
import json
import os
import unittest
from datetime import date
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy import text, event
from sqlalchemy.orm import Session
from alembic import command
import test_contextual_clinical_schema as foundation
from test_m0_baseline import config
from test_whatsapp_security import LocalClient
from app.database import get_db
from app.core.security import criar_access_token
from app.models import Clinica, Profissional, Usuario, Paciente, PacienteModulo, ProfissionalModulo
from app.models.modular import ModuloClinico
from app.models.registro import RegistroDiario
from app.routers.registros import router


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable local PostgreSQL required')
class RegistrosAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        foundation.PhysicalTests.setUpClass.__func__(cls)
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'head')
            c.execute(text("INSERT INTO modulos_clinicos(id,nome,slug,ativo) VALUES (1,'Synthetic Neuro','neurodesenvolvimento',true)"))

    tearDownClass = classmethod(foundation.PhysicalTests.tearDownClass.__func__)

    def setUp(self):
        self.db = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.db.close)
        self.clinics = [Clinica(nome='Synthetic clinic') for _ in range(2)]
        self.db.add_all(self.clinics); self.db.flush()
        self.prof = Profissional(nome='Synthetic professional',clinica_id=self.clinics[0].id,ativo=True)
        self.db.add(self.prof); self.db.flush()
        self.users = {}
        for role in ('PROFISSIONAL','ADMIN','ADMINISTRADOR','ADMIN_CLINICA','SUPORTE','GESTOR'):
            actor = Usuario(nome='Synthetic',email=uuid4().hex+'@example.invalid',senha_hash='unused',
                            perfil=role,clinica_id=self.clinics[0].id,profissional_id=self.prof.id,ativo=True)
            self.db.add(actor); self.users[role]=actor
        self.patients = [Paciente(nome='PRIVATE_SYNTHETIC',clinica_id=self.clinics[i].id,ativo=True) for i in (0,0,1)]
        self.db.add_all(self.patients); self.db.flush()
        self.db.add(ProfissionalModulo(profissional_id=self.prof.id,modulo_id=1))
        for patient in self.patients:
            self.db.add(PacienteModulo(paciente_id=patient.id,modulo_id=1,ativo=True))
        self.records = [RegistroDiario(paciente_id=p.id,data=date(2026,1,1),alimentacao='PRIVATE_SYNTHETIC',observacao='PRIVATE_SYNTHETIC') for p in self.patients]
        self.db.add_all(self.records); self.db.commit()
        app = FastAPI(); app.include_router(router)
        def database():
            with Session(self.engine) as db:
                yield db
        app.dependency_overrides[get_db] = database
        self.client = LocalClient(app)

    def request(self, operation, *, role='PROFISSIONAL', token=None, patient=None, record=None, payload=None):
        patient = self.patients[0].id if patient is None else patient
        record = self.records[0].id if record is None else record
        method,path = {'create':('POST','/registros/'), 'list':('GET',f'/registros/paciente/{patient}'),
                       'get':('GET',f'/registros/{record}'), 'update':('PUT',f'/registros/{record}'),
                       'delete':('DELETE',f'/registros/{record}')}[operation]
        headers={}
        if role is not None:
            headers['Authorization']='Bearer '+(token or criar_access_token({'sub':str(self.users[role].id),'tipo':'usuario'}))
        body=None
        if operation in ('create','update'):
            headers['Content-Type']='application/json'
            body=json.dumps(payload if payload is not None else dict(paciente_id=patient,data='2026-02-01',alimentacao='Allowed')).encode()
        return self.client.request(method,path,headers=headers,body=body)

    def snapshot(self):
        # Separate connection observes committed state, not the request identity map.
        with self.engine.connect() as c:
            return c.execute(text('SELECT to_jsonb(r) FROM registros_diarios r WHERE paciente_id IN (:a,:b,:c) ORDER BY id'),
                             dict(zip(('a','b','c'),[p.id for p in self.patients]))).scalars().all()

    def denied(self, operation, status=404, **kwargs):
        before=self.snapshot(); sql=[]
        def capture(conn,cursor,statement,parameters,context,many): sql.append(statement.lower().strip())
        def reject_flush(session, context, instances): raise AssertionError('denied persistence flush')
        event.listen(self.engine,'before_cursor_execute',capture)
        event.listen(Session,'before_flush',reject_flush)
        try:
            with patch.object(Session,'commit',side_effect=AssertionError('denied commit')):
                response=self.request(operation,**kwargs)
        finally:
            event.remove(self.engine,'before_cursor_execute',capture)
            event.remove(Session,'before_flush',reject_flush)
        self.assertEqual(response.status_code,status,response.text)
        self.assertNotIn('PRIVATE_SYNTHETIC',response.text)
        if status==404:self.assertEqual(response.json(),{'detail':'Registro não disponível.'})
        self.assertEqual(self.snapshot(),before)
        self.assertFalse(any(s.startswith(('insert ','update ','delete ')) for s in sql))
        return sql

    def deny_all(self, **kwargs):
        for operation in ('create','list','get','update','delete'):
            with self.subTest(operation=operation): self.denied(operation,**kwargs)

    def test_no_token_all_operations(self): self.deny_all(role=None,status=401)
    def test_invalid_token_all_operations(self): self.deny_all(token='invalid',status=401)
    def test_inactive_user_all_operations(self):
        self.users['PROFISSIONAL'].ativo=False; self.db.commit(); self.deny_all(status=401)
    def test_missing_clinic(self):
        self.users['PROFISSIONAL'].clinica_id=None; self.db.commit(); self.deny_all()
    def test_other_clinic(self):
        self.deny_all(patient=self.patients[2].id,record=self.records[2].id)
    def test_missing_professional_neuro(self):
        self.db.query(ProfissionalModulo).filter_by(profissional_id=self.prof.id).delete(); self.db.commit(); self.deny_all()
    def test_inactive_professional(self):
        self.prof.ativo=False; self.db.commit(); self.deny_all()
    def test_inactive_patient(self):
        self.patients[0].ativo=False; self.db.commit(); self.deny_all()
    def test_inactive_patient_neuro_link(self):
        self.db.query(PacienteModulo).filter_by(paciente_id=self.patients[0].id).update({'ativo':False}); self.db.commit(); self.deny_all()
    def test_missing_patient_neuro_link(self):
        self.db.query(PacienteModulo).filter_by(paciente_id=self.patients[0].id).delete(); self.db.commit(); self.deny_all()
    def test_unpermitted_role(self): self.deny_all(role='GESTOR')
    def test_nonexistent_resources(self): self.deny_all(patient=2147483647,record=2147483647)
    def test_update_cannot_move_to_authorized_patient(self):
        self.denied('update',patient=self.patients[1].id)
    def test_update_cannot_move_to_unauthorized_patient(self):
        self.denied('update',patient=self.patients[2].id)
    def test_update_cannot_take_foreign_record(self):
        self.denied('update',record=self.records[2].id)
    def test_update_cannot_move_to_missing_patient(self): self.denied('update',patient=2147483647)
    def test_no_content_loaded_before_denial(self):
        self.users['PROFISSIONAL'].clinica_id=None;self.db.commit()
        for operation in ('get','update','delete'):
            for sql in self.denied(operation):
                if 'from registros_diarios' in sql:
                    projection=sql.split('from')[0]
                    self.assertNotIn('observacao',projection);self.assertNotIn('alimentacao',projection)

    def authorized_crud(self, role, patient=None):
        patient=self.patients[0].id if patient is None else patient
        result=self.request('create',role=role,patient=patient)
        self.assertEqual(result.status_code,201,result.text); identity=result.json()['id']
        self.assertEqual(result.json()['paciente_id'],patient); self.assertEqual(result.json()['alimentacao'],'Allowed')
        self.assertEqual(self.request('get',role=role,record=identity).json(),result.json())
        listed=self.request('list',role=role,patient=patient);self.assertEqual(listed.status_code,200)
        self.assertIn(identity,[r['id'] for r in listed.json()])
        changed=self.request('update',role=role,record=identity,patient=patient,
            payload=dict(paciente_id=patient,data='2026-02-02',alimentacao='Updated'))
        self.assertEqual(changed.status_code,200,changed.text);self.assertEqual(changed.json()['alimentacao'],'Updated')
        self.assertEqual(changed.json()['paciente_id'],patient)
        removed=self.request('delete',role=role,record=identity)
        self.assertEqual(removed.status_code,200);self.assertEqual(removed.json(),{'ok':True})
        with Session(self.engine) as db:self.assertIsNone(db.get(RegistroDiario,identity))

    def test_professional_crud(self): self.authorized_crud('PROFISSIONAL')
    def test_clinic_admin_crud(self): self.authorized_crud('ADMIN_CLINICA')
    def test_clinic_admin_denied_foreign(self): self.deny_all(role='ADMIN_CLINICA',patient=self.patients[2].id,record=self.records[2].id)
    def test_admin_global_policy(self): self.authorized_crud('ADMIN',self.patients[2].id)
    def test_administrador_global_policy(self): self.authorized_crud('ADMINISTRADOR',self.patients[2].id)
    def test_admin_still_requires_patient_line(self):
        self.db.query(PacienteModulo).filter_by(paciente_id=self.patients[0].id).delete();self.db.commit();self.deny_all(role='ADMIN')
    def test_support_read_only(self):
        for op in ('get','list'): self.assertEqual(self.request(op,role='SUPORTE').status_code,200)
        for op in ('create','update','delete'): self.denied(op,role='SUPORTE')
    def test_support_foreign_denied(self): self.deny_all(role='SUPORTE',patient=self.patients[2].id,record=self.records[2].id)
    def test_duplicate_and_payload_validation(self):
        before=self.snapshot()
        for op in ('create','update'):
            result=self.request(op,payload=dict(paciente_id=self.patients[0].id,data='2026-01-01',alimentacao='duplicate')) if op=='create' else self.request(op,record=self.records[1].id,patient=self.patients[1].id,payload={'data':'invalid'})
            self.assertEqual(result.status_code,409 if op=='create' else 422,result.text)
            self.assertEqual(self.snapshot(),before)

    def contextual_identity(self):
        actor=self.users['PROFISSIONAL']; admin=self.users['ADMIN'].id
        person=self.db.scalar(text("INSERT INTO pessoas(nome_completo) VALUES ('Synthetic') RETURNING id"))
        actor.pessoa_id=person;self.prof.pessoa_id=person
        institution=self.db.scalar(text("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Synthetic','OUTRO') RETURNING id"))
        member=self.db.scalar(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'ASSISTENCIAL','2020-01-01') RETURNING id"),dict(p=self.patients[0].id,i=institution))
        context=self.db.scalar(text("INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,criado_por_usuario_id) VALUES (:v,:p,:i,'2020-01-01',:u) RETURNING id"),dict(v=member,p=self.patients[0].id,i=institution,u=admin))
        occupation=self.db.scalar(text("INSERT INTO ocupacoes_profissionais(nome) VALUES (:n) RETURNING id"),dict(n=uuid4().hex))
        link=self.db.scalar(text("INSERT INTO profissional_instituicoes(profissional_id,instituicao_id,ocupacao_id,data_inicio) VALUES (:p,:i,:o,'2020-01-01') RETURNING id"),dict(p=self.prof.id,i=institution,o=occupation))
        root=self.db.scalar(text("INSERT INTO usuario_instituicao_acessos(usuario_id,instituicao_id,perfil_institucional,ativo) VALUES (:u,:i,'PROFISSIONAL',true) RETURNING id"),dict(u=actor.id,i=institution))
        self.db.execute(text("INSERT INTO contexto_profissionais(instituicao_id,contexto_assistencial_id,profissional_instituicao_id,data_inicio,criado_por_usuario_id,motivo_criacao) VALUES (:i,:c,:v,'2020-01-01',:u,'Synthetic participation')"),dict(i=institution,c=context,v=link,u=admin))
        for capability in ('ASSISTENCIAL_LER','ASSISTENCIAL_REGISTRAR'):
            self.db.execute(text("INSERT INTO concessoes_assistenciais(usuario_instituicao_acesso_id,instituicao_id,capacidade,escopo_tipo,contexto_assistencial_id,concedido_por_usuario_id,motivo_concessao) VALUES (:r,:i,:cap,'CONTEXTO',:c,:u,'Synthetic grant')"),dict(r=root,i=institution,cap=capability,c=context,u=admin))
        self.db.commit()
        return institution,context

    def assert_contextual_allowed(self, scope):
        from app.services.autorizacao_contextual import AutorizacaoContextualService
        with Session(self.engine) as db:
            for cap in ('ASSISTENCIAL_LER','ASSISTENCIAL_REGISTRAR'):
                self.assertTrue(AutorizacaoContextualService().authorize_resource(db,
                    actor_id=self.users['PROFISSIONAL'].id,capability=cap,
                    instituicao_id=scope[0],contexto_assistencial_id=scope[1]))

    def test_contextual_only_is_not_legacy_authority(self):
        scope=self.contextual_identity()
        actor=self.users['PROFISSIONAL'];actor.clinica_id=None;actor.profissional_id=None
        self.db.commit();self.assert_contextual_allowed(scope);self.deny_all()

    def test_hybrid_authorized_then_legacy_revoked(self):
        scope=self.contextual_identity();self.assert_contextual_allowed(scope)
        self.authorized_crud('PROFISSIONAL')
        self.db.query(ProfissionalModulo).filter_by(profissional_id=self.prof.id).delete()
        self.db.commit();self.assert_contextual_allowed(scope);self.deny_all()

    def test_update_duplicate_rolls_back(self):
        self.assertEqual(self.request('create').status_code,201)
        before=self.snapshot()
        response=self.request('update')
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.snapshot(),before)
