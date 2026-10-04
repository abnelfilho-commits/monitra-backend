"""W1C-J2: internal diagnosis persistence, never an authorization entry point."""
import os
import unittest
from datetime import date
from unittest.mock import patch

from alembic import command
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import test_contextual_clinical_schema as physical
from test_m0_baseline import config
from app.schemas.diagnostico import DiagnosticoCreate, DiagnosticoUpdate
from app.services.diagnostico_service import DiagnosticoService as Service


@unittest.skipUnless(os.getenv('M0_TEST_POSTGRES_URL'), 'Disposable PostgreSQL 18 required')
class DiagnosisTransactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        physical.PhysicalTests.setUpClass.__func__(cls)
        with cls.engine.begin() as c:
            command.upgrade(config(c),'head')

    tearDownClass=classmethod(physical.PhysicalTests.tearDownClass.__func__)
    seed=physical.PhysicalTests.seed

    def setUp(self):
        with self.engine.begin() as c:
            self.seed(c)
        self.db=Session(self.engine)
        self.identity=dict(contexto_assistencial_id=self.contexts[0],paciente_id=self.patient,modulo_id=self.modules[0])

    def tearDown(self):
        self.db.close()

    def payload(self, **changes):
        return DiagnosticoCreate(**dict(dict(paciente_id=self.patient,care_line='NEURO',
            descricao_clinica='Synthetic diagnosis',medico_nome='Synthetic physician',
            data_diagnostico=date(2026,1,1)),**changes))

    def create(self, **changes):
        return Service._criar_contextual(self.db,self.payload(),**dict(
            dict(contexto_assistencial_id=self.contexts[0],modulo_id=self.modules[0]),**changes))

    def persisted(self):
        with self.engine.connect() as c:
            return c.execute(text('SELECT id,contexto_assistencial_id,paciente_id,modulo_id,status,descricao_clinica FROM diagnosticos WHERE paciente_id=:p ORDER BY id'),dict(p=self.patient)).all()

    def seed_diagnosis(self):
        record=self.create()
        identity=record.id
        self.db.commit()
        return identity

    def absent(self, call):
        with self.assertRaises(HTTPException) as caught:
            call()
        self.assertEqual(caught.exception.status_code,404)
        self.db.rollback()

    def test_legacy_create_commits_and_never_accepts_context_from_payload(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            row=Service.criar(self.db,self.payload(contexto_assistencial_id=self.contexts[0]),self.modules[0])
        self.assertEqual(commit.call_count,1)
        self.assertIsNone(row.contexto_assistencial_id)
        self.assertEqual(len(self.persisted()),1)
        self.assertIsNone(self.persisted()[0].contexto_assistencial_id)

    def test_legacy_create_and_mutations_can_be_caller_owned(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit,patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            row=Service.criar(self.db,self.payload(),self.modules[0],commit=False)
            Service.atualizar(self.db,row.id,DiagnosticoUpdate(observacoes='Synthetic'),commit=False)
            Service.revisar(self.db,row.id,commit=False)
            Service.cancelar(self.db,row.id,commit=False)
            self.assertEqual(row.status,'CANCELADO')
            self.assertIsNone(row.contexto_assistencial_id)
            commit.assert_not_called();rollback.assert_not_called()
        self.assertEqual(self.persisted(),[])
        self.db.rollback()
        self.assertEqual(self.persisted(),[])

    def test_legacy_mutations_preserve_default_commit_and_lifecycle(self):
        row=Service.criar(self.db,self.payload(),self.modules[0])
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.assertEqual(Service.atualizar(self.db,row.id,DiagnosticoUpdate(descricao_clinica='Updated')).descricao_clinica,'Updated')
            self.assertEqual(Service.revisar(self.db,row.id).status,'REVISADO')
            self.assertEqual(Service.cancelar(self.db,row.id).status,'CANCELADO')
            self.assertEqual(commit.call_count,3)
            for operation in (Service.cancelar,Service.revisar):
                with self.assertRaises(HTTPException) as caught:operation(self.db,row.id)
                self.assertEqual(caught.exception.status_code,409)
            self.assertEqual(commit.call_count,3)
        self.assertEqual(self.persisted()[0].status,'CANCELADO')

    def test_contextual_create_flush_then_rollback_leaves_no_row(self):
        self.db.begin()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit,patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            row=self.create()
            self.assertGreater(row.id,0)
            self.assertEqual(row.contexto_assistencial_id,self.contexts[0])
            self.assertEqual(self.persisted(),[])
            commit.assert_not_called();rollback.assert_not_called()
            self.db.rollback()
            self.assertEqual(rollback.call_count,1)
        self.assertEqual(self.persisted(),[])

    def test_contextual_create_one_caller_commit_preserves_exact_identity(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            row=self.create()
            identity=row.id
            commit.assert_not_called()
            self.db.commit()
            self.assertEqual(commit.call_count,1)
        self.assertEqual(tuple(self.persisted()[0][:4]),(identity,self.contexts[0],self.patient,self.modules[0]))

    def test_context_patient_mismatch_rejected_by_existing_fk(self):
        with self.assertRaises(IntegrityError) as caught:
            Service._criar_contextual(self.db,self.payload(paciente_id=self.other),contexto_assistencial_id=self.contexts[0],modulo_id=self.modules[0])
        self.assertEqual(caught.exception.orig.pgcode,'23503')
        self.db.rollback()
        self.assertEqual(self.persisted(),[])
        with self.engine.connect() as c:
            self.assertEqual(c.execute(text('SELECT count(*) FROM diagnosticos WHERE paciente_id=:p'),dict(p=self.other)).scalar(),0)

    def test_context_line_mismatch_rejected_by_existing_fk(self):
        with self.assertRaises(IntegrityError) as caught:self.create(modulo_id=self.modules[2])
        self.assertEqual(caught.exception.orig.pgcode,'23503')
        self.db.rollback()
        self.assertEqual(self.persisted(),[])

    def test_context_must_be_explicit_never_null_or_inferred(self):
        for context in (None,0,True,'1'):
            with self.subTest(context=context),self.assertRaises(ValueError):
                self.create(contexto_assistencial_id=context)
        with self.assertRaises(TypeError):
            Service._criar_contextual(self.db,self.payload(),modulo_id=self.modules[0])
        self.assertEqual(self.persisted(),[])

    def test_update_rejects_every_identity_field_even_null_or_same_value(self):
        identity=self.seed_diagnosis()
        before=self.persisted()
        for field,other in (('contexto_assistencial_id',self.contexts[1]),('paciente_id',self.other),('modulo_id',self.modules[1])):
            for value in (None,other,self.identity[field]):
                with self.subTest(field=field,value=value),self.assertRaises(ValueError):
                    Service._atualizar_contextual(self.db,identity,{'descricao_clinica':'Forbidden',field:value},**self.identity)
                self.db.rollback()
                self.assertEqual(self.persisted(),before)

    def test_wrong_expected_scope_is_not_found_and_cannot_move_resource(self):
        identity=self.seed_diagnosis()
        before=self.persisted()
        for field,other in (('contexto_assistencial_id',self.contexts[1]),('paciente_id',self.other),('modulo_id',self.modules[1])):
            scope=dict(self.identity,**{field:other})
            for action in (lambda:Service._atualizar_contextual(self.db,identity,{'descricao_clinica':'Forbidden'},**scope),
                           lambda:Service._cancelar_contextual(self.db,identity,**scope),
                           lambda:Service._revisar_contextual(self.db,identity,**scope)):
                self.absent(action)
                self.assertEqual(self.persisted(),before)

    def test_contextual_update_flush_and_rollback_preserve_previous_state(self):
        identity=self.seed_diagnosis()
        before=self.persisted()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit,patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            row=Service._atualizar_contextual(self.db,identity,{'descricao_clinica':'Updated','cid':None},**self.identity)
            self.assertEqual(row.descricao_clinica,'Updated')
            self.assertEqual(row.contexto_assistencial_id,self.contexts[0])
            commit.assert_not_called();rollback.assert_not_called()
            self.assertEqual(self.persisted(),before)
            self.db.rollback()
        self.assertEqual(self.persisted(),before)

    def test_contextual_update_preserves_existing_field_and_status_validation(self):
        identity=self.seed_diagnosis()
        before=self.persisted()
        for changes in ({'status':'NEW_STATE'},{'descricao_clinica':''},{'id':123}):
            with self.assertRaises((ValueError,ValidationError)):
                Service._atualizar_contextual(self.db,identity,changes,**self.identity)
            self.db.rollback()
            self.assertEqual(self.persisted(),before)
        Service._atualizar_contextual(self.db,identity,{'descricao_clinica':'Updated'},**self.identity)
        self.db.commit()
        self.assertEqual(self.persisted()[0].descricao_clinica,'Updated')
        self.assertEqual(tuple(self.persisted()[0][:4]),tuple(before[0][:4]))

    def test_lifecycle_flush_rollback_commit_and_existing_conflicts(self):
        identity=self.seed_diagnosis()
        before=self.persisted()
        for operation,status in ((Service._revisar_contextual,'REVISADO'),(Service._cancelar_contextual,'CANCELADO')):
            with patch.object(self.db,'commit',wraps=self.db.commit) as commit,patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
                row=operation(self.db,identity,**self.identity)
                self.assertEqual(row.status,status)
                self.assertEqual((row.contexto_assistencial_id,row.paciente_id,row.modulo_id),(self.contexts[0],self.patient,self.modules[0]))
                commit.assert_not_called();rollback.assert_not_called()
                self.assertEqual(self.persisted(),before)
                self.db.rollback()
            self.assertEqual(self.persisted(),before)
        Service._revisar_contextual(self.db,identity,**self.identity);self.db.commit()
        self.assertEqual(self.persisted()[0].status,'REVISADO')
        Service._cancelar_contextual(self.db,identity,**self.identity);self.db.commit()
        self.assertEqual(self.persisted()[0].status,'CANCELADO')
        for operation in (Service._cancelar_contextual,Service._revisar_contextual):
            with self.assertRaises(HTTPException) as caught:operation(self.db,identity,**self.identity)
            self.assertEqual(caught.exception.status_code,409)
            self.db.rollback()
        self.assertEqual(tuple(self.persisted()[0][:4]),tuple(before[0][:4]))

    def test_legacy_cannot_acquire_or_mutate_contextual_even_without_commit(self):
        identity=self.seed_diagnosis()
        before=self.persisted()
        self.assertEqual(Service.listar_por_paciente(self.db,self.patient),[])
        self.db.rollback()
        self.absent(lambda:Service.buscar_por_id(self.db,identity))
        for commit in (True,False):
            for action in (lambda:Service.atualizar(self.db,identity,DiagnosticoUpdate(descricao_clinica='Forbidden'),commit=commit),
                           lambda:Service.cancelar(self.db,identity,commit=commit),
                           lambda:Service.revisar(self.db,identity,commit=commit)):
                self.absent(action)
                self.assertEqual(self.persisted(),before)

    def test_contextual_primitives_cannot_convert_legacy_row(self):
        row=Service.criar(self.db,self.payload(),self.modules[0])
        identity=row.id
        self.db.rollback()
        before=self.persisted()
        for action in (lambda:Service._atualizar_contextual(self.db,identity,{'observacoes':'Forbidden'},**self.identity),
                       lambda:Service._cancelar_contextual(self.db,identity,**self.identity),
                       lambda:Service._revisar_contextual(self.db,identity,**self.identity)):
            self.absent(action)
            self.assertEqual(self.persisted(),before)
