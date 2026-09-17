"""Deterministic Wave 3 tests: synthetic persistence and failure injection."""
import ast
import os
import unittest
from dataclasses import fields, replace
from datetime import date
from pathlib import Path
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from uuid import uuid4
from app.models.modular import (ModuloClinico, PacienteModulo, FormularioModulo,
    CampoFormulario, RegistroLongitudinal, RespostaRegistro)
from app.services.care_lines import (CareOrigin, NEURO, CARDIO, AmbiguousCareLine,
    CareLineRegistry, CareLineResolver, CareLineCapabilityStatus, CareLineCapabilityNotSupported,
    PatientCareLineNotFound, CareLineInactive)
from app.services.daily_record import (ActorRef, ActorType, DailyRecordSubmission,
                                      DailyRecordResult, DailyRecordService)
from app.services.daily_record.exceptions import *
from app.services.daily_record.providers.neuro import FIELDS
from app.services.daily_record.providers.cardio import NUMERIC, TEXT
from app.services.daily_record.providers.common import resolve_form
from app.services.clinical_reading.providers.cardio import read_cardio
from app.services import cardiometabolico_engine as cardio_engine

DAY = date(2026, 1, 10)


class ContractTests(unittest.TestCase):
    def test_context(self):
        s = DailyRecordSubmission(10, 'NEURO', DAY, CareOrigin.PROFISSIONAL, ActorRef('PROFESSIONAL'))
        self.assertEqual(s.reference_date, DAY)
        self.assertNotEqual(s.actor.type.value, s.origin.value)
        self.assertNotIn('clinical_reading', {f.name for f in fields(DailyRecordResult)})

    def test_payload_isolated(self):
        source = {'nested': []}
        a = DailyRecordSubmission(10, None, DAY, 'SISTEMA', ActorRef('SYSTEM'), source)
        b = replace(a)
        a.payload['nested'].append(1)
        self.assertEqual(source, {'nested': []})
        self.assertEqual(b.payload, source)

    def test_invalid_context(self):
        with self.assertRaises(ValueError):
            ActorRef('RESPONSIBLE')
        with self.assertRaises(ValueError):
            ActorRef('SYSTEM', 1)
        with self.assertRaises(ValueError):
            DailyRecordSubmission(10, None, DAY, 'PROFISSIONAL', ActorRef('SYSTEM'))
        with self.assertRaises(TypeError):
            DailyRecordSubmission(10, None, DAY, 'SISTEMA', 10)

    def test_python39_syntax(self):
        root = Path(__file__).resolve().parents[1] / 'app/services/daily_record'
        for path in root.rglob('*.py'):
            ast.parse(path.read_text(), feature_version=(3, 9))


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        url = os.getenv('WAVE3_TEST_POSTGRES_URL')
        if url:
            if url != 'postgresql+psycopg2://wave3@127.0.0.1/wave3_test':
                raise RuntimeError('Only the isolated Wave 3 fixture database is allowed.')
            schema = 'wave3_' + uuid4().hex
            bootstrap = create_engine(url)
            with bootstrap.begin() as connection:
                connection.execute(text('CREATE SCHEMA ' + schema))
            bootstrap.dispose()
            self.engine = create_engine(url, connect_args={'options':'-csearch_path='+schema})
            with self.engine.begin() as connection:
                for table in ('pacientes', 'usuarios', 'responsaveis'):
                    connection.execute(text('CREATE TABLE '+table+' (id INTEGER PRIMARY KEY)'))
                connection.execute(text('INSERT INTO pacientes VALUES (10)'))
                connection.execute(text('INSERT INTO responsaveis VALUES (99)'))
        else:
            self.engine = create_engine('sqlite:///:memory:', poolclass=StaticPool,
                                        connect_args={'check_same_thread':False})
        for model in (ModuloClinico, PacienteModulo, FormularioModulo, CampoFormulario,
                      RegistroLongitudinal, RespostaRegistro):
            model.__table__.create(self.engine)
        with self.engine.begin() as connection:
            if url:
                connection.execute(text('ALTER TABLE respostas_registro ALTER COLUMN valor_numero TYPE numeric'))
            for name, kind in {'modulo':'TEXT', 'glicemia_jejum':'NUMERIC',
                'glicemia_pos_prandial':'NUMERIC', 'pressao_sistolica':'NUMERIC',
                'pressao_diastolica':'NUMERIC', 'peso':'NUMERIC', 'atividade_fisica':'TEXT',
                'sono':'TEXT', 'humor':'TEXT', 'score_clinico':'INTEGER', 'risco':'TEXT',
                'protocolo':'TEXT', 'leitura_clinica':'TEXT', 'observacoes':'TEXT'}.items():
                connection.execute(text('ALTER TABLE registros_longitudinais ADD COLUMN '+name+' '+kind))
        self.db = Session(self.engine)
        for line in (NEURO, CARDIO):
            self.db.add(ModuloClinico(id=line.module_id, nome=line.code, slug=line.slug, ativo=True))
            self.db.flush()
            self.db.add(PacienteModulo(paciente_id=10, modulo_id=line.module_id, ativo=True))
            self.db.add(FormularioModulo(id=line.module_id*100, modulo_id=line.module_id,
                nome=line.code, tipo='REGISTRO_DIARIO', ativo=True))
            self.db.flush()
            names = FIELDS if line == NEURO else sorted(NUMERIC | TEXT)
            for i, name in enumerate(names):
                self.db.add(CampoFormulario(id=line.module_id*1000+i,
                    formulario_id=line.module_id*100, nome_campo=name, label=name,
                    tipo_campo='texto', ativo=True))
        self.db.commit()
        self.service = DailyRecordService()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def submission(self, line='NEURO', payload=None, **kwargs):
        return DailyRecordSubmission(10, line, kwargs.pop('day', DAY),
            kwargs.pop('origin', CareOrigin.PROFISSIONAL),
            kwargs.pop('actor', ActorRef('PROFESSIONAL')), payload or {})

    def count(self):
        return self.db.query(RegistroLongitudinal).count(), self.db.query(RespostaRegistro).count()

    def test_neuro_values_and_identity(self):
        payload = dict(sono_qualidade=4, evacuacao=False, consistencia_fezes=None,
                       crise_sensorial=0, observacao='synthetic')
        with patch('app.services.neuro_engine.analisar_paciente', side_effect=AssertionError('must not run')):
            result = self.service.create(self.db, self.submission(payload=payload))
        self.assertIs(result.care_line, NEURO)
        self.assertEqual(result.reference_date, DAY)
        self.assertIsNotNone(result.created_at)
        self.assertEqual(self.count(), (1, 9))
        answer = self.db.query(RespostaRegistro).filter_by(campo_id=1000).one()
        self.assertEqual(answer.valor_numero, 4)

    def test_neuro_invalid_type_is_institutional(self):
        with self.assertRaises(InvalidDailyRecordPayload):
            self.service.create(self.db, self.submission(payload={'sono_qualidade':[]}))
        self.assertEqual(self.count(), (0, 0))

    def test_cardio_same_engine_and_reading(self):
        values = {'glicemia_jejum': 180, 'peso': 100, 'atividade_fisica': 'baixa', 'sono': 'ruim'}
        result = self.service.create(self.db, self.submission('CARDIO', values))
        row = self.db.execute(text('SELECT score_clinico, risco, protocolo, leitura_clinica FROM registros_longitudinais')).one()
        score = cardio_engine.calcular_score(values)
        self.assertEqual(tuple(row), (score, cardio_engine.classificar_risco(score),
            cardio_engine.definir_protocolo(score), cardio_engine.gerar_leitura_clinica(values, score)))
        reading = read_cardio(self.db, 10, CARDIO)
        self.assertEqual(reading.risk, row[1])
        self.assertIsNone(reading.trend)
        self.assertEqual(result.reference_date, reading.reference_date)

    def test_cardio_observations_are_exact_text_not_engine_input(self):
        narrative = "  Synthetic observation\nsecond line  "
        values = {'glicemia_jejum':180,'peso':100}
        with patch.object(cardio_engine,'calcular_score',wraps=cardio_engine.calcular_score) as score, \
             patch.object(cardio_engine,'gerar_leitura_clinica',wraps=cardio_engine.gerar_leitura_clinica) as summary:
            self.service.create(self.db,self.submission('CARDIO',dict(values,observacoes=narrative)))
            self.assertEqual(score.call_args.args[0],values)
            self.assertEqual(summary.call_args.args[0],values)
        row=self.db.execute(text('SELECT observacoes,score_clinico FROM registros_longitudinais')).one()
        self.assertEqual(row[0],narrative)
        self.assertEqual(row[1],cardio_engine.calcular_score(values))
        self.assertEqual(self.db.query(CampoFormulario).filter_by(nome_campo='observacoes').count(),0)
        self.assertEqual(self.db.query(RespostaRegistro).count(),2)
        self.assertNotIn('observacoes',read_cardio(self.db,10,CARDIO).metadata['measurements'])

    def test_observations_only_do_not_fabricate_interpretation(self):
        with patch.object(cardio_engine,'calcular_score',side_effect=AssertionError('text is not clinical evidence')):
            self.service.create(self.db,self.submission('CARDIO',{'observacoes':'Synthetic text'}))
        row=self.db.execute(text('SELECT observacoes,score_clinico,risco,protocolo,leitura_clinica FROM registros_longitudinais')).one()
        self.assertEqual(tuple(row),('Synthetic text',None,None,None,None))
        self.assertIsNone(read_cardio(self.db,10,CARDIO).risk)
        self.assertIsNone(read_cardio(self.db,10,CARDIO).trend)

    def test_observation_update_preserves_omitted_and_accepts_explicit_clear(self):
        record=self.service.create(self.db,self.submission('CARDIO',{'observacoes':'original','peso':90}))
        self.service.update(self.db,record.record_id,self.submission('CARDIO',{'peso':95}))
        self.assertEqual(self.db.execute(text('SELECT observacoes FROM registros_longitudinais')).scalar(),'original')
        self.service.update(self.db,record.record_id,self.submission('CARDIO',{'observacoes':None,'peso':95}))
        self.assertIsNone(self.db.execute(text('SELECT observacoes FROM registros_longitudinais')).scalar())

    def test_observation_invalid_type_rolls_back(self):
        with self.assertRaises(InvalidDailyRecordPayload):
            self.service.create(self.db,self.submission('CARDIO',{'observacoes':{'invalid':'value'}}))
        self.assertEqual(self.count(),(0,0))

    def test_cardio_no_data(self):
        self.service.create(self.db, self.submission('CARDIO'))
        self.assertIsNone(self.db.execute(text('SELECT risco FROM registros_longitudinais')).scalar())
        self.assertIsNone(read_cardio(self.db, 10, CARDIO).risk)

    def test_cardio_threshold_input_is_not_rounded(self):
        values = {'glicemia_jejum':179.999}
        self.service.create(self.db, self.submission('CARDIO', values))
        score = self.db.execute(text('SELECT score_clinico FROM registros_longitudinais')).scalar()
        self.assertEqual(score, cardio_engine.calcular_score(values))
        if self.engine.dialect.name == 'postgresql':
            self.assertEqual(read_cardio(self.db, 10, CARDIO).metadata['score'], score)

    def test_same_named_foreign_field_is_ignored(self):
        self.db.add(CampoFormulario(id=9999, formulario_id=200, nome_campo='sono_qualidade',
                                   label='foreign', tipo_campo='texto', ativo=True))
        self.db.commit()
        self.service.create(self.db, self.submission(payload={'sono_qualidade':4}))
        self.assertEqual(self.db.query(RespostaRegistro).filter_by(campo_id=9999).count(), 0)

    def test_assessment_legacy_commit_and_hook_preserved(self):
        from types import SimpleNamespace
        from app.services.registros_longitudinais import criar_registro_longitudinal
        self.db.add(FormularioModulo(id=300, modulo_id=1, nome='synthetic',
            tipo='ASSESSMENT', codigo='TEST', ativo=True))
        self.db.commit()
        with patch('app.services.registros_longitudinais.executar_avaliacao_por_registro') as assess:
            record = criar_registro_longitudinal(self.db, SimpleNamespace(paciente_id=10,
                modulo_id=1, formulario_id=300, data_registro=DAY, origem='PROFISSIONAL', respostas=[]))
            assess.assert_called_once_with(db=self.db, registro_id=record.id, instrumento='TEST')
        self.assertEqual(self.count(), (1, 0))

    def test_resolution(self):
        with self.assertRaises(AmbiguousCareLine):
            self.service.create(self.db, self.submission(None))
        self.assertEqual(self.count(), (0, 0))
        for line in ('NEURO', 'CARDIO'):
            self.assertEqual(self.service.create(self.db, self.submission(line)).care_line.code, line)

    def test_inactive_link(self):
        self.db.query(PacienteModulo).filter_by(modulo_id=1).update({'ativo':False})
        self.db.commit()
        with self.assertRaises(PatientCareLineNotFound):
            self.service.create(self.db, self.submission())

    def test_inactive_definition_and_capability(self):
        for definition, error in ((replace(NEURO, active=False), CareLineInactive),
            (replace(NEURO, capabilities={'daily_record':CareLineCapabilityStatus.PLANNED}), CareLineCapabilityNotSupported)):
            service = DailyRecordService(resolver=CareLineResolver(CareLineRegistry([definition])))
            with self.assertRaises(error):
                service.create(self.db, self.submission())

    def test_ambiguous_form(self):
        self.db.add(FormularioModulo(id=999, modulo_id=1, nome='duplicate', tipo='REGISTRO_DIARIO', ativo=True))
        self.db.commit()
        with self.assertRaises(AmbiguousDailyRecordForm):
            self.service.create(self.db, self.submission())

    def test_missing_active_form(self):
        self.db.query(FormularioModulo).filter_by(id=100).update({'ativo':False})
        self.db.commit()
        with self.assertRaises(DailyRecordFormNotFound):
            self.service.create(self.db, self.submission())

    def test_foreign_form_field_cannot_substitute(self):
        self.db.query(CampoFormulario).filter_by(id=1000).update({'formulario_id':200})
        self.db.commit()
        with self.assertRaises(InvalidDailyRecordPayload):
            self.service.create(self.db, self.submission())
        self.assertEqual(self.count(), (0, 0))

    def test_no_aliases(self):
        for name in ('uso_medicacao', 'qualidade_sono', 'adesao_alimentar'):
            with self.assertRaises(InvalidDailyRecordPayload):
                self.service.create(self.db, self.submission('CARDIO', {name:'x'}))

    def test_commit_once(self):
        with patch.object(self.db, 'commit', wraps=self.db.commit) as commit:
            self.service.create(self.db, self.submission('CARDIO', {'peso':100}))
            self.assertEqual(commit.call_count, 1)

    def test_providers_do_not_commit(self):
        with patch.object(self.db, 'commit', side_effect=AssertionError('provider commit')):
            for line in (NEURO, CARDIO):
                provider = self.service.providers[line.code]
                provider.prepare(self.db, line, self.submission(line.code))

    def test_provider_failure_rollback(self):
        with patch.object(self.service.providers['NEURO'], 'prepare', side_effect=RuntimeError), \
             patch.object(self.db, 'rollback', wraps=self.db.rollback) as rollback:
            with self.assertRaises(RuntimeError):
                self.service.create(self.db, self.submission())
            self.assertEqual(rollback.call_count, 1)
        self.assertEqual(self.count(), (0, 0))

    def test_answer_failure_rolls_back(self):
        add = self.db.add
        def fail_answer(obj):
            if isinstance(obj, RespostaRegistro):
                raise RuntimeError('synthetic answer failure')
            return add(obj)
        with patch.object(self.db, 'add', side_effect=fail_answer):
            with self.assertRaises(RuntimeError):
                self.service.create(self.db, self.submission())
        self.assertEqual(self.count(), (0, 0))

    def test_projection_failure_rolls_back(self):
        with patch.object(self.service.providers['CARDIO'], 'persist_projection', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.service.create(self.db, self.submission('CARDIO', {'peso':100}))
        self.assertEqual(self.count(), (0, 0))

    def test_failure_after_projection_sql_rolls_back_all(self):
        provider = self.service.providers['CARDIO']
        original = provider.persist_projection
        def fail_after_sql(db, record_id, projection):
            original(db, record_id, projection)
            raise RuntimeError('failure after projection SQL')
        with patch.object(provider, 'persist_projection', side_effect=fail_after_sql):
            with self.assertRaises(RuntimeError):
                self.service.create(self.db, self.submission('CARDIO', {'peso':100}))
        self.assertEqual(self.count(), (0, 0))

    def test_commit_failure_rolls_back(self):
        with patch.object(self.db, 'commit', side_effect=RuntimeError('commit failure')):
            with self.assertRaises(RuntimeError):
                self.service.create(self.db, self.submission('CARDIO', {'peso':100}))
        self.assertEqual(self.count(), (0, 0))

    def test_update_synchronizes_and_clears(self):
        result = self.service.create(self.db, self.submission('CARDIO', {'peso':140, 'sono':'ruim'}))
        self.service.update(self.db, result.record_id, self.submission('CARDIO', {'peso':60}))
        row = self.db.execute(text('SELECT peso, sono, score_clinico FROM registros_longitudinais')).one()
        self.assertEqual(tuple(row), (60, None, 0))
        self.assertEqual(self.count(), (1, 1))
        self.service.update(self.db, result.record_id, self.submission('CARDIO'))
        self.assertIsNone(self.db.execute(text('SELECT risco FROM registros_longitudinais')).scalar())

    def test_update_failure_preserves_previous_record(self):
        result = self.service.create(self.db, self.submission('CARDIO', {'peso':140}))
        with patch.object(self.service.providers['CARDIO'], 'persist_projection', side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.service.update(self.db, result.record_id, self.submission('CARDIO', {'peso':60}))
        self.assertEqual(self.db.query(RespostaRegistro).one().valor_numero, 140)
        self.assertEqual(self.db.execute(text('SELECT peso FROM registros_longitudinais')).scalar(), 140)

    def test_immutable_identity(self):
        result = self.service.create(self.db, self.submission())
        with self.assertRaises(DailyRecordIdentityConflict):
            self.service.update(self.db, result.record_id, self.submission('CARDIO'))
        self.db.query(FormularioModulo).filter_by(id=100).update({'ativo':False})
        self.db.add(FormularioModulo(id=101, modulo_id=1, nome='new', tipo='REGISTRO_DIARIO', ativo=True))
        self.db.query(CampoFormulario).filter_by(formulario_id=100).update({'formulario_id':101})
        self.db.commit()
        with self.assertRaises(DailyRecordIdentityConflict):
            self.service.update(self.db, result.record_id, self.submission())

    def test_responsible_date_duplicate_actor(self):
        submission = self.submission(day=date.today(), origin=CareOrigin.RESPONSAVEL_APP,
                                     actor=ActorRef('RESPONSIBLE', 99))
        result = self.service.create(self.db, submission)
        record = self.db.query(RegistroLongitudinal).one()
        self.assertEqual(record.criado_por_responsavel_id, 99)
        self.assertEqual(record.origem, 'RESPONSAVEL_APP')
        self.assertEqual(result.origin, CareOrigin.RESPONSAVEL_APP)
        with self.assertRaises(DuplicateDailyRecord):
            self.service.create(self.db, submission)
        with self.assertRaises(InvalidDailyRecordPayload):
            self.service.create(self.db, replace(submission, reference_date=DAY))


if __name__ == '__main__':
    unittest.main()
