"""Gate 3: approved operational policy, temporal BMI and isolated journey."""
from fixtures.cardio_intervention_schema import create_cardio_intervention_table
import os
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
import unittest
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4
from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.database import Base
from app.models import (Clinica, Profissional, Usuario, Paciente, ModuloClinico,
    PacienteModulo, ProfissionalModulo, FormularioModulo, CampoFormulario,
    RegistroLongitudinal, RespostaRegistro, Diagnostico)
from app.services.care_lines import CARDIO
from app.services.clinical_reading import ClinicalReadingService
from app.services.cardio_priority import prioritize
from app.services.continuity_service import continuity_signal, classify_continuity
from app.services.cardio_evolution import project_observation, evolution
from app.services.cardio_longitudinal import population, cockpit, patient_detail, patient_timeline
from app.services.timeline_service import TimelineService
from app.services.timeline.models import TimelineQuery, TimelineScope
from app.services import cardiometabolico_engine as engine

DAY = date(2026, 9, 17)


class PolicyTests(unittest.TestCase):
    def patient(self, identity, risk, continuity, name='Synthetic'):
        return {'id': identity, 'nome': name, 'risco': risk,
                'continuidade': {'classification': continuity}}

    def test_all_risk_continuity_combinations(self):
        for risk in (None, 'baixo', 'moderado', 'alto', 'critico'):
            for continuity in ('NAO_INICIADA', 'REGULAR', 'ATENCAO', 'CRITICA'):
                with self.subTest(risk=risk, continuity=continuity):
                    result = prioritize([self.patient(1, risk, continuity)])
                    included = risk in ('moderado','alto','critico') or continuity in ('ATENCAO','CRITICA')
                    self.assertEqual(bool(result), included)
                    if included:
                        self.assertEqual(result[0]['risco'], risk)
                        self.assertEqual(result[0]['continuidade']['classification'], continuity)
                        self.assertNotIn('score', result[0])

    def test_approved_order_and_main_reason(self):
        items = [self.patient(1,'critico','REGULAR'),self.patient(2,'baixo','CRITICA'),
                 self.patient(3,'moderado','CRITICA'),self.patient(4,'alto','ATENCAO'),
                 self.patient(5,'moderado','REGULAR'),self.patient(6,None,'ATENCAO')]
        result = prioritize(items)
        self.assertEqual([p['id'] for p in result],[1,4,2,3,5,6])
        self.assertEqual(result[3]['sinais'],['CONTINUIDADE_CRITICA','RISCO_CLINICO_MODERADO'])
        self.assertEqual(result[3]['motivo_principal'],'CONTINUIDADE_CRITICA')

    def test_multiple_signals_and_repeated_patient_do_not_duplicate(self):
        item = self.patient(1,'critico','CRITICA')
        result = prioritize([item,item])
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['sinais'],['RISCO_CLINICO_CRITICO','CONTINUIDADE_CRITICA'])

    def test_deterministic_ties(self):
        result = prioritize([self.patient(3,'alto','REGULAR','B'),self.patient(2,'alto','REGULAR','A'),self.patient(1,'alto','REGULAR','A')])
        self.assertEqual([p['id'] for p in result],[1,2,3])

    def test_continuity_preserves_existing_boundaries(self):
        for days, expected in ((None,'NAO_INICIADA'),(0,'REGULAR'),(3,'REGULAR'),(4,'ATENCAO'),(6,'ATENCAO'),(7,'CRITICA')):
            self.assertEqual(classify_continuity(days), expected)
        self.assertEqual(continuity_signal(None,DAY)['classification'],'NAO_INICIADA')

    def observation(self, answers):
        return project_observation(SimpleNamespace(id=1,paciente_id=1,data_registro=DAY,origem='PROFISSIONAL'), answers)

    def test_bmi_canonical_units_and_rounding_independent_of_labels(self):
        for weight, height, expected in ((80,2,20.0),(82,1.75,26.8),(80,1.8,24.7),(100,1.7,34.6)):
            for label in ('Altura', 'Altura (m)', 'Altura (cm)', 'Outro texto'):
                result=self.observation([('peso','Qualquer label',weight,None),('altura',label,height,None)])
                self.assertEqual(result['imc'],expected)
                self.assertEqual(result['imc_units'],{'peso':'kg','altura':'m'})
        # No implicit conversion from centimeters, even when a label suggests it.
        self.assertEqual(self.observation([('peso','Peso',80,None),('altura','Altura (cm)',200,None)])['imc'],0.0)

    def test_bmi_missing_invalid_or_duplicate_evidence_unavailable(self):
        weight=('peso','Peso',80,None)
        height=('altura','Altura',2,None)
        for rows in ([],[weight],[height],[weight,height,height],[weight,weight,height],
                     [weight,('altura','Altura',0,None)], [weight,('altura','Altura',-2,None)],
                     [weight,('altura','Altura',float('nan'),None)],
                     [weight,('altura','Altura',float('inf'),None)],
                     [weight,('altura','Altura',1e-300,None)],
                     [weight,('altura','Altura',2,'invalid')]):
            with self.subTest(rows=rows):
                self.assertIsNone(self.observation(rows)['imc'])

    def test_canonical_engine_boundary_characterization(self):
        cases=[({},0,'baixo'),({'glicemia_jejum':110},1,'baixo'),
               ({'glicemia_jejum':180},3,'moderado'),
               ({'glicemia_jejum':180,'pressao_sistolica':160},6,'alto'),
               ({'glicemia_jejum':250,'pressao_sistolica':180,'peso':140},10,'critico')]
        for values,score,risk in cases:
            self.assertEqual(engine.calcular_score(values),score)
            self.assertEqual(engine.classificar_risco(score),risk)


class JourneyTests(unittest.TestCase):
    postgres_url = None

    def setUp(self):
        self.admin = None
        if self.postgres_url:
            if self.postgres_url != 'postgresql+psycopg2://gate1@127.0.0.1/gate1_test':
                raise RuntimeError('Only isolated disposable Gate database allowed.')
            self.schema = 'gate3_' + uuid4().hex
            self.admin = create_engine(self.postgres_url)
            with self.admin.begin() as c: c.execute(text('CREATE SCHEMA '+self.schema))
            self.engine = create_engine(self.postgres_url,connect_args={'options':'-csearch_path='+self.schema})
        else:
            self.engine = create_engine('sqlite:///:memory:')
        # Full checked-in schema, synthetic-only; no application connection used.
        Base.metadata.create_all(self.engine)
        with self.engine.begin() as c:
            create_cardio_intervention_table(c)
            for name,kind in {'observacoes':'TEXT','score_clinico':'INTEGER','risco':'TEXT','peso':'NUMERIC'}.items():
                c.execute(text('ALTER TABLE registros_longitudinais ADD COLUMN '+name+' '+kind))
        self.db=Session(self.engine)
        self.db.add_all([Clinica(id=i,nome='Synthetic') for i in (1,2)])
        self.db.flush()
        self.db.add(Profissional(id=1,nome='Synthetic',clinica_id=1,ativo=True));self.db.flush()
        self.db.add(Usuario(id=1,nome='Synthetic',email='gate3@example.invalid',senha_hash='unused',perfil='PROFISSIONAL',clinica_id=1,profissional_id=1,ativo=True))
        self.db.add_all([ModuloClinico(id=i,nome='Synthetic',slug=str(i),ativo=True) for i in (1,2)]);self.db.flush()
        for mid in (1,2):
            self.db.add(ProfissionalModulo(profissional_id=1,modulo_id=mid))
            self.db.add(FormularioModulo(id=mid,modulo_id=mid,nome='Synthetic',tipo='REGISTRO_DIARIO',ativo=True))
        self.db.flush()
        self.fields={}
        for mid in (1,2):
            for name,label in [('glicemia_jejum','Glicemia'),('pressao_sistolica','Sistólica'),('pressao_diastolica','Diastólica'),('peso','Peso (kg)'),('altura','Altura (m)')]:
                f=CampoFormulario(formulario_id=mid,nome_campo=name,label=label,tipo_campo='numero',ativo=True)
                self.db.add(f);self.db.flush();self.fields[mid,name]=f.id
        for pid in (1,2,3,4,5):
            self.db.add(Paciente(id=pid,nome='Synthetic '+str(pid),clinica_id=2 if pid==4 else 1,altura=1.50,ativo=True))
        self.db.flush()
        for pid,mid in ((1,1),(2,2),(3,1),(3,2),(4,2),(5,2)):
            self.db.add(PacienteModulo(paciente_id=pid,modulo_id=mid,ativo=True))
        self.db.commit()
        self.user=SimpleNamespace(id=1,perfil='PROFISSIONAL',profissional_id=1,clinica_id=1)

    def tearDown(self):
        self.db.close();self.engine.dispose()
        if self.admin:
            with self.admin.begin() as c: c.execute(text('DROP SCHEMA '+self.schema+' CASCADE'))
            self.admin.dispose()

    def record(self,pid=3,mid=2,day=DAY,origin='PROFISSIONAL',**values):
        record=RegistroLongitudinal(paciente_id=pid,modulo_id=mid,formulario_id=mid,data_registro=day,origem=origin,criado_por_usuario_id=1)
        self.db.add(record);self.db.flush()
        for name,value in values.items():
            self.db.add(RespostaRegistro(registro_id=record.id,campo_id=self.fields[mid,name],valor_numero=value))
        self.db.commit()
        return record

    def test_current_batch_equals_individual_and_never_consumes_stale_columns(self):
        r=self.record(glicemia_jejum=180,pressao_sistolica=160)
        self.db.execute(text("UPDATE registros_longitudinais SET score_clinico=0,risco='baixo',peso=200 WHERE id=:id"),{'id':r.id});self.db.commit()
        service=ClinicalReadingService()
        batch=service.get_readings(self.db,[2,3,5],'CARDIO')
        for pid in (2,3,5):
            self.assertEqual(batch[pid],service.get_reading(self.db,pid,'CARDIO'))
        self.assertEqual(batch[3].risk,'alto');self.assertIsNone(batch[3].trend)
        self.assertIsNone(batch[2].risk)
        self.assertEqual(batch[3].reference_date,DAY)

    def test_batch_resolution_rejects_inactive_and_planned_context(self):
        from dataclasses import replace
        from app.services.care_lines import (CareLineRegistry, CareLineResolver, CareLineCapabilityStatus,
            CareLineCapabilityNotSupported, CareLineInactive, PatientCareLineNotFound, CareLineNotFound)
        service=ClinicalReadingService()
        with self.assertRaises(CareLineNotFound): service.get_readings(self.db,[3],'UNKNOWN')
        with self.assertRaises(PatientCareLineNotFound): service.get_readings(self.db,[1],'CARDIO')
        planned=replace(CARDIO,capabilities={**CARDIO.capabilities,'clinical_reading':CareLineCapabilityStatus.PLANNED})
        service=ClinicalReadingService(resolver=CareLineResolver(CareLineRegistry([planned])))
        with self.assertRaises(CareLineCapabilityNotSupported): service.get_readings(self.db,[3],'CARDIO')
        self.db.query(ModuloClinico).filter_by(id=2).update({'ativo':False});self.db.commit()
        with self.assertRaises(CareLineInactive): ClinicalReadingService().get_readings(self.db,[3],'CARDIO')

    def test_latest_empty_observation_does_not_fall_back_to_old_risk(self):
        self.record(day=DAY-timedelta(days=1),glicemia_jejum=250,pressao_sistolica=180,peso=140)
        latest=self.record(day=DAY)
        result=ClinicalReadingService().get_readings(self.db,[3],'CARDIO')[3]
        self.assertEqual(result.metadata['record_id'],latest.id)
        self.assertIsNone(result.risk)
        self.assertIsNone(result.trend)
        self.assertEqual(result.reference_date,DAY)

    def test_bmi_no_cadastral_height_or_carry_forward(self):
        self.record(day=DAY-timedelta(days=1),peso=80,altura=2)
        self.record(day=DAY,peso=90)
        before=evolution(self.db,[3],2)
        self.assertEqual([r['imc'] for r in before],[20,None])
        self.db.query(Paciente).filter_by(id=3).update({'altura':1.90});self.db.commit()
        self.assertEqual(before,evolution(self.db,[3],2))
        self.record(day=DAY+timedelta(days=1),altura=1.75)
        self.assertEqual([r['imc'] for r in evolution(self.db,[3],2)],[20,None,None])
        self.db.query(CampoFormulario).filter_by(formulario_id=2).update({'label':'Texto de apresentação alterado'})
        self.db.commit()
        self.assertEqual([r['imc'] for r in evolution(self.db,[3],2)],[20,None,None])
        reading=ClinicalReadingService().get_readings(self.db,[3],'CARDIO')[3]
        self.assertIsNone(reading.metadata['imc'])
        self.assertIsNone(reading.risk)

    def test_no_record_membership_and_clinic_scope(self):
        result=population(self.db,self.user,DAY)
        self.assertEqual([p['id'] for p in result],[2,3,5])
        self.assertTrue(all(p['risco'] is None and p['tendencia'] is None for p in result))
        self.assertTrue(all(p['continuidade']['classification']=='NAO_INICIADA' for p in result))
        for pid in (1,4):
            with self.assertRaises(HTTPException): patient_detail(self.db,self.user,pid)

    def test_revoked_line_patient_and_professional_denied(self):
        self.db.query(PacienteModulo).filter_by(paciente_id=3,modulo_id=2).update({'ativo':False});self.db.commit()
        self.assertNotIn(3,[p['id'] for p in population(self.db,self.user,DAY)])
        with self.assertRaises(HTTPException): patient_detail(self.db,self.user,3)
        self.db.query(ProfissionalModulo).filter_by(modulo_id=2).delete();self.db.commit()
        with self.assertRaises(HTTPException): population(self.db,self.user,DAY)

    def test_timeline_three_origins_diagnosis_interventions_only_cardio(self):
        self.record(mid=1,glicemia_jejum=999)
        for origin in ('PROFISSIONAL','RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP'):
            self.record(origin=origin,glicemia_jejum=180)
        for mid in (1,2):
            self.db.add(Diagnostico(paciente_id=3,modulo_id=mid,descricao_clinica='Synthetic diagnosis '+str(mid),data_diagnostico=DAY,medico_nome='Synthetic'))
        self.db.execute(text("INSERT INTO intervencoes_cardiometabolicas (id,modulo_id,paciente_id,tipo,descricao,prioridade,created_at) VALUES (1,2,3,'orientacao','Synthetic intervention','alta',CURRENT_TIMESTAMP)"));self.db.commit()
        events=patient_timeline(self.db,self.user,3)
        self.assertEqual(len(events),5)
        intervention = next(e for e in events if e['event_type']=='INTERVENTION')
        self.assertIsNone(intervention['actor'])
        self.assertIsNone(intervention['data'])
        self.assertEqual({e['care_line'] for e in events},{'CARDIO'})
        self.assertEqual({e['origem'] for e in events if e['event_type']=='DAILY_RECORD'}, {'PROFISSIONAL','RESPONSAVEL_APP','RESPONSAVEL_WHATSAPP'})
        self.assertTrue(all('risco' not in e for e in events))
        self.assertEqual(len(evolution(self.db,[3],2)),3)
        neuro=TimelineService.get_events(self.db,TimelineQuery(3,scope=TimelineScope.CARE_LINE,requested_care_line='NEURO'))
        self.assertEqual(len(neuro),2)

    def test_priority_pagination_separate_signals_and_no_duplicate(self):
        self.record(pid=2,day=DAY,glicemia_jejum=250,pressao_sistolica=180,peso=140)
        self.record(pid=3,day=DAY-timedelta(days=8),glicemia_jejum=180)
        self.record(pid=5,day=DAY-timedelta(days=8),glicemia_jejum=90)
        first=cockpit(self.db,self.user,0,2,DAY)
        second=cockpit(self.db,self.user,2,2,DAY)
        self.assertEqual(first['pagination']['total'],3)
        self.assertEqual([p['id'] for p in first['pacientes_criticos']+second['pacientes_criticos']],[2,3,5])
        self.assertEqual(first['pacientes_criticos'][1]['sinais'],['CONTINUIDADE_CRITICA','RISCO_CLINICO_MODERADO'])
        self.assertEqual(first['indicadores']['baixo'],1)
        self.assertEqual(first['continuidade']['CRITICA'],2)
        self.assertTrue(all(e['care_line']=='CARDIO' for e in first['recent_activity']))
        self.assertFalse(any(k in first['capabilities'] for k in ('pts','agenda','sessions','care_plan')))

    def test_recent_limit_matches_institutional_global_order(self):
        from app.services.cardio_longitudinal import CARDIO_TIMELINE_SOURCES
        from app.services.timeline.models import event_order_key
        for i in range(35):
            self.record(pid=2 if i%2 else 3, day=DAY-timedelta(days=i%6), glicemia_jejum=180)
        expected=[]
        for pid in (2,3):
            expected.extend(TimelineService.get_events(self.db,TimelineQuery(pid,scope=TimelineScope.CARE_LINE,
                requested_care_line='CARDIO'),sources=CARDIO_TIMELINE_SOURCES))
        expected.sort(key=event_order_key)
        actual=TimelineService.get_recent_events(self.db,[2,3],CARDIO,10,sources=CARDIO_TIMELINE_SOURCES)
        self.assertEqual(actual,expected[:10])

    def test_population_queries_constant_with_patient_count(self):
        self.record(glicemia_jejum=180)
        def count():
            statements=[]
            def track(conn,cursor,statement,parameters,context,executemany): statements.append(statement)
            event.listen(self.engine,'before_cursor_execute',track)
            try: result=cockpit(self.db,self.user,0,20,DAY)
            finally: event.remove(self.engine,'before_cursor_execute',track)
            return len(statements),result
        small,_=count()
        for pid in range(10,60):
            self.db.add(Paciente(id=pid,nome='Synthetic '+str(pid),clinica_id=1,ativo=True));self.db.flush()
            self.db.add(PacienteModulo(paciente_id=pid,modulo_id=2,ativo=True))
            self.record(pid=pid,glicemia_jejum=180)
        large,result=count()
        self.assertEqual(small,large)
        print("Gate3 query budget:", self.engine.dialect.name, "3 patients =", small, "queries; 53 patients =", large, "queries")
        self.assertLessEqual(large,20)
        self.assertEqual(result['pagination']['total'],51)
        self.assertEqual(len(result['pacientes_criticos']),20)


@unittest.skipUnless(os.getenv('CARDIO_GATE3_POSTGRES_URL'),'Requires disposable Gate 3 PostgreSQL')
class PostgresJourneyTests(JourneyTests):
    postgres_url=os.getenv('CARDIO_GATE3_POSTGRES_URL')
