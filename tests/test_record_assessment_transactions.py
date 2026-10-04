"""W1C-J1 transaction ownership, using the current schema on disposable PG18."""
import os
import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from alembic import command
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import test_contextual_clinical_schema as physical
from test_m0_baseline import config
from app.models.avaliacao_clinica import AvaliacaoClinica
from app.services import registros_longitudinais as records
from app.services.clinical_engine import assessment_service as assessments
from app.services.clinical_engine.assessment_builder import AssessmentBuilder
from app.services.clinical_engine.assessment_repository import AssessmentRepository


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class TransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        physical.PhysicalTests.setUpClass.__func__(cls)
        with cls.engine.begin() as c:
            command.upgrade(config(c), 'head')

    tearDownClass = classmethod(physical.PhysicalTests.tearDownClass.__func__)
    seed = physical.PhysicalTests.seed
    insert = physical.PhysicalTests.insert

    def setUp(self):
        with self.engine.begin() as c:
            self.seed(c)
            c.execute(text("UPDATE formularios_modulo SET tipo='ASSESSMENT',codigo='MCHAT',nome='M-CHAT' WHERE id=:f"), dict(f=self.form))
            self.fields = [c.execute(text("INSERT INTO campos_formulario(formulario_id,nome_campo,label,tipo_campo) VALUES (:f,:n,:n,'texto') RETURNING id"), dict(f=self.form,n=name)).scalar_one() for name in ('mchat_1','mchat_2')]
        # Text queries in AssessmentBuilder do not autoflush pending ORM answers.
        self.db = Session(self.engine, autoflush=False)
        self.payload = SimpleNamespace(paciente_id=self.patient,modulo_id=self.modules[0],
            formulario_id=self.form,data_registro=date(2026,1,1),origem='PROFISSIONAL',
            respostas=[SimpleNamespace(campo_id=f,valor=v) for f,v in zip(self.fields,('NAO','SIM'))])

    def tearDown(self):
        self.db.close()

    def counts(self, connection=None):
        if connection is None:
            with self.engine.connect() as c:
                return self.counts(c)
        # Count answers independently of the root join, so orphan answers cannot hide.
        params = dict(p=self.patient,f1=self.fields[0],f2=self.fields[1])
        return tuple(connection.execute(text(sql),params).scalar_one() for sql in (
            'SELECT count(*) FROM registros_longitudinais WHERE paciente_id=:p',
            'SELECT count(*) FROM respostas_registro WHERE campo_id IN (:f1,:f2)',
            'SELECT count(*) FROM avaliacoes_clinicas WHERE paciente_id=:p'))

    def test_legacy_record_and_assessment_keep_default_commits_and_result(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            record=records.criar_registro_longitudinal(self.db,self.payload)
        self.assertEqual(commit.call_count,2)  # Historical root commit, then assessment commit.
        self.assertIsNotNone(record.id)
        self.assertIsNone(record.contexto_assistencial_id)
        self.assertEqual(self.counts(),(1,2,1))
        assessment=self.db.query(AvaliacaoClinica).filter_by(registro_id=record.id).one()
        self.assertEqual(assessment.score,1)
        self.assertEqual(assessment.resultado['instrumento_label'],'M-CHAT')

    def test_legacy_assessment_failure_keeps_historical_record_behavior(self):
        error=RuntimeError('synthetic legacy assessment failure')
        with patch.object(records,'executar_avaliacao_por_registro',side_effect=error), patch('builtins.print') as output, patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            record=records.criar_registro_longitudinal(self.db,self.payload)
        self.assertIsNotNone(record.id)
        self.assertEqual(commit.call_count,1)
        output.assert_called_once_with('Erro ao executar assessment: synthetic legacy assessment failure')
        self.assertEqual(self.counts(),(1,2,0))

    def test_non_assessment_record_does_not_invent_assessment_in_either_mode(self):
        self.db.execute(text("UPDATE formularios_modulo SET tipo='LONGITUDINAL' WHERE id=:f"),dict(f=self.form))
        self.db.commit()
        with patch.object(records,'executar_avaliacao_por_registro',side_effect=AssertionError('not an assessment')):
            with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
                records.criar_registro_longitudinal(self.db,self.payload,commit=False)
                commit.assert_not_called()
                self.assertEqual(self.counts(self.db),(1,2,0))
                self.assertEqual(self.counts(),(0,0,0))
                self.db.rollback()
                records.criar_registro_longitudinal(self.db,self.payload)
                self.assertEqual(commit.call_count,1)
        self.assertEqual(self.counts(),(1,2,0))

    def test_success_one_caller_commit_persists_whole_unit(self):
        self.db.begin()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            record=records.criar_registro_longitudinal(self.db,self.payload,commit=False)
            commit.assert_not_called(); rollback.assert_not_called()
            self.assertIsNone(record.contexto_assistencial_id)
            self.assertEqual(self.counts(self.db),(1,2,1))
            assessment=self.db.query(AvaliacaoClinica).filter_by(registro_id=record.id).one()
            self.assertEqual(assessment.score,1)  # Answers were flushed before raw SQL builder.
            self.assertEqual(self.counts(),(0,0,0))
            self.db.commit()
            self.assertEqual(commit.call_count,1)
        self.assertEqual(self.counts(),(1,2,1))

    def test_failure_before_assessment_rolls_back_root_and_answers(self):
        error=RuntimeError('before assessment')
        def fail(**kwargs):
            self.assertEqual(self.counts(self.db),(1,2,0))
            raise error
        with patch.object(records,'executar_avaliacao_por_registro',side_effect=fail):
            self.assert_caller_rollback(error)

    def assert_caller_rollback(self, error):
        self.db.begin()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            with self.assertRaises(type(error)) as caught:
                records.criar_registro_longitudinal(self.db,self.payload,commit=False)
            self.assertIs(caught.exception,error)
            commit.assert_not_called(); rollback.assert_not_called()
            self.db.rollback()
            self.assertEqual(rollback.call_count,1)
        self.assertEqual(self.counts(),(0,0,0))

    def test_failure_during_engine_propagates_and_rolls_back_everything(self):
        error=RuntimeError('during assessment')
        with patch.object(assessments,'executar_avaliacao_clinica',side_effect=error):
            self.assert_caller_rollback(error)

    def test_real_repository_flush_failure_leaves_no_partial_unit(self):
        # PostgreSQL rejects the required instrument; no simulated commit/DB success.
        with patch.object(assessments,'executar_avaliacao_clinica',return_value={'instrumento':None}), patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            with self.assertRaises(IntegrityError):
                records.criar_registro_longitudinal(self.db,self.payload,commit=False)
            commit.assert_not_called(); rollback.assert_not_called()
            self.db.rollback()
        self.assertEqual(self.counts(),(0,0,0))

    def test_failure_after_assessment_flush_before_caller_commit_rolls_back_all(self):
        self.db.begin()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            try:
                records.criar_registro_longitudinal(self.db,self.payload,commit=False)
                self.assertEqual(self.counts(self.db),(1,2,1))
                self.assertEqual(self.counts(),(0,0,0))
                commit.assert_not_called(); rollback.assert_not_called()
                raise RuntimeError('caller mandatory step failed')
            except RuntimeError:
                self.db.rollback()
            commit.assert_not_called()
            self.assertEqual(rollback.call_count,1)
        self.assertEqual(self.counts(),(0,0,0))

    def test_existing_record_primitive_and_assessment_service_compose_without_commit(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            record=records.persistir_registro_longitudinal(self.db,self.payload)
            result=assessments.executar_avaliacao_por_registro(self.db,record.id,'MCHAT',commit=False)
            self.assertGreater(result['avaliacao_id'],0)
            self.assertEqual(result['resultado']['score'],1)
            self.assertEqual(self.counts(self.db),(1,2,1))
            commit.assert_not_called(); rollback.assert_not_called()
            self.db.rollback()
        self.assertEqual(self.counts(),(0,0,0))

    def test_repository_flush_only_assigns_id_and_caller_can_rollback(self):
        record=records.persistir_registro_longitudinal(self.db,self.payload)
        self.db.flush()
        context=AssessmentBuilder.from_registro(self.db,record.id,'MCHAT')
        result=assessments.executar_avaliacao_clinica(context)
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            assessment=AssessmentRepository.salvar_avaliacao(self.db,context,result,commit=False)
            self.assertIsNotNone(assessment.id)
            self.assertIsNotNone(assessment.created_at)
            self.assertEqual(self.counts(self.db),(1,2,1))
            commit.assert_not_called(); rollback.assert_not_called()
        self.db.rollback()
        self.assertEqual(self.counts(),(0,0,0))

    def test_legacy_standalone_assessment_still_commits_and_returns_same_shape(self):
        record=records.persistir_registro_longitudinal(self.db,self.payload)
        self.db.commit()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            result=assessments.executar_avaliacao_por_registro(self.db,record.id,'MCHAT')
        self.assertEqual(commit.call_count,1)
        self.assertEqual(set(result),{'avaliacao_id','resultado'})
        self.assertEqual(result['resultado']['score'],1)
        self.assertEqual(self.counts(),(1,2,1))

    def test_instrument_name_fallback_remains_unchanged(self):
        self.db.execute(text('UPDATE formularios_modulo SET codigo=NULL WHERE id=:f'),dict(f=self.form))
        self.db.commit()
        records.criar_registro_longitudinal(self.db,self.payload,commit=False)
        self.assertEqual(self.db.query(AvaliacaoClinica).filter_by(paciente_id=self.patient).one().instrumento,'MCHAT')
        self.db.rollback()
        self.assertEqual(self.counts(),(0,0,0))

    def test_both_assessment_modes_keep_w1ci_contextual_absence(self):
        with self.engine.begin() as c:
            identity=self.insert(c,'registros_longitudinais')
        for commit_mode in (True,False):
            with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
                with self.assertRaises(ValueError):
                    assessments.executar_avaliacao_por_registro(self.db,identity,'MCHAT',commit=commit_mode)
                commit.assert_not_called()
            self.db.rollback()
        self.assertEqual(self.counts(),(1,0,0))
