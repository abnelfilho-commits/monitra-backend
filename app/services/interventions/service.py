"""Institutional authorization, resolution and transaction boundary."""
from contextlib import contextmanager
from app.core.acl import assert_clinica_access
from app.models.paciente import Paciente
from app.services.care_lines import care_line_resolver
from app.services.care_lines.exceptions import CareLineNotFound
from .adapters import GenericAdapter, CardioAdapter
from .models import InterventionSubmission, InterventionUpdate, SourceType
from .exceptions import (InterventionNotFound, InterventionIdentityConflict,
    InvalidInterventionPayload, InterventionOperationNotSupported)


class InterventionService:
    def __init__(self, resolver=None, adapters=None, line_sources=None):
        self.resolver = resolver or care_line_resolver
        self.registry = self.resolver.registry
        self.adapters = dict(adapters if adapters is not None else {
            SourceType.GENERIC_INTERVENTION: GenericAdapter(),
            SourceType.CARDIO_INTERVENTION: CardioAdapter()})
        self.line_sources = dict(line_sources if line_sources is not None else {
            'NEURO': SourceType.GENERIC_INTERVENTION, 'CARDIO': SourceType.CARDIO_INTERVENTION})

    @staticmethod
    @contextmanager
    def _transaction(db):
        try:
            yield
            db.commit()
        except Exception:
            db.rollback()
            raise

    def _adapter(self, source_type):
        adapter = self.adapters.get(source_type)
        if adapter is None:
            raise InterventionOperationNotSupported('Fonte de intervenção não suportada.')
        return adapter

    @staticmethod
    def _patient(db, patient_id, user):
        if patient_id is None:
            raise InterventionIdentityConflict('Intervenção sem paciente persistido.')
        patient = db.query(Paciente).filter(Paciente.id == patient_id).first()
        if patient is None:
            raise InterventionNotFound('Paciente não encontrado.')
        assert_clinica_access(user, patient.clinica_id)
        return patient

    def _resource(self, db, source_type, source_id, user, lock=False):
        adapter = self._adapter(source_type)
        raw = adapter.get(db, source_id, lock=lock)
        if raw is None:
            raise InterventionNotFound('Intervenção não encontrada.')
        record = adapter.to_record(raw, self.registry)
        self._patient(db, record.patient_id, user)
        return adapter, raw, record

    def create(self, db, submission, *, user):
        with self._transaction(db):
            if not isinstance(submission, InterventionSubmission) or submission.actor.id != user.id:
                raise InvalidInterventionPayload('Executor deve corresponder ao usuário autenticado.')
            patient = self._patient(db, submission.patient_id, user)
            line = self.resolver.resolve(db, patient.id, submission.requested_care_line, 'interventions')
            adapter = self._adapter(self.line_sources.get(line.code))
            raw = adapter.create(db, submission, line, user, patient)
            return adapter.to_record(raw, self.registry)

    def get(self, db, source_type, source_id, *, user):
        return self._resource(db, source_type, source_id, user)[2]

    def list_for_patient(self, db, patient_id, *, user, source_type=None, requested_care_line=None):
        self._patient(db, patient_id, user)
        line = None
        if requested_care_line is not None:
            line = self.registry.get(requested_care_line)
            if line is None:
                raise CareLineNotFound('Linha de cuidado não reconhecida pela aplicação.')
        adapters = [self._adapter(source_type)] if source_type is not None else self.adapters.values()
        result = []
        for adapter in adapters:
            for raw in adapter.list_for_patient(db, patient_id):
                record = adapter.to_record(raw, self.registry)
                if line is None or record.module_id == line.module_id:
                    result.append(record)
        # Source-local ordering is preserved; no invented common clinical timestamp.
        return result

    def update(self, db, source_type, source_id, changes, *, user, expected_patient_id=None):
        with self._transaction(db):
            adapter, raw, record = self._resource(db, source_type, source_id, user, lock=True)
            if record.source_type != SourceType.GENERIC_INTERVENTION:
                raise InterventionOperationNotSupported('Edição Cardio indisponível em V1.')
            if expected_patient_id is not None and expected_patient_id != record.patient_id:
                raise InterventionIdentityConflict('Paciente é imutável.')
            if not isinstance(changes, InterventionUpdate):
                raise InvalidInterventionPayload('Somente campos mutáveis são aceitos.')
            return adapter.to_record(adapter.update(db, raw, changes), self.registry)

    def delete(self, db, source_type, source_id, *, user):
        with self._transaction(db):
            adapter, raw, record = self._resource(db, source_type, source_id, user, lock=True)
            if record.source_type != SourceType.GENERIC_INTERVENTION:
                raise InterventionOperationNotSupported('Exclusão Cardio indisponível em V1.')
            adapter.delete(db, raw)
