# HML remediation migration — execution report

Scope: development branch `codex/cardio-v1-stabilization`, based on
`d228aae55b0ed34730ebb554d5c29a205e0ba57c`. No access to HML, no shared database
writes, push, merge, deployment or frontend changes.

## Decision and graph

Chosen alternative A: a nullable staging revision, followed by the existing
fail-closed constraint revision. No diagnosis is deleted or reconstructed.
There is no automatic membership inference, module default or hardcoded HML
identifier in the migration chain. The operator SQL is a separate one-time,
explicitly approved inventory operation, not called by application or Alembic.

Before:
`fb27d5139e1e -> 5a01c7e2d903 -> 8c01a0d1a001 -> 002 -> 003 -> 004`

After:
`fb27d5139e1e -> 5a01c7e2d903 -> 8c01a0d1a000 -> 8c01a0d1a001 -> 8c01a0d1a002 -> 8c01a0d1a003 -> 8c01a0d1a004`

Single head remains `8c01a0d1a004`. Revision 000 adds only a nullable INTEGER
column. Revision 001 keeps validation, NOT NULL, FK and composite index; its
parent changes to 000 and ADD COLUMN moves to 000. All other revisions unchanged.
The user confirmed 001 has not been applied in HML or PROD. Previously migrated
local disposable databases are not evidence of this revised path: rehearsal uses
fresh isolated schemas. No stamping of shared databases is part of this plan.

Why not an inline backfill: it would entangle environment-specific approvals with
permanent schema code. Splitting creates an explicit pause where operators can
apply audited mappings, and fails closed if they do not.

## Operational SQL

`scripts/sql/hml_remediation_approved.sql` is limited to the approved HML inventory:
5 diagnoses, 16 generic interventions, 2 specialized interventions, missing
Cardio linkage for patient 6, and the single empty conversation. It checks revision,
module identities, exact ID sets and relevant memberships; these membership checks
are drift guards, not the source of a mapping. The mapping is the human decision.

It locks affected tables, checks all conditions before any change, maps the approved
IDs to Neuro, inserts the approved Cardio linkage, and removes only the approved
empty conversation. All actions commit together. Any mismatch rolls back everything
and requires human review. Reexecution is deliberately refused rather than silently
changing a different inventory. Backups must include all affected rows, including
conversation data, and be stored securely; do not print sensitive data in logs.

The new linkage uses active=true, date 2026-06-09, no end date, and an observation
that explicitly distinguishes first available evidence from absolute historical
start. Existing Neuro linkage and longitudinal observations are untouched.

## Future HML sequence — NOT EXECUTED

1. Human approval of this new backend commit and execution window. Resolve the
   separate deployment/configuration preflight. Stop all application/channel writes;
   control auto-deploy before integrating branches. Confirm database identity.
2. Take and verify backup/restore; reconfirm revision `fb27d5139e1e`, inventory,
   module IDs, real constraints/triggers and absence of unexpected drift.
3. From the exact approved artifact, run `alembic upgrade 8c01a0d1a000`.
   This applies 5a01 and 000, leaving both generic associations nullable.
4. Run the reviewed file with `psql -X -v ON_ERROR_STOP=1 -f scripts/sql/hml_remediation_approved.sql`
   against the explicitly verified HML connection. Do not invoke via application.
   Any error: stop, inspect, do not run the next step.
5. Confirm 5 diagnoses and 16 generic interventions are preserved and module 1;
   patient 6 now has Neuro and Cardio; patient 7 unchanged; conversation 1 absent.
6. Run `alembic upgrade 8c01a0d1a004`. Revision 001 validates diagnoses; 002 validates
   generic interventions; 003 assigns specialized Cardio source to module 2; 004
   creates receipts/context. With the approved empty conversation removed, 004 has
   no existing conversation to label NEURO.
7. Verify final revision, row preservation against backup, all three NOT NULL/FKs,
   diagnosis index, absence of NULLs, two specialized module-2 rows, and linkage date.
   Keep writes paused until compatible backend deployment and smoke approval.

Do not run `upgrade head` directly on unsanitized historical data. No arbitrary
line reassignment or null-to-Neuro fallback is available.

Verification queries (run after successful chain):

```sql
SELECT version_num FROM alembic_version;
SELECT modulo_id,count(*) FROM diagnosticos GROUP BY modulo_id;
SELECT modulo_id,count(*) FROM intervencoes GROUP BY modulo_id;
SELECT id,paciente_id,modulo_id FROM intervencoes_cardiometabolicas ORDER BY id;
SELECT modulo_id,ativo,data_inicio,data_fim FROM paciente_modulos WHERE paciente_id=6;
SELECT count(*) FROM whatsapp_conversas WHERE id=1;
SELECT table_name,column_name,is_nullable FROM information_schema.columns
 WHERE table_schema=current_schema() AND column_name='modulo_id'
 AND table_name IN ('diagnosticos','intervencoes','intervencoes_cardiometabolicas');
SELECT indexdef FROM pg_indexes WHERE schemaname=current_schema()
 AND indexname='ix_diagnosticos_paciente_modulo';
```

## Rollback and limits

An unsuccessful migration call rolls its DDL and Alembic revision back. The
operator script is independently atomic. If the final migration fails after the
operator script has committed, keep writes paused: explicit mappings remain at
staging for diagnosis/correction, and are not automatically undone. Do not rerun the
one-time script. Revision 000 downgrade refuses to discard populated context;
revision 001 downgrade still refuses without a preservation plan. Use a coordinated
verified backup restore if promotion must be abandoned; do not indiscriminately
remove the reconstructed linkage after new clinical use or lose WhatsApp receipts.

Table locks and schema constraints require a maintenance window. No timing on HML
is inferred from synthetic tests. Runtime thresholds, Clinical Engines, clinical
rules and application authorization are unchanged.

## Validation scope

PG18 fixture represents affected tables at revision fb27d5139e1e and inventoried
relationships with synthetic data. Diagnosis table is built by its real historical
migration (all original fields). The complete six-revision promotion chain is run
through Alembic MigrationContext/ScriptDirectory and real PostgreSQL transactions.
This is not a copy of HML or a reconstruction of every historical base migration.
Empty-data scenario retains canonical module reference data, required by existing
003; it means no historical clinical rows, not absence of required catalog data.

Scenarios tested: inventory preservation (including original diagnosis fields,
Neuro linkage and observations); empty clinical data; unsanitized diagnosis;
unsanitized intervention; changed conversation causing full remediation rollback.
Additional tests: every conversation guard, repeated script refusal, valid explicit
Cardio diagnosis preservation, invalid module FK rejection, whole-call DDL rollback,
and exact single-head graph.

The full-suite PG mode exposed missing authenticated user and agenda/professional FK targets in the
existing route fixture. Only that synthetic fixture was corrected, no application
code changed. Initial JSON fixture binding error was also corrected before final run.

## Executed results

**HML REMEDIATION MIGRATION GATE: BLOCKED** — migrations pass; the required full
regression exposed an existing application concurrency failure, not a migration
failure. No application files differ from approved d228aae.

- Isolated migration suite: 11 tests, OK, 1.195s, zero skips; all five mandatory
  scenarios PASS on PostgreSQL 18.
- Route fixture regression: 5 tests, OK, 0.483s, zero skips.
- Final full suite: 338 tests, 23.181s, FAILED (errors=1), zero skips: 337 passed.
- Python 3.9.25 compilation in memory: 278 files (app/tests/alembic), PASS.
- Alembic graph inspection: single head 8c01a0d1a004 and six expected promotion
  revisions, PASS. Diff whitespace check PASS.

Full-suite blocker: `test_neuro_app_whatsapp_concurrent_duplicate_policy`
(`tests/test_whatsapp_postgres.py:246`). PostgreSQL reported DeadlockDetected while
WhatsApp locked the patient. WhatsApp `authorized_lines` locks responsible then
patient (`app/services/whatsapp_daily_record.py:16`); APP locks patient first
(`app/routers/responsavel_registros.py:201`), then inserts a record with responsible
FK. The incompatible lock acquisition is a concrete candidate cause, consistent
with the observed wait cycle. No clinical rule or auth/lock behavior was changed to
force a green test. A targeted concurrency correction/reproduction needs its own
scope approval; do not accept a subsequent lucky rerun as proof of resolution.

Exact final full-suite command (only disposable container networking):

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

Isolated commands used the same container/network/read-only mount with only the
relevant URL: `python -m unittest discover -s tests -p test_remediation_migration.py -v`
and `python -m unittest discover -s tests -p test_daily_record_routes.py -v`.
Compilation used Python `compile()` over app/tests/alembic (no bytecode writing).
The obsolete variable name WAVE5 is existing test configuration, not a new Wave.

The disposable PG18 container has no published ports and no shared database
connection. Frontend remains unchanged at 76b6631ff84763a8a412a5277f7e7bf0e8e84dee.
