# WAVE 1 — EXECUTION REPORT

Date: 2026-09-17. STATUS: PASS — Gate 1 in isolated synthetic runtime.
This is not a deployment or acceptance of the unchanged shared environment.

Baseline backend: 1e45bd8b14d31bd6fb9af709fab67ca312dc97a8.
Baseline frontend: 919a4a59ad1ea8980eaaccb753e68181463bcd91.
Both worktrees: codex/cardio-v1-stabilization. No push/deploy.
Wave-specific commits are recorded in the execution handoff.
Backend: /private/tmp/integra-wave1. Frontend: /private/tmp/integra-wave7-front.
Original application checkouts were not modified.

## Decision implemented

The user confirmed that all existing records are development/test data, not
production clinical history. Interventions and diagnoses require their own
persisted care line. There is no permanent legacy/unassigned support for these
entities, no NULL-to-Neuro fallback and no inference from patient memberships.

## Implementation and files

- `app/services/care_lines/access.py`: registry/resolver reuse; role, clinic,
  active patient/module and professional-module authorization.
- `app/services/patient_line_service.py`, `app/routers/pacientes.py`: membership
  lists independent of clinical observations; patient-row locking for idempotent
  second-line association; patient creation clinic determined server-side.
  Eager-loading avoids introducing per-patient clinic/professional queries.
- `app/core/deps.py`: responsible JWT cannot authenticate as institutional user.
- Diagnosis model/schema/service/router: mandatory persisted line; authenticated
  create/read/list/update/revise/cancel scoped by patient, clinic and line.
- Intervention model/contracts/adapters/service/router: mandatory explicit line,
  specialized Cardio source persists its line; generic resource routes require
  line context, including mutation. Existing Cardio temporal semantics preserved.
- `app/routers/cardiometabolico.py`: membership-driven list including no-record
  patients; protected patient/Timeline/evolution endpoints; stored-line filter
  for specialized interventions. Existing clinical calculations unchanged.
- `app/routers/analytics.py`, `timeline.py`: authorized Neuro patient context.
- `app/services/timeline/sources.py`, `timeline_service.py`,
  `timeline_event_service.py`: persisted diagnosis/intervention association and
  Neuro source filters; sessions filtered by persisted PTS ancestry.
- `app/services/session_service.py`, `app/routers/sessoes_assistenciais.py`:
  patient session listing contextualized through persisted PTS line.
- Frontend pages: Pacientes, RegistrarDiagnostico, DiagnosticoDetalhe,
  cardiometabolico/PacienteCardiometabolico; services: pacientes, diagnosticos,
  intervencoes, sessoesAssistenciais. Diagnosis shares the existing authenticated
  client and carries active context through patient lookup, creation/detail and
  cancellation navigation. Cardio exposes its diagnosis list/action, removes PTS
  action. Backend remains responsible for authorization.

## Migrations (tested only on disposable PostgreSQL)

Existing `5a01c7e2d903` remains the additive nullable intervention step.
Successors:

1. `8c01a0d1a001`: diagnosis module FK/index and NOT NULL; rejects existing
   unidentified diagnoses transactionally, with no deletion or guessed backfill.
2. `8c01a0d1a002`: generic interventions NOT NULL; rejects unidentified rows.
3. `8c01a0d1a003`: specialized Cardio table stores module FK/NOT NULL; assignment
   derives from the exclusively Cardio physical source, never patient membership.

No migration was applied to the application database. No patient data was changed.
PostgreSQL tests prove constraint enforcement, invalid-FK rejection, no defaults,
transactional rollback on inconsistent mass and preservation of explicit lines.
The diagnosis downgrade deliberately requires an explicit preservation plan.

## Tests

Final full suite, in a disposable PostgreSQL container without published ports:

```sh
docker run --rm --network container:integra-cardio-gate1-pg \
  -v /private/tmp/integra-wave1:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e CARDIO_GATE1_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e CARE_PLAN_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e SESSION_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test \
  docker-api python -m unittest discover -s tests
```

Result: **231 tests, all passed, zero skipped** (10.709 seconds, final rerun).
New tests: test_cardio_foundation.py, test_cardio_foundation_postgres.py.
Updated regression fixtures/tests: test_care_plan.py, test_interventions.py,
test_intervention_routes.py, test_intervention_consumers.py,
test_intervention_migration.py, test_timeline.py, test_sessions_attendance.py.

Additional Daily Record PostgreSQL characterization:

```sh
docker run --rm --network container:integra-cardio-gate1-pg \
  -v /private/tmp/integra-wave1:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test \
  docker-api python -m unittest discover -s tests -p test_daily_record.py
```

Result: **29 tests, all passed** (1.537 seconds).
An earlier full run with WAVE3_TEST_POSTGRES_URL globally enabled had five fixture
setup failures: Daily Record HTTP fixtures create SessaoAssistencial without its
agenda_cuidados ancestor on PostgreSQL. Those HTTP fixtures run in their existing
SQLite configuration in the full passing suite; Daily Record PostgreSQL tests
were executed separately. This is a test-fixture limitation, not hidden success.

Python 3.9 AST and in-memory compile of app Python files, new migrations and tests:
**233 files passed**. No bytecode was written to the repository.

Frontend `npm run build -- --outDir /private/tmp/integra-cardio-v1-front-build`:
**PASS**, 861 modules; existing large-bundle warning remains.
Targeted `npx eslint src/pages/DiagnosticoDetalhe.jsx src/pages/RegistrarDiagnostico.jsx
src/services/diagnosticos.js src/services/intervencoes.js src/services/pacientes.js
src/services/sessoesAssistenciais.js`: **PASS**, zero findings. The unused variable
in the touched diagnosis form was removed after explicit frontend authorization.
The prior automatic approval block is resolved. `node --check
tests/gate1-integration.cjs` also passed.

### Real browser + API + PostgreSQL integration

A disposable PostgreSQL 16 container, the actual `app.main:app` on local port
8019, and Vite on 5174 were used. No HTTP responses or auth dependencies were
mocked. Authentication used the real login/JWT flow with synthetic credentials.

`tests/fixtures/cardio_gate1_runtime.py` rejects any database URL except the
isolated Gate 1 database and requires it to be empty. It creates ORM structures,
reconstructs the known pre-Wave-1 module columns, adds the already-known Cardio
raw SQL projections, and executes revisions 5a01c7e2d903 through 8c01a0d1a003.
This tests the new migration chain, not a claim that all historical schema drift
has been reconciled. No shared schema was copied or modified.

Frontend command (desktop runtime supplies Playwright; Chrome installed):

```sh
PLAYWRIGHT_MODULE=/Users/Abnel/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright node tests/gate1-integration.cjs
```

PASS for four real journeys: Neuro-only patient, Cardio-only patient, and the
same multi-line patient in each line. Each journey opens the correct 360,
creates a diagnosis through the shared form, checks POST context and persisted
module, opens the detail, rejects cross-line access and checks isolated 360
presentation. Contextual cancellation navigation also passed. Additional API
checks prove clinic isolation, membership without observations, explicit
intervention creation and isolated Neuro/Cardio Timelines.

An initial browser assertion used exact text that omitted the rendered
“Descrição:” label. The selector was corrected; no application behavior was
changed for that test failure. Final browser execution passed, with zero HTTP
5xx responses. No real patient data or credentials were used.

`git diff --check`: PASS in both worktrees. Implementation diff reviewed.

## Gate evidence

- [x] Neuro-only and Cardio-only patient lists isolated.
- [x] Same multi-line patient identity in both lists; idempotent second-line API.
- [x] Cardio patient with no observation included.
- [x] Diagnosis creation/list/mutations isolated, including HTTP authorization.
- [x] Intervention NULL rejected; cross-line HTTP read/update/delete rejected.
- [x] Timeline uses the row's persisted intervention/diagnosis line, no fallback.
- [x] Patient session list filters persisted PTS line.
- [x] Clinic/professional access and responsible/user credential separation tested.
- [x] Neuro characterization suite passes; no clinical engine rules changed.
- [x] Four diagnosis/360 UI journeys against migrated coherent synthetic runtime verified.
- [x] Mandatory-line migrations and constraints verified in isolated PostgreSQL.
- Shared environment intentionally unchanged; sanitation requires separate authorization.

Gate 1 PASS. Proceed to master Wave 2 only after recording this checkpoint.

## Application data and exact sanitation scope for review

Read-only counts on the existing sentinela_api database connection:
264 generic interventions, 3 diagnoses, 70 specialized Cardio interventions.
Generic interventions and diagnoses currently lack module columns. No inbound
foreign keys to these two tables were found in information_schema.

Before any shared-environment mutation, the proposed bounded operation is:
remove only those 264 generic intervention test rows and 3 diagnosis test rows,
rechecking counts/schema and locking the two tables; abort on a changed snapshot.
Do not cascade/truncate or remove patients, users, memberships, daily records,
PTS/sessions, or the 70 specialized Cardio interventions. Apply the migration
chain transactionally; specialized Cardio rows retain content and acquire their
source-proven line. No production operation. No automatic clinical replacement
records: synthetic replacement fixtures, if needed for UI validation, must have
explicit line and clearly synthetic content in an isolated validation environment.
This sanitation was **not executed**. There is no new product/clinical ambiguity.

## Remaining observations

Report Engine composition and old Cardio presentation calculations remain for
later master waves. No claim of complete Cardio APP/WhatsApp convergence is made.
CARDIO-DR-OBS-001 remains a separate clinical representation decision.
No broad cleanup, identity-core implementation, production migration, merge,
push or deployment occurred.

## Next Wave

Proceed to the master Wave 2 directed AS-IS/plan for the Cardio journey,
Professional/APP/WhatsApp Daily Records and interventions independent of PTS.
Do not claim shared environment readiness until its separately authorized
sanitation/migrations are executed. No shared data operation is needed to
continue implementation and synthetic validation.
