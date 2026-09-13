"""Synthetic SQLAlchemy fixtures; never connect to an operational database."""
import os
import unittest
from dataclasses import replace
from datetime import date

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.models.modular import ModuloClinico, PacienteModulo
from app.services.care_lines import (
    CARDIO, NEURO, AmbiguousCareLine, CareContext, CareOrigin,
    CareLineCapabilityNotSupported, CareLineCapabilityStatus as Status,
    CareLineInactive, CareLineNotFound, CareLineRegistry, CareLineResolver,
    PatientCareLineNotFound,
)


class RegistryTests(unittest.TestCase):
    def test_aliases(self):
        registry = CareLineRegistry()
        for line in (NEURO, CARDIO):
            for alias in (line.code, line.slug, line.module_id, str(line.module_id),
                          ' ' + line.code.lower() + ' '):
                with self.subTest(alias=alias):
                    self.assertIs(registry.get(alias), line)

    def test_unknown_and_invalid(self):
        for alias in ('unknown', '', 99, True, None, '²'):
            self.assertIsNone(CareLineRegistry().get(alias))

    def test_empty_registry(self):
        self.assertEqual(tuple(CareLineRegistry([]).all()), ())

    def test_collisions_rejected(self):
        for line in (NEURO, replace(CARDIO, slug='neuro'),
                     replace(CARDIO, module_id=1), replace(CARDIO, code='1')):
            with self.assertRaises(ValueError):
                CareLineRegistry([NEURO, line])

    def test_capability_status_and_immutability(self):
        source = {'active': Status.ACTIVE, 'planned': Status.PLANNED,
                  'unavailable': Status.UNAVAILABLE}
        line = replace(NEURO, capabilities=source)
        source['active'] = Status.PLANNED
        self.assertTrue(line.supports('active'))
        for name in ('planned', 'unavailable', 'missing'):
            self.assertFalse(line.supports(name))
        self.assertEqual(line.capability_status('missing'), Status.UNAVAILABLE)
        with self.assertRaises(TypeError):
            line.capabilities['active'] = Status.PLANNED
        with self.assertRaises(TypeError):
            replace(NEURO, capabilities={'x': 'ACTIVE'})

    def test_context(self):
        context = CareContext(10, NEURO, origin='SISTEMA', reference_date=date(2026, 1, 1))
        self.assertIs(context.care_line, NEURO)
        self.assertIs(context.origin, CareOrigin.SISTEMA)
        with self.assertRaises(TypeError):
            CareContext(10, 'NEURO')
        with self.assertRaises(ValueError):
            CareContext(10, NEURO, origin='unknown')


class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        # Only the two existing tables used by resolution are needed. No patient data.
        ModuloClinico.__table__.create(self.engine)
        PacienteModulo.__table__.create(self.engine)
        self.db = Session(self.engine)
        self.db.add_all([ModuloClinico(id=line.module_id, nome=line.display_name,
                                      slug=line.slug, ativo=True) for line in (NEURO, CARDIO)])
        self.db.commit()
        self.resolver = CareLineResolver()

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def link(self, module, active=True, patient=10):
        self.db.add(PacienteModulo(paciente_id=patient, modulo_id=module, ativo=active))
        self.db.commit()

    def test_single_lines(self):
        for line in (NEURO, CARDIO):
            self.link(line.module_id, patient=line.module_id)
            self.assertIs(self.resolver.resolve(self.db, line.module_id), line)

    def test_ambiguous(self):
        self.link(1)
        self.link(2)
        with self.assertRaises(AmbiguousCareLine) as caught:
            self.resolver.resolve(self.db, 10)
        self.assertEqual(caught.exception.code, 'AMBIGUOUS_CARE_LINE')
        self.assertIs(self.resolver.resolve(self.db, 10, 'CARDIO'), CARDIO)

    def test_missing_link(self):
        self.link(1)
        with self.assertRaises(PatientCareLineNotFound):
            self.resolver.resolve(self.db, 10, 'CARDIO')
        with self.assertRaises(PatientCareLineNotFound):
            self.resolver.resolve(self.db, 11)

    def test_unknown(self):
        with self.assertRaises(CareLineNotFound):
            self.resolver.resolve(self.db, 10, 'unknown')

    def test_capabilities(self):
        self.link(2)
        self.assertIs(self.resolver.resolve(self.db, 10, 'CARDIO', 'daily_record'), CARDIO)
        for requested in (None, 'CARDIO'):
            for capability in ('clinical_reading', 'unknown', ''):
                with self.subTest(requested=requested, capability=capability):
                    with self.assertRaises(CareLineCapabilityNotSupported):
                        self.resolver.resolve(self.db, 10, requested, capability)
        self.link(1)
        self.assertIs(self.resolver.resolve(self.db, 10, required_capability='clinical_reading'), NEURO)
        with self.assertRaises(AmbiguousCareLine):
            self.resolver.resolve(self.db, 10, required_capability='daily_record')

    def test_inactive_link(self):
        self.link(1, active=False)
        for requested in (None, 'NEURO'):
            with self.assertRaises(PatientCareLineNotFound):
                self.resolver.resolve(self.db, 10, requested)

    def test_inactive_persisted_module(self):
        self.link(1)
        self.db.get(ModuloClinico, 1).ativo = False
        self.db.commit()
        for requested in (None, 'NEURO'):
            with self.assertRaises(PatientCareLineNotFound):
                self.resolver.resolve(self.db, 10, requested)

    def test_inactive_application_line(self):
        self.link(1)
        resolver = CareLineResolver(CareLineRegistry([replace(NEURO, active=False)]))
        with self.assertRaises(CareLineInactive):
            resolver.resolve(self.db, 10, 'NEURO')
        with self.assertRaises(PatientCareLineNotFound):
            resolver.resolve(self.db, 10)

    def test_duplicate_links(self):
        self.link(1)
        self.link(1)
        self.assertIs(self.resolver.resolve(self.db, 10), NEURO)

    def test_unregistered_module_ignored(self):
        self.db.add(ModuloClinico(id=99, nome='Synthetic', slug='synthetic', ativo=True))
        self.link(99)
        with self.assertRaises(PatientCareLineNotFound):
            self.resolver.resolve(self.db, 10)
        self.link(1)
        self.assertIs(self.resolver.resolve(self.db, 10), NEURO)

    def test_future_line_needs_only_registration(self):
        line = replace(CARDIO, code='SYNTHETIC', slug='synthetic', module_id=99)
        self.db.add(ModuloClinico(id=99, nome=line.display_name, slug=line.slug, ativo=True))
        self.link(99)
        resolver = CareLineResolver(CareLineRegistry([NEURO, CARDIO, line]))
        self.assertIs(resolver.resolve(self.db, 10, required_capability='daily_record'), line)


if __name__ == '__main__':
    unittest.main()
