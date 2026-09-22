import ast
import os
from pathlib import Path
import unittest
from dataclasses import fields, replace
from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.modular import (ModuloClinico, PacienteModulo, FormularioModulo,
                                CampoFormulario, RegistroLongitudinal, RespostaRegistro)
from app.services.care_lines import (NEURO, CARDIO, CareLineRegistry, CareLineResolver,
    CareLineCapabilityStatus as Status, AmbiguousCareLine, PatientCareLineNotFound,
    CareLineInactive, CareLineCapabilityNotSupported, CareLineNotFound)
from app.services.clinical_reading import ClinicalReading, ClinicalReadingService
from app.services.clinical_reading.providers.cardio import read_cardio
from app.services.clinical_reading.providers.neuro import read_neuro
from app.services import neuro_engine
from app.services.report_engine.providers.clinical_engine_provider import NeuroClinicalEngineProvider
from app.services.report_engine.context import ReportContext

DAY = date(2026, 1, 10)


def observation(**kwargs):
    values = dict(data=DAY, sono_qualidade=4, irritabilidade=1, crise_sensorial=0,
                  evacuacao=True, consistencia_fezes=4, tempo_tela='MENOS_1H',
                  seletividade_alimentar='NENHUMA', aceitou_alimento_novo=True,
                  observacao=None)
    values.update(kwargs)
    return SimpleNamespace(**values)


class ContractTests(unittest.TestCase):
    def test_identity_and_defaults(self):
        reading = ClinicalReading(10, NEURO, None, None, None, None)
        self.assertIs(reading.care_line, NEURO)
        self.assertEqual(reading.patient_id, 10)
        self.assertIsNone(reading.clinical_state)
        self.assertIsNone(reading.evidence)
        self.assertIsNone(reading.alerts)
        self.assertIsNone(reading.risk)
        self.assertIsNone(reading.trend)

    def test_metadata_isolation(self):
        source = {'nested': []}
        a = ClinicalReading(10, NEURO, None, None, None, None, source)
        b = ClinicalReading(10, NEURO, None, None, None, None, source)
        a.metadata['nested'].append(1)
        self.assertEqual(source, {'nested': []})
        self.assertEqual(b.metadata, source)
        c = ClinicalReading(10, NEURO, None, None, None, None)
        d = ClinicalReading(10, NEURO, None, None, None, None)
        c.metadata['x'] = 1
        self.assertEqual(d.metadata, {})

    def test_no_legacy_or_operational_calculation_dependencies(self):
        root = Path(__file__).resolve().parents[1] / 'app/services/clinical_reading'
        forbidden = ('routers', 'timeline', 'cockpit', 'risk_analytics', 'scripts',
                     'app.services.cardiometabolico')
        for path in root.rglob('*.py'):
            tree = ast.parse(path.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    modules = [node.module or ''] + [alias.name for alias in node.names]
                elif isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                else:
                    continue
                for module in modules:
                    self.assertFalse(any(module == item or module.startswith(item + '.')
                        or item in module.split('.') for item in forbidden), (path, module))

    def test_no_universal_score_or_protocol(self):
        names = {field.name for field in fields(ClinicalReading)}
        self.assertNotIn('score', names)
        self.assertNotIn('protocol', names)

    def test_resolved_line_and_clinical_date_required(self):
        with self.assertRaises(TypeError):
            ClinicalReading(10, 'NEURO', DAY, None, None, None)
        with self.assertRaises(TypeError):
            ClinicalReading(10, NEURO, datetime(2026, 1, 10), None, None, None)
        with self.assertRaises(TypeError):
            ClinicalReading(10, NEURO, None, None, None, None, metadata=None)
        with self.assertRaises(ValueError):
            ClinicalReading(0, NEURO, None, None, None, None)


class NeuroReadingTests(unittest.TestCase):
    def test_actual_engine_mapping(self):
        records = [observation(irritabilidade=3, crise_sensorial=2, sono_qualidade=1,
                   tempo_tela='MAIS_4H', observacao='crise sensorial') for _ in range(3)]
        records += [observation() for _ in range(3)]
        with patch.object(neuro_engine, 'obter_registros_neuro_paciente', return_value=records):
            raw = neuro_engine.analisar_paciente(None, 10)
            result = read_neuro(None, 10, NEURO)
        self.assertEqual(raw['risco_atual'], 'alto_risco')
        self.assertEqual(raw['tendencia'], 'piora')
        self.assertEqual(raw['momento_clinico']['status'], 'CRITICO')
        self.assertEqual(result.risk, raw['risco_atual'])
        self.assertEqual(result.trend, raw['tendencia'])
        self.assertEqual(result.clinical_state, raw['momento_clinico'])
        self.assertEqual(result.alerts, raw['alertas'])
        self.assertEqual(result.summary, raw['resumo_clinico'])
        self.assertEqual(result.reference_date, DAY)
        self.assertEqual(result.evidence['scope'], 'axis_analysis')
        for key in ('pontuacao_risco', 'protocolo', 'prioridade', 'eixo_dominante',
                    'painel_clinico', 'total_registros', 'status_resumido', 'interpretacao'):
            self.assertEqual(result.metadata[key], raw[key])
        result.clinical_state['status'] = 'changed'
        self.assertEqual(raw['momento_clinico']['status'], 'CRITICO')

    def test_no_records(self):
        with patch.object(neuro_engine, 'obter_registros_neuro_paciente', return_value=[]):
            result = read_neuro(None, 10, NEURO)
        self.assertEqual(result.risk, 'sem_dados')
        self.assertEqual(result.trend, 'sem_dados')
        self.assertEqual(result.clinical_state['status'], 'SEM_DADOS')
        self.assertIsNone(result.reference_date)
        self.assertIsNone(result.evidence)
        self.assertEqual(result.alerts, [])

    def test_raw_engine_and_report_boundary_preserved(self):
        for records in ([], [observation()], [observation(irritabilidade=3, crise_sensorial=2)]):
            with self.subTest(records=len(records)):
                with patch.object(neuro_engine, 'obter_registros_neuro_paciente', return_value=records):
                    raw = neuro_engine.analisar_paciente(None, 10)
                    self.assertEqual(ClinicalReadingService.get_neuro_reading(None, 10), raw)
                    self.assertEqual(ClinicalReadingService.build_report_context(None, 10, 'neuro'), raw)
                    # Exercise the actual unchanged Report Engine provider too.
                    context = ReportContext('CLN-001', 10, 1, DAY, DAY, module='NEURO', db=object())
                    with patch.object(ClinicalReadingService, 'get_reading', return_value=read_neuro(None, 10, NEURO)):
                        collected = NeuroClinicalEngineProvider().collect(context)
                    for key in raw:
                        self.assertEqual(collected.data.get(key), raw[key])
                    self.assertEqual(context.official_readings['NEURO'], collected.data)

    def test_no_cardio_report_support(self):
        with self.assertRaisesRegex(ValueError, 'Módulo clínico não suportado: CARDIO'):
            ClinicalReadingService.build_report_context(None, 10, 'CARDIO')

    def test_current_raw_characterization(self):
        with patch.object(neuro_engine, 'obter_registros_neuro_paciente', return_value=[observation()]):
            raw = neuro_engine.analisar_paciente(None, 10)
        self.assertEqual(raw['pontuacao_risco'], 0)
        self.assertEqual(raw['risco_atual'], 'baixo_risco')
        self.assertEqual(raw['tendencia'], 'sem_dados')
        self.assertEqual(raw['protocolo'], 'Acompanhamento de rotina')
        self.assertEqual(raw['prioridade'], 'BAIXA')
        self.assertEqual(raw['alertas'], [])
        self.assertEqual(raw['momento_clinico']['status'], 'ESTAVEL')
        self.assertEqual(raw['resumo_clinico'],
            'Os registros recentes sugerem estabilidade clínica relativa, sem sinais críticos predominantes.')


class DatabaseReadingTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        for model in (ModuloClinico, PacienteModulo, FormularioModulo, CampoFormulario,
                      RegistroLongitudinal, RespostaRegistro):
            model.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([ModuloClinico(id=line.module_id, nome=line.display_name,
                                      slug=line.slug, ativo=True) for line in (NEURO, CARDIO)])
        self.db.add_all([FormularioModulo(id=1, modulo_id=1, nome='Neuro', tipo='REGISTRO_DIARIO'),
                         FormularioModulo(id=2, modulo_id=2, nome='Cardio', tipo='REGISTRO_DIARIO'),
                         FormularioModulo(id=3, modulo_id=2, nome='Assessment', tipo='ASSESSMENT')])
        self.db.commit()
        self.service = ClinicalReadingService()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def link(self, module, active=True):
        self.db.add(PacienteModulo(paciente_id=10, modulo_id=module, ativo=active))
        self.db.commit()

    def record(self, values, day=DAY, form=2, module=2, patient=10):
        record = RegistroLongitudinal(paciente_id=patient, modulo_id=module, formulario_id=form,
                                      data_registro=day, origem='PROFISSIONAL')
        self.db.add(record)
        self.db.flush()
        for name, value in values.items():
            field = CampoFormulario(formulario_id=form, nome_campo=name, label=name, tipo_campo='TEST')
            self.db.add(field)
            self.db.flush()
            self.db.add(RespostaRegistro(registro_id=record.id, campo_id=field.id,
                       valor_numero=value if isinstance(value, (float, int)) else None,
                       valor_texto=value if isinstance(value, str) else None))
        self.db.commit()
        return record

    def test_neuro_resolution(self):
        self.link(1)
        with patch.object(neuro_engine, 'obter_registros_neuro_paciente', return_value=[]):
            self.assertIs(self.service.get_reading(self.db, 10).care_line, NEURO)

    def test_cardio_resolution(self):
        self.assertTrue(CARDIO.supports('clinical_reading'))
        self.assertEqual(CARDIO.capability_status('report'), Status.ACTIVE)
        self.assertEqual(CARDIO.capability_status('cockpit'), Status.ACTIVE)
        self.link(2)
        self.assertEqual(self.service.get_reading(self.db, 10).care_line.code, 'CARDIO')

    def test_ambiguous_and_explicit(self):
        self.link(1)
        self.link(2)
        with self.assertRaises(AmbiguousCareLine):
            self.service.get_reading(self.db, 10)
        self.assertEqual(self.service.get_reading(self.db, 10, 'cardiometabolico').care_line.code, 'CARDIO')

    def test_unlinked_and_unknown(self):
        self.link(1)
        with self.assertRaises(PatientCareLineNotFound):
            self.service.get_reading(self.db, 10, 'CARDIO')
        with self.assertRaises(CareLineNotFound):
            self.service.get_reading(self.db, 10, 'unknown')

    def test_inactive_link(self):
        self.link(2, active=False)
        with self.assertRaises(PatientCareLineNotFound):
            self.service.get_reading(self.db, 10, 2)

    def test_inactive_database_module(self):
        self.link(2)
        self.db.get(ModuloClinico, 2).ativo = False
        self.db.commit()
        with self.assertRaises(PatientCareLineNotFound):
            self.service.get_reading(self.db, 10, 2)

    def test_inactive_application_and_capability(self):
        self.link(2)
        for definition, error in (
            (replace(CARDIO, active=False), CareLineInactive),
            (replace(CARDIO, capabilities={'clinical_reading': Status.PLANNED}), CareLineCapabilityNotSupported),
            (replace(CARDIO, capabilities={}), CareLineCapabilityNotSupported),
        ):
            service = ClinicalReadingService(CareLineResolver(CareLineRegistry([definition])))
            with self.assertRaises(error):
                service.get_reading(self.db, 10, 2)

    def test_missing_provider(self):
        self.link(1)
        with self.assertRaises(CareLineCapabilityNotSupported):
            ClinicalReadingService(providers={}).get_reading(self.db, 10)

    def test_cardio_canonical_calculation(self):
        self.link(2)
        self.record({'glicemia_jejum': 180, 'pressao_sistolica': 160,
                     'pressao_diastolica': 100, 'peso': 120})
        reading = self.service.get_reading(self.db, 10)
        self.assertEqual(reading.metadata['score'], 8)
        self.assertEqual(reading.risk, 'alto')
        self.assertEqual(reading.metadata['protocol'], 'intensivo_cardiometabolico')
        self.assertEqual(reading.summary, 'Paciente apresenta hiperglicemia persistente, hipertensão importante, '
                         'obesidade severa, com necessidade de acompanhamento longitudinal contínuo.')
        self.assertIsNone(reading.trend)
        self.assertIsNone(reading.clinical_state)
        self.assertIsNone(reading.alerts)
        self.assertIsNone(reading.evidence)

    def test_cardio_no_record(self):
        reading = read_cardio(self.db, 10, CARDIO)
        self.assertIsNone(reading.risk)
        self.assertIsNone(reading.reference_date)
        self.assertIsNone(reading.summary)
        self.assertIsNone(reading.trend)

    def test_latest_daily_record_and_tie_break(self):
        self.record({'glicemia_jejum': 250}, day=date(2026, 1, 1))
        self.record({'glicemia_jejum': 250}, day=date(2026, 1, 11), form=3)
        self.record({'glicemia_jejum': 250}, day=date(2026, 1, 12), form=1, module=1)
        self.record({'glicemia_jejum': 250}, day=date(2026, 1, 13), patient=99)
        self.record({'glicemia_jejum': 250})
        latest = self.record({'glicemia_jejum': 100})
        reading = read_cardio(self.db, 10, CARDIO)
        self.assertEqual(reading.reference_date, DAY)
        self.assertEqual(reading.metadata['record_id'], latest.id)
        self.assertEqual(reading.risk, 'baixo')

    def test_empty_latest_does_not_fall_back(self):
        self.record({'glicemia_jejum': 250}, day=date(2026, 1, 1))
        self.record({})
        reading = read_cardio(self.db, 10, CARDIO)
        self.assertIsNone(reading.risk)
        self.assertEqual(reading.reference_date, DAY)
        self.assertEqual(reading.metadata['availability'], 'no_usable_answers')

    def test_bmi_and_old_observation_do_not_override(self):
        self.record({'glicemia_jejum': 250}, day=date(2020, 1, 1))
        self.record({'peso': 120, 'altura': 1.5}, day=date(2020, 1, 2))
        reading = read_cardio(self.db, 10, CARDIO)
        # BMI > 40 would produce alto in the legacy timeline. Engine score is 2.
        self.assertEqual(reading.risk, 'baixo')
        self.assertEqual(reading.metadata['score'], 2)
        self.assertIsNone(reading.trend)
        self.assertIsNone(reading.alerts)
        self.assertEqual(reading.reference_date, date(2020, 1, 2))

    def test_bmi_metadata_uses_same_observation_without_risk_change(self):
        for values, expected in (({'peso':82,'altura':1.75},26.8),({'peso':82},None),({'altura':1.75},None),({},None)):
            self.record(values)
            reading=read_cardio(self.db,10,CARDIO)
            self.assertEqual(reading.metadata['imc'],expected)
            self.assertEqual(reading.risk,'baixo' if 'peso' in values else None)
            self.assertNotIn('altura',reading.metadata['measurements'])
        self.assertIsNone(reading.trend)

    def test_unvalidated_engine_trend_not_called(self):
        self.record({'glicemia_jejum': 250})
        with patch('app.services.cardiometabolico_engine.calcular_tendencia', side_effect=AssertionError):
            self.assertIsNone(read_cardio(self.db, 10, CARDIO).trend)

    def test_invalid_numeric_answer_is_unavailable(self):
        self.record({'glicemia_jejum': 'not-a-number', 'peso': 120})
        reading = read_cardio(self.db, 10, CARDIO)
        self.assertIsNone(reading.risk)
        self.assertEqual(reading.metadata['availability'], 'invalid_answers')

    def test_duplicate_answers_are_unavailable(self):
        record = self.record({'glicemia_jejum': 100})
        field = self.db.query(CampoFormulario).first()
        self.db.add(RespostaRegistro(registro_id=record.id, campo_id=field.id, valor_numero=250))
        self.db.commit()
        self.assertIsNone(read_cardio(self.db, 10, CARDIO).risk)

    def test_wrong_form_answers_are_ignored(self):
        record = self.record({})
        field = CampoFormulario(formulario_id=1, nome_campo='glicemia_jejum', label='test', tipo_campo='TEST')
        self.db.add(field)
        self.db.flush()
        self.db.add(RespostaRegistro(registro_id=record.id, campo_id=field.id, valor_numero=250))
        self.db.commit()
        self.assertIsNone(read_cardio(self.db, 10, CARDIO).risk)


if __name__ == '__main__':
    unittest.main()
