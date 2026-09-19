# DAILY RECORD CONCURRENCY — EXECUTION REPORT

Baseline: f6f8c273b922557212847574f37392e407bdba12, branch
`codex/cardio-v1-stabilization`. Only development worktree and disposable PG18.
No migration, HML access, infrastructure change, push, merge or deployment.

## AS-IS inspection before the application change

| Entry / call chain | Transaction / original locks | Auth, clinic and line | Dedup / persistence |
|---|---|---|---|
| Portal `POST /registros-longitudinais/` -> `write_legacy_longitudinal` -> `DailyRecordService` | Session dependency; service commits or rolls back; no identity locks before create | `authorized_patient`: role, clinic, professional module; resolver/form compatibility; authenticated user propagated | Neuro provider responsible-only duplicate rule does not limit professional records; parent flush, answers, author, Cardio projection before commit |
| Portal `POST /cardiometabolico/registro-diario` -> `call_write` -> same service | Same; originally no explicit parent lock | Professional `authorized_patient` for CARDIO; resolver; clinical date today | Same institutional store, professional actor; no new daily uniqueness rule |
| Portal `PATCH /registros-longitudinais/{id}` -> attendance guard -> adapter/service | Original record FOR UPDATE before service; commit/rollback service | Authorized stored patient/line; immutable patient/line; canonical attendance cannot be edited here | Replaces answers/projection in one transaction; no intermediate commit |
| APP `POST /responsavel/pacientes/{id}/registros` | Patient FOR UPDATE, then service writes/commits; failure closes/rolls back Session | Authenticated responsible; active responsible-patient link; active patient; resolver NEURO | Today/yesterday; Neuro duplicate check across responsible origins per patient/form/day; author responsible |
| APP `POST /responsavel/pacientes/{id}/registros-cardio` | Patient FOR UPDATE, channel duplicate query, service commit | Responsible link/patient checks; resolver CARDIO | Per patient/day/responsible and responsible origins; answers/direct projections/observacoes in same transaction |
| WhatsApp POST -> `process_message` -> `processar_mensagem` -> `create_record` -> service `commit=False` | Phone advisory transaction lock -> receipt insert/unique message ID -> responsible FOR UPDATE (identity resolution) -> patient FOR UPDATE -> responsible link FOR UPDATE; ingress alone commits/rolls back | Signature/recipient/payload validation first; unique phone identity; active responsible/patient/link, clinic compatibility and active care line revalidated | Receipt/fingerprint dedup; Neuro patient/form/day vs Cardio patient/responsible/day; conversation + receipt + clinical data atomic |

Foreign keys relevant to the cycle: `registros_longitudinais.paciente_id -> pacientes.id`
and `criado_por_responsavel_id -> responsaveis.id`. Professional author references
`usuarios.id`; module/form reference `modulos_clinicos`/`formularios_modulo`;
answers reference the record and form field. FK checks can acquire implicit KEY
SHARE locks, even when the caller never explicitly locks that parent.

Other paths inspected, not silently conflated with the institutional pipeline:
- `app/routers/registros.py` remains mounted at `/registros`, authenticated, writing
  the old `registros_diarios` table with its own patient/date UNIQUE and 409/rollback.
  It is not an institutional longitudinal writer. No responsible-author FK in that
  old model. Convergence/removal of this legacy API is outside this correction.
  Read-only frontend check: App.jsx registers NovoRegistroDiario, which posts to
  /registros-longitudinais/. The old NovoRegistro component/service still exists,
  but is not registered in App.jsx. Cardio uses /cardiometabolico/registro-diario.
- `ResponsavelRegistroService.criar_registro_neuro` has no callers found in app;
  legacy generic writer, not any of the current APP/WhatsApp routes. Do not reuse it.
- Generic non-daily forms and SessionService attendance have separate lifecycles;
  they are not relabeled as Daily Record and were not refactored.

## Proven cause

The previously failing real APP/WhatsApp test raised PostgreSQL 40P01. A new causal
regression reproduces the *old* lock order with two barrier-synchronized transactions,
using actual schema FKs:

- APP: holds patient FOR UPDATE; inserting responsible-authored record waits for
  responsible KEY SHARE held incompatibly by WhatsApp.
- WhatsApp: holds responsible FOR UPDATE; waits for patient FOR UPDATE held by APP.

Both causal-test transactions always roll back. Exactly one deadlock victim and
one completed transaction are expected in this deliberate legacy reproduction;
this is not an error in the corrected application tests. No sleep-based guess is
needed to arrange the two initial locks.

Original susceptibility: both APP lines used the same patient-first order and both
WhatsApp lines used responsible-first. Multi-Line does not remove the shared parent
rows. Portal inserts did not explicitly lock responsible, but implicit FKs matter;
Portal edits also locked records before introducing an institutional patient lock.
APP x APP and WhatsApp x WhatsApp had more consistent orders, but all pairs must be
validated rather than assuming that the original symptom defines the scope.

## Canonical policy

`app/services/daily_record/concurrency.py` centralizes transaction-scoped locks:

1. Responsible identity, only for responsible-authored operations.
2. Patient identity.
3. Responsible link when the WhatsApp authorization flow locks it.
4. Existing record for edits; answer/projection writes follow.

Identity locks are FOR NO KEY UPDATE (SQLAlchemy `with_for_update(key_share=True)`
without `read=True`). They exclude competing writes, deletes and revocation updates,
but allow FK KEY SHARE checks. No caller should later upgrade these identity locks
to FOR UPDATE. Existing record locks remain FOR UPDATE. No isolation-level reduction,
retry loops, global mutex or per-line infrastructure is introduced.

WhatsApp retains its phone advisory lock, message identity uniqueness and responsible
identity serialization even before a patient is selected. Choosing responsible first
is compatible with that existing channel lifecycle. Professional operations skip the
responsible identity entirely. Serial scope is an individual responsible/patient,
not the population; different lines/dates of one patient serialize briefly because
the real FK parent is shared. Transactions must not pre-lock resources out of order
or batch unrelated patients in arbitrary order before calling this API.

APP channel checks acquire this same context before their duplicate queries. The
institutional service itself locks before resolver/provider execution, including
callers that bypass the adapters. Portal PATCH locks patient before its existing
attendance guard locks record. No attendance protection was removed.

Cardio's existing per-responsible/day duplicate rule is also enforced in its provider
under the canonical service lock; it is no longer dependent solely on the caller's
preliminary query. Existing channel response checks remain compatible. Neuro clinical
provider, thresholds and interpretation remain unchanged.

## Authorization, identity and transaction preservation

No authorization check was removed or replaced with a lock. Existing professional
clinic/line boundaries and responsible checks remain; WhatsApp continues refreshing
active responsible, patient and link after lock acquisition. No FK, clinic context,
line context, actor namespace or persisted origin changed. Responsible APP and
WhatsApp remain distinct origins. Operational locks do not compute clinical values.

Commit ownership is unchanged: APP/Portal service commit; WhatsApp ingress commit
of receipt, conversation and clinical rows together. A losing duplicate transaction
rolls back; it does not leave answers/projections or an extra clinical record.
Webhook HMAC, recipient validation, durable receipt dedup and outbound delivery logic
are untouched. Meta was not contacted.

## Tests

New `tests/test_daily_record_concurrency.py` uses real PG18 sessions and barriers:
- Deliberate reproduction of the old FK/lock cycle, fully rolled back.
- All six pairs APP/WhatsApp/Portal (including Portal x Portal), three repetitions
  each for Neuro and Cardio. Professional records are not incorrectly deduplicated
  against responsible records.
- Multi-Line same-patient parallel writes remain distinct by module.
- Different responsible actors: Neuro one record, Cardio two according to existing
  policy, not a newly invented uniqueness scope.
- Concurrent same final WhatsApp message: one clinical record, one receipt,
  one conversation transition; identical reply returned.
- Direct institutional service concurrency, including Cardio provider check;
  losing transaction rollback asserted.
- Portal edit against responsible creation: edit preserved, separate responsible
  observation retained; no lost record.

Every matrix checks expected count, author namespace, persisted origin, module,
patient and absence of orphan/partial answers. Unexpected validation/SQL errors
are not counted as legitimate duplicate losers. Test lock timeouts bound hangs;
production lock timeouts or automatic retries were not added.

Existing full suite covers signatures, auth/revocation, clinic/line denial,
projections, interpretation, reports, migration preservation and negative paths.
SQLite fixture now includes synthetic identity tables needed by canonical locks;
PostgreSQL remains the evidence for concurrency.

## Limits

This proves the exercised institutional write paths on PostgreSQL READ COMMITTED,
not universal deadlock freedom for arbitrary external SQL or future code. Direct
SQL, legacy parallel storage and ad-hoc transactions can bypass application ordering.
Future writers must enter the institutional service. Patient/link administrative
workflows are not a general concurrency redesign in this change.

The prior mutable-data/no-production decisions and all approved migration/sanitation
files remain byte-for-byte unchanged relative to f6f8c27. Existing HML deployment
configuration, backup/window approvals and actual execution remain separate gates.

## Final results

**DAILY RECORD CONCURRENCY GATE: PASS**

**HML REMEDIATION MIGRATION GATE: PASS** (development/disposable validation only).
This supersedes the concurrency-blocked result in the previous migration report;
it is not authorization or evidence of HML deployment.

- Initial full regression after application fix: 344 tests, OK, zero skips (32.633s).
- Expanded final concurrency suite plus original blocking case, ten repetitions:
  90 test executions, OK, zero skips (30.112s). Eight new distinct tests, not 90
  distinct tests. Each channel matrix also repeats its pair scenarios three times.
- Repeated final full regression with all PostgreSQL URLs enabled: 346 tests, OK,
  zero skips (30.609s). Includes the 11 migration/remediation tests, all daily record,
  APP/Portal/WhatsApp, Multi-Line, Neuro, Cardio and Report Engine regressions.
- Python 3.9.25 compilation: 280 files in app/tests/alembic, PASS.
- Alembic single head 8c01a0d1a004; diff of alembic and scripts/sql against f6f8c27
  empty. Clinical engines, report engine, schemas and frontend unchanged.
- git diff --check PASS. Final local commit/hash reported in delivery.

Commands:

```sh
# Repeated concurrency (same read-only mount and isolated network as full suite):
docker run --rm --network container:integra-remediation-pg18 \
  -v /private/tmp/integra-wave4-backend:/work:ro -w /work \
  -e PYTHONDONTWRITEBYTECODE=1 \
  -e WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test \
  docker-api python -c 'import sys,unittest; sys.path.insert(0,"tests"); suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromNames(["test_daily_record_concurrency","test_whatsapp_postgres.WhatsAppPostgresTests.test_neuro_app_whatsapp_concurrent_duplicate_policy"]) for _ in range(10)); r=unittest.TextTestRunner().run(suite); sys.exit(not r.wasSuccessful())'

# Full regression, repeated after the concurrency validation:
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

git diff --quiet f6f8c27 -- alembic scripts/sql
git diff --check
```
