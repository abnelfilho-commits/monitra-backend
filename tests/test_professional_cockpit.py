"""Explicit-line cockpit gate on disposable PostgreSQL; no shared database."""
import os
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from test_whatsapp_security import LocalClient
from urllib.parse import urlsplit, parse_qsl

class TestClient(LocalClient):
    def get(self, path, params=None):
        url=urlsplit(path)
        return super().get(url.path, params=params or dict(parse_qsl(url.query, keep_blank_values=True)))
from sqlalchemy import event
import test_cardio_longitudinal as fixture
import test_report_multiline as report_fixture
from app.models import (Paciente, PacienteModulo, ProfissionalModulo, Profissional,
                        ModuloClinico, Intervencao, Diagnostico, AvaliacaoClinica,
                        CampoFormulario, RespostaRegistro)
from app.routers.cockpit import router, get_db, get_usuario_atual
from app.services.cockpit_profissional_service import CockpitProfissionalService as Cockpit
from app.services.patient_line_service import list_patients
from app.services.clinical_reading import ClinicalReadingService
from app.services.care_lines import care_line_registry
from app.services.timeline import sources, professional_activity
from app.services import neuro_engine, cardio_longitudinal


@unittest.skipUnless(os.environ.get('CARDIO_GATE3_POSTGRES_URL'), 'Disposable PostgreSQL required')
class ProfessionalCockpitTests(unittest.TestCase):
    postgres_url = os.environ.get('CARDIO_GATE3_POSTGRES_URL')
    tearDown = fixture.JourneyTests.tearDown
    record = fixture.JourneyTests.record
    seed_neuro = report_fixture.ReportTests.seed_neuro

    def setUp(self):
        fixture.JourneyTests.setUp(self)
        app=FastAPI(); app.include_router(router)
        app.dependency_overrides[get_db]=lambda:self.db
        app.dependency_overrides[get_usuario_atual]=lambda:self.user
        self.client=TestClient(app)

    def get(self,line,**kwargs):
        return Cockpit.get_cockpit(self.db,self.user,line,**kwargs)

    def test_required_explicit_context_even_single_line(self):
        self.db.query(ProfissionalModulo).filter_by(modulo_id=2).delete();self.db.commit()
        self.assertEqual(self.client.get('/cockpit/profissional').status_code,422)
        self.assertEqual(self.client.get('/cockpit/profissional?care_line=').status_code,422)

    def test_single_line_access_both_directions(self):
        for allowed,denied in ((1,2),(2,1)):
            self.db.query(ProfissionalModulo).delete()
            self.db.add(ProfissionalModulo(profissional_id=1,modulo_id=allowed));self.db.commit()
            self.assertEqual(self.client.get('/cockpit/profissional',params={'care_line':allowed}).status_code,200)
            self.assertEqual(self.client.get('/cockpit/profissional',params={'care_line':denied}).status_code,403)

    def test_unknown_inactive_and_professional_boundaries(self):
        self.assertEqual(self.client.get('/cockpit/profissional?care_line=999').status_code,400)
        module=self.db.get(ModuloClinico,2);module.ativo=False;self.db.commit()
        self.assertEqual(self.client.get('/cockpit/profissional?care_line=2').status_code,400)
        module.ativo=True;self.db.get(Profissional,1).ativo=False;self.db.commit()
        self.assertEqual(self.client.get('/cockpit/profissional?care_line=1').status_code,403)
        self.db.get(Profissional,1).ativo=True;self.db.commit()
        self.user.clinica_id=2
        self.assertEqual(self.client.get('/cockpit/profissional?care_line=1').status_code,403)
        self.user.clinica_id=None
        self.assertEqual(self.client.get('/cockpit/profissional?care_line=1').status_code,403)

    def test_population_equals_institutional_listing_without_owner_filter(self):
        for line in (1,2):
            self.assertEqual(self.get(line)['total_pacientes'],len(list_patients(self.db,self.user,line)))
        self.assertEqual(self.get(1)['total_pacientes'],2)
        self.assertEqual(self.get(2)['total_pacientes'],3)
        self.db.get(Paciente,2).ativo=False
        self.db.query(PacienteModulo).filter_by(paciente_id=5,modulo_id=2).update({'ativo':False})
        self.db.commit()
        self.assertEqual(self.get(2)['total_pacientes'],1)
        self.assertEqual([p.id for p in list_patients(self.db,self.user,2)],[3])

    def test_cardio_reuses_approved_composition_never_executes_neuro(self):
        self.record(glicemia_jejum=250,pressao_sistolica=180,peso=140)
        with patch.object(neuro_engine,'analisar_paciente',side_effect=AssertionError('Neuro called')), \
             patch.object(neuro_engine,'analisar_registros',side_effect=AssertionError('Neuro called')):
            expected=cardio_longitudinal.cockpit(self.db,self.user,0,5)
            result=self.get(2)
        self.assertEqual(result['composition'],expected)
        self.assertEqual(result['pacientes_prioritarios'][0]['id'],3)
        self.assertEqual(result['pacientes_prioritarios'][0]['risco'],'critico')
        self.assertIsNone(result['pacientes_prioritarios'][0]['tendencia'])

    def test_empty_observations_no_fabricated_priority(self):
        for line in (1,2):
            response=self.get(line)
            self.assertEqual(response['pacientes_prioritarios'],[])
            self.assertEqual(response['atividades_recentes'],[])

    def neuro_record(self,pid,day):
        record=self.record(pid=pid,mid=1,day=day)
        for name,value in (('sono_qualidade',1),('irritabilidade',4),('crise_sensorial',4),('consistencia_fezes',1)):
            field=self.db.query(CampoFormulario).filter_by(formulario_id=1,nome_campo=name).first()
            if field is None:
                field=CampoFormulario(formulario_id=1,nome_campo=name,label=name,tipo_campo='numero',ativo=True)
                self.db.add(field);self.db.flush()
            self.db.add(RespostaRegistro(registro_id=record.id,campo_id=field.id,valor_numero=value))
        self.db.commit()
        return record

    def test_neuro_batch_equals_individual_engine_and_priority(self):
        self.neuro_record(1,fixture.DAY)
        self.neuro_record(3,fixture.DAY)
        self.neuro_record(3,fixture.DAY-timedelta(days=1))
        self.record(pid=3,mid=2,glicemia_jejum=250)
        service=ClinicalReadingService()
        batch=service.get_readings(self.db,[1,3],1)
        for pid in (1,3):
            self.assertEqual(batch[pid],service.get_reading(self.db,pid,1))
            raw=neuro_engine.analisar_paciente(self.db,pid)
            self.assertEqual(batch[pid].risk,raw['risco_atual'])
            self.assertEqual(batch[pid].trend,raw['tendencia'])
            self.assertEqual(batch[pid].alerts,raw['alertas'])
        expected=sorted([1,3],key=lambda pid:(batch[pid].metadata['pontuacao_risco'],batch[pid].metadata['total_registros']),reverse=True)
        self.assertEqual([r['paciente_id'] for r in self.get(1)['pacientes_prioritarios']],expected)
        self.assertEqual(self.get(1,offset=1,limit=1)['pacientes_prioritarios'][0]['paciente_id'],expected[1])

    def test_every_neuro_activity_source_filters_own_line(self):
        self.seed_neuro()
        for mid in (1,2):
            record=self.record(mid=mid)
            self.db.add(Intervencao(paciente_id=3,modulo_id=mid,tipo='Synthetic',descricao='Line '+str(mid),data_intervencao=datetime.combine(fixture.DAY,datetime.min.time())))
            self.db.add(Diagnostico(paciente_id=3,modulo_id=mid,data_diagnostico=fixture.DAY,descricao_clinica='Line '+str(mid),status='ATIVO',medico_nome='Synthetic'))
            self.db.add(AvaliacaoClinica(paciente_id=3,modulo_id=mid,registro_id=record.id,instrumento='Synthetic',score=1))
        self.db.commit()
        patients=list_patients(self.db,self.user,1)
        for collector in professional_activity.COLLECTORS:
            with self.subTest(collector=str(collector)):
                events=collector(self.db,[3],care_line_registry,module_id=1,limit=15)
                self.assertTrue(events)
                self.assertTrue(all(e.care_line.module_id==1 for e in events))
                with patch.object(professional_activity,'COLLECTORS',(collector,)):
                    result=professional_activity.recent_neuro_activity(self.db,patients,care_line_registry.get(1),care_line_registry)
                self.assertEqual(len(result),1)
                self.assertEqual(result[0]['paciente_id'],3)
                self.assertEqual(result[0]['care_line'],'NEURO')
        result=self.get(1)['atividades_recentes']
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]['paciente_id'],3)
        # Same identity, independently scoped Cardio output.
        cardio=self.get(2)['atividades_recentes']
        self.assertTrue(cardio)
        self.assertNotIn('M-CHAT',str(cardio))
        self.assertNotIn('DENVER',str(cardio))

    def test_cardio_all_activity_sources_and_cross_clinic_exclusion(self):
        from sqlalchemy import text
        from app.services.timeline.models import SourceType
        for pid,mid in ((3,1),(3,2),(4,2)):
            self.record(pid=pid,mid=mid)
            self.db.add(Intervencao(paciente_id=pid,modulo_id=mid,tipo='Synthetic',descricao='Synthetic',data_intervencao=datetime.combine(fixture.DAY,datetime.min.time())))
            self.db.add(Diagnostico(paciente_id=pid,modulo_id=mid,data_diagnostico=fixture.DAY,descricao_clinica='Synthetic',status='ATIVO',medico_nome='Synthetic'))
        self.db.execute(text("INSERT INTO intervencoes_cardiometabolicas (id,paciente_id,modulo_id,tipo,descricao,created_at) VALUES (1,3,2,'Synthetic','Synthetic',CURRENT_TIMESTAMP),(2,4,2,'Synthetic','Synthetic',CURRENT_TIMESTAMP)"))
        self.db.commit()
        events=self.get(2)['atividades_recentes']
        self.assertEqual(len(events),4)
        self.assertEqual({e['patient_id'] for e in events},{3})
        self.assertEqual({e['care_line'] for e in events},{'CARDIO'})
        self.assertEqual({e['id'].split(':')[0] for e in events},
            {SourceType.LONGITUDINAL_RECORD.value,SourceType.GENERIC_INTERVENTION.value,
             SourceType.CARDIO_INTERVENTION.value,SourceType.DIAGNOSIS.value})
        self.db.query(PacienteModulo).filter_by(paciente_id=3,modulo_id=2).update({'ativo':False})
        self.db.commit()
        self.assertEqual(self.get(2)['atividades_recentes'],[])

    def test_clinical_interpretation_code_unchanged_by_cockpit(self):
        # Raw engine and institutional batch must agree for absence as well as
        # observed data; no low/stable substitutions in the composition.
        raw=neuro_engine.analisar_paciente(self.db,1)
        reading=ClinicalReadingService().get_readings(self.db,[1],1)[1]
        self.assertEqual(reading.risk,raw['risco_atual'])
        self.assertEqual(reading.trend,raw['tendencia'])
        self.assertIsNone(reading.reference_date)
        self.assertEqual(reading.clinical_state,raw['momento_clinico'])

    def test_query_budget_constant_for_population_growth(self):
        self.record(mid=1);self.record(mid=2)
        def count(line):
            calls=[]
            def capture(*args): calls.append(1)
            event.listen(self.engine,'before_cursor_execute',capture)
            try: self.get(line)
            finally: event.remove(self.engine,'before_cursor_execute',capture)
            return len(calls)
        small={line:count(line) for line in (1,2)}
        for pid in range(100,150):
            self.db.add(Paciente(id=pid,nome='Synthetic '+str(pid),clinica_id=1,ativo=True))
            self.db.flush()
            for mid in (1,2): self.db.add(PacienteModulo(paciente_id=pid,modulo_id=mid,ativo=True))
        self.db.commit()
        large={line:count(line) for line in (1,2)}
        self.assertEqual(small,large)
        self.assertLessEqual(max(large.values()),22)
        print('Professional cockpit PostgreSQL query budget:',small,'->',large,'after 50 additional patients')
