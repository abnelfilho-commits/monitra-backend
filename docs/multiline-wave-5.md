# Wave 5 — Institutional interventions V1

Baseline: `feature/multiline-wave-4-timeline`,
`feafbfbebda70606eb7fd9273f0074cb6e9826d8`.
Implementation branch: `feature/multiline-wave-5-interventions`.

## Boundary

`InterventionService` owns patient/resource authorization, creation resolution,
physical adapter dispatch and write transactions. `GenericAdapter` retains
`intervencoes`; `CardioAdapter` retains `intervencoes_cardiometabolicas`.
No storage consolidation, clinical scoring or DailyRecordService invocation.
Only the Wave 3 ActorRef value contract is reused.

Creation dispatch is a small configurable `line_sources` mapping. Existing
resource dispatch uses source_type, not active patient links. A future line can
supply a registry definition and map to the generic adapter without changing
service algorithms. There is no implicit fallback for an unconfigured provider.

## Contracts

Python 3.9-compatible dataclasses:

- `InterventionSubmission`: patient_id, optional requested_care_line, authenticated
  executor ActorRef, type, optional narrative/reference_datetime, isolated payload.
- `InterventionRecord`: source_type/source_id, patient_id, optional resolved
  CareLineDefinition, module_id, care_line_association, optional namespaced actor,
  type, narrative, reference_datetime, created_at, isolated factual metadata.
- `InterventionUpdate`: type, narrative, reference_datetime only.

The type vocabulary is authored and is not a universal enum. Generic creation
requires a clinical datetime and accepts nullable narrative. No new normalization
or future-date/duplicate policy was introduced. Specialized payload keys are
validated; generic rejects them, Cardio accepts only priority. Cardio requires a
string narrative (empty string remains accepted, matching the current channel).
Cardio string lengths respect the actual table limits; priority is not a risk.

No risk, score, trend, protocol or clinical_state is exposed or calculated.
No clinical observation is invented. Cardio rejects reference_datetime and
preserves the database-created timestamp separately. No origin field or fake
executor/editor audit persistence is introduced.

## Durable association and migration

Revision `5a01c7e2d903`, parent `fb27d5139e1e`, adds only:

- `intervencoes.modulo_id INTEGER NULL`, no default;
- `fk_intervencoes_modulo_id` to `modulos_clinicos.id`, no destructive cascade.

No backfill. Downgrade drops this FK and column; original rows remain. As with any
column removal, downgrading after new associated writes loses their module
association; it is not a lossless reversal of new application data.

New institutional generic writes persist the resolved module. Existing NULL rows
remain UNASSIGNED, including after edits. Unknown registry IDs remain explicit
module IDs with no invented CareLineDefinition. Cardio remains DERIVED from its
specialized source. Patient/source identity namespaces are unchanged.

**Apply the migration before activating this backend version.** The ORM and the
Wave 4 generic collector now select modulo_id. No migration was applied to the
application database, HML or PROD in this mission. Upgrade/downgrade were tested
only against an isolated synthetic PostgreSQL schema.

## Service API and transactions

- create(db, submission, user=...)
- get(db, source_type, source_id, user=...)
- list_for_patient(db, patient_id, user=..., source_type=None, requested_care_line=None)
- update(db, source_type, source_id, changes, user=..., expected_patient_id=None)
- delete(db, source_type, source_id, user=...)

Writes commit once and roll back on failure. Adapters add/execute/flush but never
commit or roll back. Update/delete lock the persisted resource. Return data is
materialized before the commit; there is no mandatory post-commit refresh.
A caller must provide a dedicated request/operation Session, not expect this
boundary to commit only part of an unrelated pending transaction.

Get/list do not commit. List preserves each source's existing ordering; an
all-source internal list is source-grouped, not a new global clinical chronology.
Use Timeline for consolidated temporal ordering.

Creation uses CareLineResolver with `interventions`. PLANNED is not usable.
Ambiguity is rejected; inactive application definitions, inactive database links
and modules retain the Wave 1 error semantics. Historical get/list/update/delete
do not require current active linkage; their context is the stored resource.

## Authorization and actors

All seven intervention HTTP routes authenticate with get_usuario_atual. Service
operations load the actual patient/resource and use assert_clinica_access.
Resource authorization never uses the patient supplied in a PUT to establish
access. ADMIN semantics are unchanged; ADMIN_CLINICA is not a global bypass.

Generic authorship stores authenticated user.id and reads namespace `usuarios`.
Cardio stores user.profissional_id only when that professional exists, is active
and belongs to the patient's clinic; invalid relationships fail. No relationship
means NULL, including ADMIN without a professional. Cardio reads namespace
`profissionais`, never reverse-maps to a user. user.id need not equal professional.id.

Original authorship (including historical NULL), patient, module and created_at
are immutable on update. No last-editor field exists. Generic hard delete is
preserved with authorization, without soft-delete or invented audit history.
Cardio update/delete are unsupported and no endpoints were introduced for them.

## Legacy HTTP compatibility

Migrated routes:

- POST /intervencoes/
- GET /intervencoes/paciente/{paciente_id}
- GET /intervencoes/{intervencao_id}
- PUT /intervencoes/{intervencao_id}
- DELETE /intervencoes/{intervencao_id}
- POST /cardiometabolico/pacientes/{paciente_id}/intervencoes
- GET /cardiometabolico/pacientes/{paciente_id}/intervencoes

Explicit serializers preserve generic field names (including profissional_id),
Cardio list fields/priority, and create/delete confirmations. The ORM's new module
column and institutional fields do not leak into these legacy responses.
Generic and Cardio lists remain source-specific and unpaginated.

Generic POST accepts optional requested_care_line. Existing Neuro mono-line calls
remain valid. Multi-line calls without selection return 409 with
AMBIGUOUS_CARE_LINE in detail. This is the approved temporary frontend limitation;
no UNASSIGNED fallback or route-name inference exists. A generic dated payload
resolving to Cardio is rejected rather than dropping its clinical datetime.
The specialized Cardio route supplies explicit CARDIO context and its original
payload. No frontend changes were made.

Domain errors are translated at the HTTP boundary: missing resources 404,
identity/ambiguity conflicts 409, other payload/capability/unsupported-operation
errors 400. Existing ACL errors retain 403; authentication retains its own status.
Integrity errors are not exposed with database or clinical payload details.

## Compatibility and clinical protection

Only the Wave 4 generic collector changed: it reads modulo_id, reports EXPLICIT
for a persisted ID (including unknown IDs), preserves NULL as UNASSIGNED, and
includes module_id in factual metadata. PATIENT includes both; CARE_LINE includes
known associated generic events and excludes UNASSIGNED. Cardio collector and
TimelineEvent contract remain unchanged.

Report's get_timeline profile still reads all generic interventions for the
patient and excludes specialized Cardio storage. No new module filters were
added to Cockpit or Sessions. Session context still returns the five most recent
generic interventions. Professional Cockpit still emits only the newest event
per patient. Existing raw clinical engines and ClinicalReading were not edited.

## Validation actually executed

Runtime: Docker `docker-api`, Python **3.9.25**. Checkout mounted read-only;
PYTHONDONTWRITEBYTECODE=1. Seventeen changed Python files compiled in memory and
parsed with ast feature_version=(3, 9), including migration, routes and tests.

Before new tests, existing suite: 105 passed. Final results:

| Coverage | Tests | Result |
| --- | ---: | --- |
| Wave 1 care_lines | 17 | PASS |
| Wave 2 clinical_reading | 27 | PASS |
| Wave 3 daily_record + routes | 34 | PASS |
| Neuro characterization | 3 | PASS |
| Wave 4 Timeline, including new association case | 25 | PASS |
| Wave 5 contract/service | 37 | PASS |
| Wave 5 HTTP | 9 | PASS |
| Report/Cockpit/Session characterization | 4 | PASS |
| PostgreSQL migration/adapter/revision tests | 3 | PASS |
| **Full suite** | **159** | **PASS, zero skips** |

The focused `test_intervention*.py` run passed 53 tests. One initial new Cockpit
characterization expected three displayed events; inspection confirmed the
existing newest-event-per-patient behavior. Only the test expectation was fixed.
No Cockpit production change was made. The first 48-test focused aggregate had
one failure from that expectation; subsequent focused and full suites passed.

Reproducible isolated PostgreSQL setup (no published port, no external network):

```sh
docker run -d --rm --network none --name integra-wave5-test-postgres -e POSTGRES_USER=wave5 -e POSTGRES_DB=wave5_test -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine
```

Focused command actually executed:

```sh
docker run --rm --network container:integra-wave5-test-postgres -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:///:memory: -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test -v /private/tmp/integra-wave1:/workspace:ro -w /workspace docker-api python -m unittest discover -s tests -p 'test_intervention*.py' -v
```

Final full-suite command actually executed:

```sh
docker run --rm --network container:integra-wave5-test-postgres -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:///:memory: -e WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test -v /private/tmp/integra-wave1:/workspace:ro -w /workspace docker-api python -m unittest discover -s tests -v
```

The PostgreSQL tests allow only the exact disposable fixture URL and use fresh
random schemas. They verify nullable/no-default/FK behavior, no backfill,
downgrade, migration ancestry, real adapter writes and timestamp/actor semantics.
They do not prove a full historical Alembic bootstrap or HML schema parity.
Without the explicit test URL, those three tests are skipped.
Other tests use synthetic SQLite fixtures; unrelated source collectors are
stubbed only where a focused consumer characterization does not need them.

Cleanup of the disposable fixture container:

```sh
docker stop integra-wave5-test-postgres
```

## Debt and HML pre-rollout gate

- Verify Cardio table, columns, nullability, profissionais FK, priority, timestamp
  type/default and assumed indexes in HML. Local schema matched reconnaissance;
  no HML parity is claimed. Creation provenance is still uncertain.
- Apply the single additive migration before new code is active.
- Accept the approved ambiguity limitation or plan explicit frontend selection
  separately. No frontend convergence is claimed.
- Cardio still has no separate durable executor identity, clinical datetime,
  edit/delete, or editor audit. Generic hard delete has no history.
- These seven route corrections do not secure the separate legacy Timeline
  routes identified in reconnaissance. Do not claim all clinical read paths
  are now protected; those routes remain a separate security debt.
- Legacy Report/Cockpit/Session aggregation remains unchanged, not fully
  Multi-Line. No idempotency or duplicate policy was added.
- No new indexes or Cardio bootstrap migration was introduced.

No push, merge, deployment, clinical rule change, patient-data migration,
frontend change, or later-Wave implementation is part of this mission.
