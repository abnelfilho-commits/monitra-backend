"""Wave 5 deterministic contracts, persistence, authorization and failure tests."""
import ast
import os
import unittest
from dataclasses import fields, replace
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.models import Clinica, Paciente, Profissional, Usuario, Intervencao, OcupacaoProfissional
from app.models.modular import ModuloClinico, PacienteModulo
from app.models.profissional_modulo import ProfissionalModulo
from sqlalchemy.exc import IntegrityError
from app.services.care_lines import (NEURO, CARDIO, CareLineRegistry, CareLineResolver,
    CareLineCapabilityStatus, AmbiguousCareLine, CareLineInactive,
    PatientCareLineNotFound, CareLineCapabilityNotSupported, CareLineNotFound)
from app.services.interventions import InterventionService, InterventionSubmission, InterventionUpdate
from app.services.interventions.models import ActorRef, InterventionRecord, SourceType, CareLineAssociation
from app.services.interventions.exceptions import *

G = SourceType.GENERIC_INTERVENTION
C = SourceType.CARDIO_INTERVENTION
DAY = datetime(2026, 1, 10, 13, 45)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:', poolclass=StaticPool,
                                    connect_args={'check_same_thread': False})
        for model in (Clinica, OcupacaoProfissional, Profissional, Usuario, Paciente,
                      ModuloClinico, PacienteModulo, ProfissionalModulo, Intervencao):
            model.__table__.create(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text('''CREATE TABLE intervencoes_cardiometabolicas (
                id INTEGER PRIMARY KEY, paciente_id INTEGER NOT NULL, modulo_id INTEGER NOT NULL, profissional_id INTEGER,
                tipo VARCHAR(100) NOT NULL, descricao TEXT, prioridade VARCHAR(30) DEFAULT 'moderada',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)'''))
        self.db = Session(self.engine)
        self.db.add_all([Clinica(id=1, nome='Synthetic'), Clinica(id=2, nome='Other')])
        self.db.add(Profissional(id=700, nome='Synthetic', clinica_id=1, ativo=True))
        self.db.add(Usuario(id=50, nome='Synthetic', email='test@example.invalid', senha_hash='unused',
                            clinica_id=1, profissional_id=700, ativo=True))
        for pid, clinic in ((10,1),(11,1),(20,2)):
            self.db.add(Paciente(id=pid, nome='Synthetic', clinica_id=clinic, ativo=True))
        for line in (NEURO, CARDIO):
            self.db.add(ModuloClinico(id=line.module_id, nome=line.code, slug=line.slug, ativo=True))
        for pid, module in ((10,1),(11,2),(20,1),(20,2)):
            self.db.add(PacienteModulo(paciente_id=pid, modulo_id=module, ativo=True))
        self.db.add_all([ProfissionalModulo(profissional_id=700, modulo_id=i) for i in (1,2)])
        self.db.commit()
        self.user = SimpleNamespace(id=50, perfil='PROFISSIONAL', clinica_id=1, profissional_id=700)
        self.service = InterventionService()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def submit(self, patient=10, line=None, **changes):
        defaults = dict(patient_id=patient, requested_care_line=line,
            actor=ActorRef('PROFESSIONAL', self.user.id), type='authored', narrative='Synthetic',
            reference_datetime=DAY)
        defaults.update(changes)
        return InterventionSubmission(**defaults)

    def cardio(self, **changes):
        return self.service.create(self.db, self.submit(11, 'CARDIO', reference_datetime=None, **changes), user=self.user)

    def generic(self):
        return self.service.create(self.db, self.submit(), user=self.user)

    def historical(self, module=1, patient=10):
        row = Intervencao(paciente_id=patient, profissional_id=50, modulo_id=module,
                          tipo='historical', descricao='Synthetic', data_intervencao=DAY)
        self.db.add(row)
        self.db.commit()
        return row.id


class ContractTests(unittest.TestCase):
    def test_payload_and_metadata_isolation(self):
        original = {'nested': []}
        a = InterventionSubmission(1,None,ActorRef('PROFESSIONAL',2),'type',payload=original)
        b = replace(a)
        a.payload['nested'].append(1)
        self.assertEqual(original, {'nested': []})
        self.assertEqual(b.payload, original)
        record = InterventionRecord(G,1,1,NEURO,1,CareLineAssociation.EXPLICIT,
            None,'type',None,None,None)
        other = replace(record)
        record.metadata['x'] = 1
        self.assertEqual(other.metadata, {})

    def test_identity_and_content_validation(self):
        for values in ({'patient_id':0}, {'actor':ActorRef('PROFESSIONAL')},
                       {'actor':ActorRef('SYSTEM')}, {'type':3}, {'reference_datetime':'today'}):
            args = dict(patient_id=1,requested_care_line=None,actor=ActorRef('PROFESSIONAL',2),type='type')
            args.update(values)
            with self.assertRaises(InvalidInterventionPayload):
                InterventionSubmission(**args)
        with self.assertRaises(InvalidInterventionPayload):
            InterventionUpdate('type', None, None)

    def test_contract_excludes_clinical_interpretation_and_mutable_identity(self):
        self.assertEqual({f.name for f in fields(InterventionUpdate)}, {'type','narrative','reference_datetime'})
        for model in (InterventionSubmission, InterventionRecord):
            self.assertFalse({'risk','score','trend','protocol','clinical_state'} & {f.name for f in fields(model)})

    def test_python39_and_no_engine_or_commit_in_adapters(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root/'app/services/interventions').glob('*.py'):
            ast.parse(path.read_text(), feature_version=(3,9))
        source = (root/'app/services/interventions/adapters.py').read_text()
        for token in ('.commit(', '.rollback(', 'ClinicalReading', 'calcular_score'):
            self.assertNotIn(token, source)


class PersistenceTests(Fixture):
    def test_generic_auto_resolve_and_durable_reread(self):
        r = self.generic()
        self.db.expire_all()
        read = self.service.get(self.db,G,r.source_id,user=self.user)
        self.assertEqual(read.module_id,1)
        self.assertEqual(read.care_line,NEURO)
        self.assertEqual(read.care_line_association,CareLineAssociation.EXPLICIT)
        self.assertEqual(read.actor,{'namespace':'usuarios','id':50})
        self.assertEqual(read.reference_datetime,DAY)
        self.assertIsNotNone(read.created_at)

    def test_multi_line_explicit_and_ambiguous(self):
        self.db.add(PacienteModulo(paciente_id=10,modulo_id=2,ativo=True)); self.db.commit()
        with self.assertRaises(AmbiguousCareLine):
            self.generic()
        r=self.service.create(self.db,self.submit(line='NEURO'),user=self.user)
        self.assertEqual(r.module_id,1)

    def test_unlinked_and_unknown(self):
        for line,error in (('CARDIO',PatientCareLineNotFound),('missing',CareLineNotFound)):
            with self.assertRaises(error):
                self.service.create(self.db,self.submit(line=line),user=self.user)

    def test_inactive_definition_and_capability(self):
        for line,error in ((replace(NEURO,active=False),CareLineInactive),
            (replace(NEURO,capabilities={'interventions':CareLineCapabilityStatus.PLANNED}),CareLineCapabilityNotSupported)):
            service=InterventionService(resolver=CareLineResolver(CareLineRegistry([line])))
            with self.assertRaises(error):
                service.create(self.db,self.submit(line='NEURO'),user=self.user)

    def test_inactive_database_module_and_link(self):
        for model in (ModuloClinico,PacienteModulo):
            row=self.db.query(model).filter(model.id==1).one(); row.ativo=False; self.db.commit()
            with self.assertRaises(PatientCareLineNotFound): self.generic()
            row=self.db.query(model).filter(model.id==1).one(); row.ativo=True; self.db.commit()

    def test_null_line_is_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            self.historical(module=None)
        self.db.rollback()

    def test_unknown_module_is_not_readable(self):
        with self.assertRaises(InvalidInterventionPayload):
            self.service.get(self.db,G,self.historical(module=999),user=self.user)

    def test_orphan_is_not_an_institutional_resource(self):
        identity=self.historical(patient=None)
        with self.assertRaises(InterventionIdentityConflict):
            self.service.get(self.db,G,identity,user=self.user)

    def test_existing_read_and_update_do_not_require_active_links(self):
        r=self.generic()
        self.db.query(PacienteModulo).delete(); self.db.commit()
        self.assertEqual(self.service.get(self.db,G,r.source_id,user=self.user).module_id,1)
        with self.assertRaises(HTTPException):
            self.service.update(self.db,G,r.source_id,InterventionUpdate('edit',None,DAY),user=self.user)

    def test_generic_rejects_missing_date_and_specialized_payload(self):
        for changes in ({'reference_datetime':None},{'payload':{'priority':'alta'}}):
            with self.assertRaises(InvalidInterventionPayload):
                self.service.create(self.db,self.submit(**changes),user=self.user)

    def test_actor_spoof_rejected(self):
        with self.assertRaises(InvalidInterventionPayload):
            self.service.create(self.db,self.submit(actor=ActorRef('PROFESSIONAL',999)),user=self.user)
        with self.assertRaises(InvalidInterventionPayload):
            self.cardio(payload={'profissional_id':999})

    def test_cardio_uses_distinct_professional_id_and_priority(self):
        r=self.cardio(payload={'priority':'alta'})
        read=self.service.get(self.db,C,r.source_id,user=self.user)
        self.assertEqual(read.actor,{'namespace':'profissionais','id':700})
        self.assertEqual(read.metadata,{'priority':'alta'})
        self.assertEqual(read.care_line,CARDIO)
        self.assertEqual(read.care_line_association,CareLineAssociation.EXPLICIT)
        self.assertIsNone(read.reference_datetime)
        self.assertIsNotNone(read.created_at)

    def test_cardio_no_professional_admin(self):
        self.user=SimpleNamespace(id=50,perfil='ADMIN',clinica_id=None,profissional_id=None)
        record = self.cardio()
        self.assertEqual(record.care_line, CARDIO)
        self.assertIsNone(record.actor)

    def test_cardio_no_professional_same_clinic(self):
        self.user.profissional_id=None
        with self.assertRaises(HTTPException): self.cardio()

    def test_cardio_invalid_professional(self):
        for field,value in (('ativo',False),('clinica_id',2)):
            row=self.db.get(Profissional,700); setattr(row,field,value); self.db.commit()
            with self.assertRaises(HTTPException): self.cardio()
            row=self.db.get(Profissional,700); setattr(row,field,True if field=='ativo' else 1); self.db.commit()
        self.user.profissional_id=999
        with self.assertRaises(HTTPException): self.cardio()

    def test_cardio_rejects_clinical_date(self):
        with self.assertRaises(InvalidInterventionPayload):
            self.service.create(self.db,self.submit(11,'CARDIO'),user=self.user)

    def test_update_only_content_preserves_identity_and_author(self):
        r=self.generic()
        self.user.id=60
        changes=InterventionUpdate('new type',None,datetime(2025,2,3,4,5))
        result=self.service.update(self.db,G,r.source_id,changes,user=self.user,expected_patient_id=10)
        for field in ('source_type','source_id','patient_id','module_id','actor','created_at'):
            self.assertEqual(getattr(result,field),getattr(r,field))
        self.assertEqual(result.type,changes.type)
        self.assertIsNone(result.narrative)
        self.assertEqual(result.reference_datetime,changes.reference_datetime)

    def test_update_legacy_null_preserves_uncertainty(self):
        identity=self.historical()
        r=self.service.update(self.db,G,identity,InterventionUpdate('edit','new',DAY),user=self.user)
        self.assertEqual(r.module_id,1)
        self.assertEqual(r.care_line_association,CareLineAssociation.EXPLICIT)

    def test_patient_reassignment_and_untyped_mutation_rejected(self):
        r=self.generic()
        with self.assertRaises(InterventionIdentityConflict):
            self.service.update(self.db,G,r.source_id,InterventionUpdate('edit',None,DAY),user=self.user,expected_patient_id=11)
        with self.assertRaises(InvalidInterventionPayload):
            self.service.update(self.db,G,r.source_id,{'module_id':2},user=self.user)

    def test_delete_and_missing(self):
        r=self.generic()
        self.service.delete(self.db,G,r.source_id,user=self.user)
        with self.assertRaises(InterventionNotFound): self.service.get(self.db,G,r.source_id,user=self.user)

    def test_cardio_mutations_unsupported(self):
        r=self.cardio()
        with self.assertRaises(InterventionOperationNotSupported):
            self.service.update(self.db,C,r.source_id,InterventionUpdate('x',None,DAY),user=self.user)
        with self.assertRaises(InterventionOperationNotSupported):
            self.service.delete(self.db,C,r.source_id,user=self.user)

    def test_list_source_and_historical_line_filters(self):
        explicit=self.generic(); legacy=self.historical()
        self.assertEqual(len(self.service.list_for_patient(self.db,10,user=self.user,source_type=G)),2)
        result=self.service.list_for_patient(self.db,10,user=self.user,requested_care_line='NEURO')
        self.assertEqual([r.source_id for r in result],[explicit.source_id, legacy])
        with self.assertRaises(HTTPException):
            self.service.list_for_patient(self.db,10,user=self.user,requested_care_line='missing')

    def test_all_operations_clinic_acl_and_admin(self):
        generic=self.generic(); cardio=self.cardio()
        operations=[lambda:self.generic(),lambda:self.cardio(),
            lambda:self.service.get(self.db,G,generic.source_id,user=self.user),
            lambda:self.service.list_for_patient(self.db,10,user=self.user,source_type=G),
            lambda:self.service.list_for_patient(self.db,11,user=self.user,source_type=C),
            lambda:self.service.update(self.db,G,generic.source_id,InterventionUpdate('edit',None,DAY),user=self.user),
            lambda:self.service.delete(self.db,G,generic.source_id,user=self.user)]
        for role in ('PROFISSIONAL','ADMIN_CLINICA'):
            self.user.perfil=role; self.user.clinica_id=2
            for operation in operations:
                with self.assertRaises(HTTPException) as caught: operation()
                self.assertEqual(caught.exception.status_code,403)
        self.user.perfil='ADMIN'; self.user.profissional_id=None
        for operation in operations: operation()

    def test_authorization_uses_persisted_patient_before_payload(self):
        identity=self.historical(patient=20)
        with self.assertRaises(HTTPException) as caught:
            self.service.update(self.db,G,identity,InterventionUpdate('edit',None,DAY),user=self.user,expected_patient_id=10)
        self.assertEqual(caught.exception.status_code,403)

    def test_one_commit_materialized_return(self):
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit, patch.object(self.db,'refresh',side_effect=AssertionError('post-commit refresh')):
            r=self.generic()
            self.assertEqual(commit.call_count,1)
        self.db.close()
        self.assertEqual(r.actor['id'],50)
        self.assertIsNotNone(r.created_at)

    def test_adapter_error_rolls_back_flushed_insert(self):
        adapter=self.service.adapters[G]
        create=adapter.create
        def fail(*args):
            create(*args)
            raise RuntimeError('synthetic failure')
        with patch.object(adapter,'create',side_effect=fail), patch.object(self.db,'rollback',wraps=self.db.rollback) as rollback:
            with self.assertRaises(RuntimeError): self.generic()
            self.assertEqual(rollback.call_count,1)
        self.assertEqual(self.db.query(Intervencao).count(),0)

    def test_commit_failure_rolls_back(self):
        with patch.object(self.db,'commit',side_effect=RuntimeError('synthetic commit failure')):
            with self.assertRaises(RuntimeError): self.generic()
        self.assertEqual(self.db.query(Intervencao).count(),0)

    def test_failed_update_rolls_back_content(self):
        r=self.generic()
        with patch.object(self.db,'commit',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                self.service.update(self.db,G,r.source_id,InterventionUpdate('bad',None,DAY),user=self.user)
        self.assertEqual(self.service.get(self.db,G,r.source_id,user=self.user).type,r.type)

    def test_future_line_uses_generic_adapter_without_service_change(self):
        future=replace(NEURO,code='FUTURE',slug='future',module_id=3)
        self.db.add(ModuloClinico(id=3,nome='Future',slug='future',ativo=True))
        self.db.add(PacienteModulo(paciente_id=10,modulo_id=3,ativo=True))
        self.db.add(ProfissionalModulo(profissional_id=700,modulo_id=3)); self.db.commit()
        service=InterventionService(resolver=CareLineResolver(CareLineRegistry([NEURO,CARDIO,future])),
            line_sources={'NEURO':G,'CARDIO':C,'FUTURE':G})
        r=service.create(self.db,self.submit(line='FUTURE'),user=self.user)
        self.assertEqual(service.get(self.db,G,r.source_id,user=self.user).care_line,future)

    def test_missing_adapter_never_persists(self):
        service=InterventionService(line_sources={})
        with self.assertRaises(InterventionOperationNotSupported):
            service.create(self.db,self.submit(),user=self.user)
        self.assertEqual(self.db.query(Intervencao).count(),0)

    def test_list_generic_order_unchanged(self):
        first=self.generic()
        second=self.service.create(self.db,self.submit(reference_datetime=datetime(2025,1,1)),user=self.user)
        result=self.service.list_for_patient(self.db,10,user=self.user,source_type=G)
        self.assertEqual([r.source_id for r in result],[first.source_id,second.source_id])

    def test_update_and_delete_commit_once(self):
        r=self.generic()
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.service.update(self.db,G,r.source_id,InterventionUpdate('edit','new',DAY),user=self.user)
            self.assertEqual(commit.call_count,1)
        with patch.object(self.db,'commit',wraps=self.db.commit) as commit:
            self.service.delete(self.db,G,r.source_id,user=self.user)
            self.assertEqual(commit.call_count,1)

    def test_cardio_materialization_failure_rolls_back_insert(self):
        with patch.object(self.service.adapters[C],'to_record',side_effect=RuntimeError('synthetic result failure')):
            with self.assertRaises(RuntimeError): self.cardio()
        self.assertEqual(self.db.execute(text('SELECT COUNT(*) FROM intervencoes_cardiometabolicas')).scalar(),0)

    def test_unavailable_capability_and_unknown_source(self):
        line=replace(NEURO,capabilities={'interventions':CareLineCapabilityStatus.UNAVAILABLE})
        service=InterventionService(resolver=CareLineResolver(CareLineRegistry([line])))
        with self.assertRaises(CareLineCapabilityNotSupported):
            service.create(self.db,self.submit(),user=self.user)
        with self.assertRaises(InterventionOperationNotSupported):
            self.service.get(self.db,'not-a-source',1,user=self.user)
