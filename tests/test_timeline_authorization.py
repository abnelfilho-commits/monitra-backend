"""Real HTTP/authentication/adapters on disposable local PostgreSQL; synthetic data only."""
import os
import unittest
from datetime import date, datetime
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from sqlalchemy import text, event
from sqlalchemy.orm import Session
from alembic import command
import test_contextual_clinical_schema as foundation
from test_m0_baseline import config
from test_whatsapp_security import LocalClient
from app.database import get_db
from app.core.security import criar_access_token
from app.models import Clinica, Profissional, Usuario, Paciente, PacienteModulo, ProfissionalModulo
from app.models.modular import ModuloClinico, FormularioModulo, RegistroLongitudinal, CampoFormulario, RespostaRegistro
from app.models.avaliacao_clinica import AvaliacaoClinica
from app.models.intervencao import Intervencao
from app.routers.timeline import router
from app.services.longitudinal.factory import get_adapter


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable local PostgreSQL required')
class TimelineAuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        foundation.PhysicalTests.setUpClass.__func__(cls)
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'head')

    tearDownClass = classmethod(foundation.PhysicalTests.tearDownClass.__func__)

    def setUp(self):
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.db = Session(self.connection, autoflush=False)
        self.addCleanup(self._close_fixture)
        self.db.add_all([ModuloClinico(id=1,nome='Synthetic Neuro',slug='neurodesenvolvimento',ativo=True),
                         ModuloClinico(id=2,nome='Synthetic Cardio',slug='cardiometabolico',ativo=True)])
        self.db.flush()
        self.clinics = [Clinica(nome='Synthetic clinic') for _ in range(2)]
        self.db.add_all(self.clinics); self.db.flush()
        self.prof = Profissional(nome='Synthetic professional', clinica_id=self.clinics[0].id, ativo=True)
        self.db.add(self.prof); self.db.flush()
        self.users = {}
        for role in ('PROFISSIONAL','ADMIN','ADMINISTRADOR','ADMIN_CLINICA','SUPORTE','GESTOR'):
            u = Usuario(nome='Synthetic actor', email=uuid4().hex+'@example.invalid', senha_hash='unused',
                        perfil=role, clinica_id=self.clinics[0].id, profissional_id=self.prof.id, ativo=True)
            self.db.add(u); self.users[role]=u
        self.db.add(ProfissionalModulo(profissional_id=self.prof.id, modulo_id=1))
        self.patient = Paciente(nome='SYNTHETIC_PRIVATE_PATIENT', clinica_id=self.clinics[0].id, ativo=True)
        self.other_patient=Paciente(nome='Synthetic other',clinica_id=self.clinics[1].id,ativo=True)
        self.db.add_all([self.patient,self.other_patient]); self.db.flush()
        self.db.add(PacienteModulo(paciente_id=self.patient.id,modulo_id=1,ativo=True))
        self.forms = {}
        for kind in ('MCHAT','DENVER','REGISTRO'):
            f=FormularioModulo(modulo_id=1,nome='Synthetic '+kind,codigo=kind,
                tipo='LONGITUDINAL' if kind=='REGISTRO' else 'ASSESSMENT',ativo=True)
            self.db.add(f);self.db.flush();self.forms[kind]=f
        self.records={};self.events={}
        for kind in self.forms:
            r=RegistroLongitudinal(paciente_id=self.patient.id,modulo_id=1,formulario_id=self.forms[kind].id,
                data_registro=date(2026,1,1),origem='PROFISSIONAL')
            self.db.add(r);self.db.flush();self.records[kind]=r
            if kind=='REGISTRO': self.events[kind]=r
            else:
                a=AvaliacaoClinica(registro_id=r.id,paciente_id=self.patient.id,modulo_id=1,
                    formulario_id=self.forms[kind].id,instrumento=kind,score=6,
                    resultado={},interpretacao='SYNTHETIC_PRIVATE_CONTENT')
                self.db.add(a);self.db.flush();self.events[kind]=a
        field=CampoFormulario(formulario_id=self.forms['REGISTRO'].id,nome_campo='synthetic',label='Synthetic',tipo_campo='texto')
        self.db.add(field);self.db.flush()
        self.answer=RespostaRegistro(registro_id=self.records['REGISTRO'].id,campo_id=field.id,valor_texto='SYNTHETIC_PRIVATE_CONTENT')
        self.db.add(self.answer)
        i=Intervencao(paciente_id=self.patient.id,modulo_id=1,tipo='Synthetic',descricao='SYNTHETIC_PRIVATE_CONTENT',data_intervencao=datetime(2026,1,1))
        self.db.add(i);self.db.flush();self.events['INTERVENCAO']=i
        app=FastAPI();app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        self.client=LocalClient(app)

    def _close_fixture(self):
        self.db.close();self.transaction.rollback();self.connection.close()

    def request(self, kind, *, role='PROFISSIONAL', token=None, identity=None):
        headers={}
        if role is not None:
            headers['Authorization']='Bearer '+(token or criar_access_token({'sub':str(self.users[role].id),'tipo':'usuario'}))
        canonical='DENVER' if kind.upper() in ('DENVERII','DENVER_II') else kind.upper()
        identity=identity if identity is not None else self.events[canonical].id
        return self.client.request('GET',f'/timeline/eventos/{kind}/{identity}',headers=headers)

    def denied(self, kind, status=404, **kw):
        with patch('app.services.longitudinal.service.get_adapter',side_effect=AssertionError('content loaded before ACL')):
            r=self.request(kind,**kw)
        self.assertEqual(r.status_code,status,r.text)
        self.assertNotIn('SYNTHETIC_PRIVATE',r.text)
        if status==404:self.assertEqual(r.json(),{'detail':'Evento clínico não disponível.'})

    def deny_all(self, **kw):
        for kind in self.events:
            with self.subTest(kind=kind):self.denied(kind,**kw)

    def test_missing_authentication(self): self.deny_all(role=None,status=401)
    def test_invalid_token(self): self.deny_all(token='invalid',status=401)
    def test_responsible_token(self):
        self.deny_all(token=criar_access_token({'sub':str(self.users['PROFISSIONAL'].id),'tipo':'responsavel'}),status=401)
    def test_unpermitted_profile(self): self.deny_all(role='GESTOR')
    def test_missing_legacy_identity(self):
        u=self.users['PROFISSIONAL'];u.clinica_id=None;u.profissional_id=None;self.db.flush();self.deny_all()
    def test_foreign_clinic(self):
        self.patient.clinica_id=self.clinics[1].id;self.db.flush();self.deny_all()
    def test_professional_line_revocation(self):
        for kind in self.events:self.assertEqual(self.request(kind).status_code,200)
        self.db.query(ProfissionalModulo).filter_by(profissional_id=self.prof.id).delete();self.db.flush();self.deny_all()
    def test_patient_line_revocation(self):
        for kind in self.events:self.assertEqual(self.request(kind).status_code,200)
        self.db.query(PacienteModulo).filter_by(paciente_id=self.patient.id).delete();self.db.flush();self.deny_all()
    def test_inactive_actor(self):
        self.users['PROFISSIONAL'].ativo=False;self.db.flush();self.deny_all(status=401)
    def test_inactive_patient(self):
        self.patient.ativo=False;self.db.flush();self.deny_all()
    def test_missing_ids_and_invalid_ids(self):
        self.deny_all(identity=2147483647);self.deny_all(identity=-1,status=422)
    def test_authorized_contracts_and_profiles(self):
        for kind,row in self.events.items():
            expected=jsonable_encoder(get_adapter(kind).build_response(self.db,row.id))
            for role in ('PROFISSIONAL','ADMIN','ADMINISTRADOR','ADMIN_CLINICA','SUPORTE'):
                with self.subTest(kind=kind,role=role):
                    r=self.request(kind,role=role);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json(),expected)
    def test_global_admin_policy_does_not_expand_clinic_admin(self):
        self.patient.clinica_id=self.clinics[1].id;self.db.flush()
        for kind in self.events:
            self.assertEqual(self.request(kind,role='ADMIN').status_code,200)
            self.denied(kind,role='ADMIN_CLINICA');self.denied(kind,role='SUPORTE')
    def test_denver_aliases_and_mismatched_kind(self):
        for stored in ('DENVER','DENVERII','DENVER_II'):
            self.events['DENVER'].instrumento=stored;self.db.flush()
            for route in ('DENVER','DENVERII','DENVER_II','denver'):
                r=self.request(route);self.assertEqual(r.status_code,200,r.text);self.assertEqual(r.json()['tipo'],'DENVER')
        self.denied('MCHAT',identity=self.events['DENVER'].id)
        self.denied('DENVER',identity=self.events['MCHAT'].id)
    def test_assessment_inconsistent_ancestry(self):
        for kind in ('MCHAT','DENVER'):
            row=self.events[kind]
            for field,value in [('registro_id',2147483647),('paciente_id',self.other_patient.id),('modulo_id',2),('formulario_id',self.forms['REGISTRO'].id),('instrumento','PHQ9')]:
                with self.subTest(kind=kind,field=field):
                    with self.db.begin_nested() as savepoint:
                        setattr(row,field,value);self.db.flush()
                        self.denied(kind);savepoint.rollback()
                    self.db.expire_all()
    def test_record_form_line_inconsistent(self):
        self.forms['REGISTRO'].modulo_id=2;self.db.flush();self.denied('REGISTRO')
    def test_record_answer_form_inconsistent(self):
        f=CampoFormulario(formulario_id=self.forms['MCHAT'].id,nome_campo='wrong',label='Synthetic',tipo_campo='texto')
        self.db.add(f);self.db.flush();self.answer.campo_id=f.id;self.db.flush();self.denied('REGISTRO')
    def test_contextual_events_denied_even_to_admin(self):
        # Real contextual identity and FK-consistent ancestry, confined to this test transaction.
        actor=self.users['ADMIN'].id
        institution=self.db.scalar(text("INSERT INTO instituicoes(razao_social,tipo_instituicao) VALUES ('Synthetic','OUTRO') RETURNING id"))
        link=self.db.scalar(text("INSERT INTO paciente_instituicoes(paciente_id,instituicao_id,tipo_vinculo,data_inicio) VALUES (:p,:i,'OUTRO','2020-01-01') RETURNING id"),dict(p=self.patient.id,i=institution))
        ctx=self.db.scalar(text("INSERT INTO contextos_assistenciais(paciente_instituicao_id,paciente_id,instituicao_id,data_inicio,criado_por_usuario_id) VALUES (:l,:p,:i,'2020-01-01',:u) RETURNING id"),dict(l=link,p=self.patient.id,i=institution,u=actor))
        self.db.execute(text('INSERT INTO contexto_assistencial_linhas(contexto_assistencial_id,modulo_id) VALUES (:c,1)'),dict(c=ctx))
        for r in self.records.values():r.contexto_assistencial_id=ctx
        self.events['INTERVENCAO'].contexto_assistencial_id=ctx;self.db.flush()
        self.deny_all();self.deny_all(role='ADMIN')
    def test_no_content_projection_before_denial(self):
        self.users['PROFISSIONAL'].clinica_id=None;self.db.flush();statements=[]
        def capture(conn,cursor,statement,parameters,context,many): statements.append(statement.lower())
        event.listen(self.engine,'before_cursor_execute',capture)
        try:self.deny_all()
        finally:event.remove(self.engine,'before_cursor_execute',capture)
        for sql in statements:
            if any('from '+table in sql for table in ('avaliacoes_clinicas','registros_longitudinais','intervencoes')):
                projection=sql.split('from')[0]
                for sensitive in ('resultado','descricao','leitura_clinica','interpretacao'):
                    self.assertNotIn(sensitive,projection)
    def test_no_write_or_commit(self):
        with patch.object(self.db,'commit',side_effect=AssertionError('commit')),patch.object(self.db,'flush',side_effect=AssertionError('flush')):
            for kind in self.events:self.assertEqual(self.request(kind).status_code,200)
    def test_internal_error_sanitized(self):
        with patch('app.services.longitudinal.service.get_adapter',side_effect=RuntimeError('SYNTHETIC_PRIVATE_SQL')):
            for kind in self.events:
                r=self.request(kind);self.assertEqual(r.status_code,500);self.assertNotIn('SYNTHETIC_PRIVATE',r.text)

    def test_unknown_type_is_sanitized(self):
        self.denied('UNKNOWN',identity=self.events['MCHAT'].id)

    def test_denver_form_aliases_remain_scoped_to_timeline(self):
        from app.routers.assessments import router as assessment_router
        app=FastAPI();app.include_router(assessment_router)
        app.dependency_overrides[get_db]=lambda:self.db
        client=LocalClient(app)
        for code in ('DENVER','DENVERII','DENVER_II'):
            self.forms['DENVER'].codigo=code
            for instrument in ('DENVER','DENVERII','DENVER_II'):
                self.events['DENVER'].instrumento=instrument;self.db.flush()
                self.assertEqual(self.request('DENVER').status_code,200)
                token=criar_access_token({'sub':str(self.users['PROFISSIONAL'].id),'tipo':'usuario'})
                r=client.request('GET',f"/assessments/{self.events['DENVER'].id}",headers={'Authorization':'Bearer '+token})
                self.assertEqual(r.status_code,200 if code==instrument else 404)
