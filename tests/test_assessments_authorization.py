"""Local ASGI/SQLite security tests; no network, operational DB or credentials."""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
import unittest
from datetime import date
from unittest.mock import patch
from fastapi import FastAPI
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.database import get_db
from app.models import (Clinica, Profissional, Usuario, Paciente, ModuloClinico,
                        PacienteModulo, ProfissionalModulo)
from app.models.modular import FormularioModulo, RegistroLongitudinal, CampoFormulario, RespostaRegistro
from app.models.avaliacao_clinica import AvaliacaoClinica
from app.core.security import criar_access_token
from app.routers import assessments as routes
from app.services.clinical_engine.assessment_builder import AssessmentBuilder
from app.services.clinical_engine.assessment_service import executar_avaliacao_clinica
from test_whatsapp_security import LocalClient


class AssessmentAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        for model in (Clinica, Profissional, Usuario, Paciente, ModuloClinico,
                      PacienteModulo, ProfissionalModulo, FormularioModulo,
                      RegistroLongitudinal, CampoFormulario, RespostaRegistro, AvaliacaoClinica):
            model.__table__.create(self.engine)
        self.db = Session(self.engine, autoflush=False)
        self.db.add_all([Clinica(id=i, nome='Synthetic') for i in (1, 2)])
        self.db.add(Profissional(id=1, nome='Synthetic', clinica_id=1, ativo=True))
        for i, role in ((1, 'PROFISSIONAL'), (2, 'ADMIN'), (3, 'SUPORTE'), (4, 'GESTOR'), (5, 'ADMIN_CLINICA')):
            self.db.add(Usuario(id=i, nome='Synthetic', email=f'{i}@example.invalid', senha_hash='unused',
                                perfil=role, clinica_id=1, profissional_id=1, ativo=True))
        self.db.add_all([ModuloClinico(id=i, nome=str(i), slug=str(i), ativo=True) for i in (1, 2, 3)])
        self.db.add(ProfissionalModulo(profissional_id=1, modulo_id=1))
        for i in (1, 2):
            self.db.add(Paciente(id=i, nome='Synthetic', clinica_id=i, ativo=True))
            for m in (1, 2, 3):
                self.db.add(PacienteModulo(paciente_id=i, modulo_id=m, ativo=True))
        self.db.add_all([FormularioModulo(id=1, modulo_id=1, nome='M-CHAT', codigo='MCHAT', tipo='ASSESSMENT'),
                         FormularioModulo(id=2, modulo_id=1, nome='Denver', codigo='DENVER', tipo='ASSESSMENT'),
                         FormularioModulo(id=3, modulo_id=3, nome='PHQ9', codigo='PHQ9', tipo='ASSESSMENT')])
        self.db.flush()
        for i, patient, module, context in ((1,1,1,None), (2,2,1,None), (3,1,3,None), (4,1,1,99)):
            self.db.add(RegistroLongitudinal(id=i,paciente_id=patient,modulo_id=module,
                contexto_assistencial_id=context,formulario_id=3 if i == 3 else 1,origem='PROFISSIONAL',data_registro=date(2026,1,1)))
        self.db.flush()
        for i in (1,2,3,4):
            r=self.db.get(RegistroLongitudinal,i)
            self.db.add(AvaliacaoClinica(id=i,registro_id=i,paciente_id=r.paciente_id,modulo_id=r.modulo_id,
                                        formulario_id=r.formulario_id,instrumento='PHQ9' if i == 3 else 'MCHAT',resultado={'synthetic':True}))
        for fid, form, name, answer in ((1,1,'mchat_1','NAO'), (2,1,'mchat_2','SIM'),
                                       (3,2,'ps_1','PASSOU'), (4,2,'lg_1','FALHOU')):
            self.db.add(CampoFormulario(id=fid,formulario_id=form,nome_campo=name,
                                       label='Synthetic',tipo_campo='texto'))
            self.db.add(RespostaRegistro(registro_id=1,campo_id=fid,valor_texto=answer))
        self.db.commit()
        app=FastAPI();app.include_router(routes.router)
        app.dependency_overrides[get_db]=lambda:self.db
        self.client=LocalClient(app)

    def tearDown(self):
        self.db.close();self.engine.dispose()

    def request(self, method='GET', path='/assessments/1', *, actor=1, payload=None, token=None):
        import json
        headers={'Content-Type':'application/json'}
        if actor is not None:
            headers['Authorization']='Bearer '+(token or criar_access_token({'sub':str(actor),'tipo':'usuario'}))
        return self.client.request(method,path,body=json.dumps(payload or {}).encode(),headers=headers)

    def count(self):
        return self.db.scalar(select(func.count()).select_from(AvaliacaoClinica))

    def denied_post(self, record=1, actor=1, payload=None, status=404):
        before=self.count()
        with patch.object(routes,'executar_avaliacao_por_registro') as engine:
            response=self.request('POST','/assessments/execute',actor=actor,
                payload=payload or {'registro_id':record,'instrumento':'MCHAT'})
            self.assertEqual(response.status_code,status,response.text)
            engine.assert_not_called()
        self.assertEqual(self.count(),before)
        return response

    def test_all_routes_require_authentication(self):
        for method,path in [('GET','/assessments/1'),('GET','/assessments/registro/1'),
                            ('GET','/assessments/paciente/1'),('POST','/assessments/execute')]:
            with self.subTest(path=path):
                r=self.request(method,path,actor=None,payload={'registro_id':1,'instrumento':'MCHAT'})
                self.assertEqual(r.status_code,401)

    def test_invalid_and_responsible_tokens(self):
        for token in ('invalid',criar_access_token({'sub':'1','tipo':'responsavel'})):
            self.assertEqual(self.request(token=token).status_code,401)

    def test_inactive_user_and_revocation(self):
        self.assertEqual(self.request().status_code,200)
        self.db.get(Usuario,1).ativo=False;self.db.commit()
        self.assertEqual(self.request().status_code,401)

    def test_unauthorized_profile(self):
        self.assertEqual(self.request(actor=4).status_code,404)
        self.denied_post(actor=4)

    def test_cross_clinic_and_missing_indistinguishable(self):
        foreign=self.request(path='/assessments/2')
        missing=self.request(path='/assessments/999')
        self.assertEqual((foreign.status_code,foreign.json()),(missing.status_code,missing.json()))
        self.denied_post(record=2)

    def test_admin_global_and_admin_clinic(self):
        self.assertEqual(self.request(path='/assessments/2',actor=2).status_code,200)
        self.assertEqual(self.request(path='/assessments/2',actor=5).status_code,404)

    def test_contexts_including_other_institution_never_bypass(self):
        for context in (99,100):
            self.db.get(RegistroLongitudinal,4).contexto_assistencial_id=context;self.db.commit()
            for actor in (1,2):
                self.assertEqual(self.request(path='/assessments/4',actor=actor).status_code,404)
                self.assertEqual(self.request(path='/assessments/registro/4',actor=actor).status_code,404)
                self.denied_post(record=4,actor=actor)

    def test_unpermitted_line_hidden_from_list(self):
        self.assertEqual(self.request(path='/assessments/3',actor=2).status_code,200)
        self.assertEqual(self.request(path='/assessments/3').status_code,404)
        response=self.request(path='/assessments/paciente/1')
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual([x['id'] for x in response.json()],[1])
        self.denied_post(record=3)

    def test_professional_and_patient_line_revocation(self):
        for model in (ProfissionalModulo,PacienteModulo):
            with self.subTest(model=model):
                row=self.db.query(model).filter_by(modulo_id=1).first()
                self.db.delete(row);self.db.commit()
                self.assertEqual(self.request().status_code,404)
                self.denied_post()

    def test_orphan_patient_module_and_form_mismatch(self):
        row=self.db.get(AvaliacaoClinica,1)
        for field,value in [('registro_id',999),('paciente_id',2),('modulo_id',2),('formulario_id',2),('instrumento','DENVER')]:
            original=getattr(row,field);setattr(row,field,value);self.db.commit()
            self.assertEqual(self.request().status_code,404)
            self.assertEqual(self.request(path='/assessments/paciente/1').json(),[])
            setattr(row,field,original);self.db.commit()

    def test_invalid_identity_fields_and_ids(self):
        for payload in ({'registro_id':1,'instrumento':'MCHAT','paciente_id':2},
                        {'registro_id':True,'instrumento':'MCHAT'},
                        {'registro_id':-1,'instrumento':'MCHAT'}):
            self.denied_post(payload=payload,status=422)
        self.assertEqual(self.request(path='/assessments/-1').status_code,422)

    def test_form_instrument_module_validation(self):
        self.denied_post(payload={'registro_id':1,'instrumento':'DENVER'},status=422)
        self.denied_post(payload={'registro_id':1,'instrumento':'UNKNOWN'},status=422)
        form=self.db.get(FormularioModulo,1)
        for field,value in [('modulo_id',2),('tipo','LONGITUDINAL'),('ativo',False)]:
            original=getattr(form,field);setattr(form,field,value);self.db.commit()
            self.denied_post(status=422)
            setattr(form,field,original);self.db.commit()

    def test_support_reads_but_cannot_execute(self):
        self.assertEqual(self.request(actor=3).status_code,200)
        self.denied_post(actor=3)

    def test_authorized_reads_preserve_contract(self):
        a=self.request().json();b=self.request(path='/assessments/registro/1').json()
        self.assertEqual(a,b)
        self.assertEqual(set(a),set(routes.DETAIL))
        self.assertEqual(set(self.request(path='/assessments/paciente/1').json()[0]),set(routes.SUMMARY))

    def test_execute_real_engines_same_results_and_persistence(self):
        for instrument,form in (('MCHAT',1),('DENVER',2)):
            with self.subTest(instrument=instrument):
                self.db.get(RegistroLongitudinal,1).formulario_id=form;self.db.commit()
                expected=executar_avaliacao_clinica(AssessmentBuilder.from_registro(self.db,1,instrument))
                before=self.count()
                result=self.request('POST','/assessments/execute',payload={'registro_id':1,'instrumento':instrument})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(self.count(),before+1)
                expected['instrumento_label']=result.json()['resultado']['instrumento_label']
                self.assertEqual(result.json()['resultado'],expected)

    def test_failure_after_flush_rolls_back_and_sanitizes(self):
        before=self.count()
        def failing(**kwargs):
            self.assertFalse(kwargs['commit'])
            self.db.add(AvaliacaoClinica(registro_id=1,paciente_id=1,modulo_id=1,instrumento='MCHAT'))
            self.db.flush()
            raise RuntimeError('SECRET_SQL_CLINICAL')
        with patch.object(routes,'executar_avaliacao_por_registro',side_effect=failing):
            result=self.request('POST','/assessments/execute',payload={'registro_id':1,'instrumento':'MCHAT'})
        self.assertEqual(result.status_code,500)
        self.assertNotIn('SECRET',result.text)
        self.assertEqual(self.count(),before)

    def test_read_failure_sanitized(self):
        with patch.object(routes,'assessment_access',side_effect=RuntimeError('SECRET_SQL')):
            response=self.request()
        self.assertEqual(response.status_code,500)
        self.assertNotIn('SECRET',response.text)

    def test_record_id_manipulation_and_patient_listing_denied(self):
        denied=self.request(path='/assessments/registro/2')
        missing=self.request(path='/assessments/registro/999')
        self.assertEqual((denied.status_code,denied.json()),(missing.status_code,missing.json()))
        self.assertEqual(self.request(path='/assessments/paciente/2').status_code,404)
        self.denied_post(record=999)

    def test_inactive_patient_and_catalog(self):
        self.db.get(Paciente,1).ativo=False;self.db.commit()
        self.assertEqual(self.request().status_code,404)
        self.denied_post()
        self.db.get(Paciente,1).ativo=True
        self.db.get(ModuloClinico,1).ativo=False;self.db.commit()
        self.assertEqual(self.request().status_code,404)
        self.denied_post()

    def test_commit_failure_rolls_back(self):
        before=self.count()
        with patch.object(self.db,'commit',side_effect=RuntimeError('SECRET_COMMIT')):
            response=self.request('POST','/assessments/execute',payload={'registro_id':1,'instrumento':'MCHAT'})
        self.assertEqual(response.status_code,500)
        self.assertNotIn('SECRET',response.text)
        self.assertEqual(self.count(),before)

    def test_read_never_flushes_or_commits(self):
        with patch.object(self.db,'commit',side_effect=AssertionError('commit')), patch.object(self.db,'flush',side_effect=AssertionError('flush')):
            for path in ('/assessments/1','/assessments/registro/1','/assessments/paciente/1'):
                self.assertEqual(self.request(path=path).status_code,200)

    def test_lowercase_instrument_compatible(self):
        response=self.request('POST','/assessments/execute',payload={'registro_id':1,'instrumento':'mchat'})
        self.assertEqual(response.status_code,200,response.text)
