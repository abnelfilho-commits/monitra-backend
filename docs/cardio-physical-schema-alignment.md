# Cardio V1 — Physical schema alignment implementation gate

Status: PASS locally; pending human approval before commit/promotion.
Baseline: homolog @ 642c62ef2876b455eac45bba8cce300a8006542e.

## Approved physical contract

The previously verified HML table has seven columns: id INTEGER NOT NULL with
sequence/PK; paciente_id INTEGER NOT NULL with FK to pacientes and ON DELETE
CASCADE; tipo unbounded VARCHAR NOT NULL; descricao TEXT nullable; prioridade
unbounded VARCHAR nullable without a database default; created_at TIMESTAMPTZ
nullable DEFAULT now(); modulo_id INTEGER NOT NULL with FK to modulos_clinicos.
It has the patient index ix_intervencoes_cardio_paciente_id. There is no author
column. HML was NOT accessed during this implementation gate.

## Change

CARDIO_TABLE, CardioAdapter and the institutional Timeline source use only those
seven columns. Actor is explicitly None in both reading contracts, including
newly created interventions. No author is inferred from a patient, professional,
clinic or requesting user. The authenticated executor and professional access
checks remain enforced, separately from persisted authorship.

The INSERT omits both nonexistent authorship and created_at, preserving the
PostgreSQL clock/default. Existing application content validation and priority
selection are unchanged. No clinical rules, fallback, empty-list suppression,
care-line filters, access rules, report composition or renderer were changed.

## Fixtures and regression coverage

Independent fixture tests/fixtures/cardio_intervention_schema.py specifies the
verified DDL directly, not from CARDIO_TABLE. PostgreSQL is the schema oracle;
SQLite remains only a unit-test approximation. Runtime/remediation fixtures use
the same original columns before the existing module migration. The targeted
adapter test introspects actual PostgreSQL columns, nullability, types, defaults,
PK, FKs, cascade and patient index.

Existing cases were strengthened (test count unchanged): create/get/list on a
table without profissional_id; absent authorship; timezone-aware creation time;
individual Timeline; professional Cockpit endpoint; Dashboard and analytics;
Multi-Line and cross-clinic exclusion; inactive linkage; Cardio intervention
content retained in the shared report/PDF, absent from Neuro; unchanged query
budgets. Existing Neuro and authorization regressions also passed.

## Executed validation

All database tests used the existing disposable local container
integra-remediation-pg18, never shared/HML databases. Test image docker-api runs
Python 3.9.25. Worktree mounted read-only at /work; PYTHONDONTWRITEBYTECODE=1.

Full suite: 357 tests PASS, zero skips, 32.222 seconds.

```sh
docker run --rm --network container:integra-remediation-pg18 \
  -v /private/tmp/integra-wave4-backend:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e REMEDIATION_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARDIO_GATE1_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARE_PLAN_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e SESSION_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARDIO_GATE3_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARDIO_GATE4_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test \
  -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test \
  docker-api python -m unittest discover -s tests
```

Targeted PostgreSQL: 36 tests PASS, zero skips, 9.143 seconds.

```sh
docker run --rm --network container:integra-remediation-pg18 \
  -v /private/tmp/integra-wave4-backend:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/work:/work/tests \
  -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test \
  -e CARDIO_GATE3_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARDIO_GATE4_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  docker-api python -m unittest -v \
  test_intervention_migration.MigrationTests \
  test_cardio_longitudinal.PostgresJourneyTests \
  test_professional_cockpit.ProfessionalCockpitTests \
  test_report_multiline.PostgresReportTests
```

- In-memory Python 3.9.25 compile: 32 files PASS (both changed application files
  and all test/fixture Python files).
- Alembic ScriptDirectory.get_heads(): ['8c01a0d1a004'], no database connection.
- git diff --check: PASS.
- git diff --exit-code HEAD -- app/services/neuro_engine.py
  app/services/cardiometabolico_engine.py app/services/clinical_reading
  app/services/cardio_evolution.py app/services/cardio_priority.py alembic: PASS;
  these rules/contracts and migrations are byte-for-byte unchanged.
- PostgreSQL query counts: longitudinal Cardio 14 -> 14 for 3 -> 53 patients;
  professional cockpit Neuro 14 -> 14, Cardio 16 -> 16 after 50 additional patients.
- Shared PDF renderer generated Neuro and Cardio PDFs in disposable test storage.
  Assertions check PDF signatures, source content and line isolation; this gate
  did not perform a new visual layout review.

## Remaining limitations

Persisted institutional authorship is a separately approved future evolution;
no migration or historical backfill was introduced here. The old manual demo
seed app/scripts/seed_demo_cardio_poc.py still assumes profissional_id and omits
mandatory module context; it is not a runtime consumer, was not executed, and
must not be used as an aligned seed. Broad seed repair is outside this fix.

Existing Pydantic dict() deprecation warning remains. Frontend unchanged. No HML
access, commit, push, merge or deployment. Revalidation in HML requires a separate
authorized promotion; local PASS is not a claim of a deployed correction.
