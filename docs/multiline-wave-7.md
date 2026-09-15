# Wave 7 — Sessions / Attendance Multi-Line

Backend baseline: `feature/multiline-wave-6-care-plan`,
`7ac25887cf428e9b8fd7558b4bf809f8eb184c20`, verified clean and synchronized.
Implementation branch: `feature/multiline-wave-7-sessions-attendance`.

## Institutional boundary

`SessionService` owns session context, authorization, state transitions and
attendance. Existing execution/evolution service names are authenticated
compatibility facades over this boundary. The effective Neuro attendance was
characterized before replacing it; the overwritten invalid duplicate was removed.

Identity follows Session → Agenda → Objective/PTS → Patient + PTS.modulo_id.
Session.paciente_id must match PTS.paciente_id, and Agenda.pts_id must match its
objective. Missing ancestry and inconsistent longitudinal links are rejected.
Existing records are never reclassified from current patient-line membership.
No module columns or parallel clinical tables were added.

All nine session routes require get_usuario_atual. Clinic authorization uses the
existing assert_clinica_access through persisted ancestry. ADMIN keeps its global
exception; ADMIN_CLINICA stays clinic-scoped. There is no new assigned-professional
execution restriction. /minhas remains a professional-only personal selection,
with ancestry/clinic checks on its selected resources.

## Atomic attendance

Both attendance and registrar-evolucao use the same boundary:

1. SELECT FOR UPDATE on Session, refreshing existing ORM state.
2. Authorize persisted ancestry; validate state and existing canonical link.
3. Resolve the stored care line and active ATENDIMENTO_SESSAO form.
4. Validate payload/field membership, required narrative and required fields.
5. Call persistir_registro_longitudinal (no internal commit).
6. Set authenticated usuario.id as criado_por_usuario_id, origin PROFISSIONAL,
   and no responsible author; flush responses/authorship.
7. Set Session.registro_longitudinal_id; flush.
8. Materialize the response; commit once.

The shared transaction wrapper rolls back every pre-commit failure. No
DailyRecordService or clinical engine is used. Dedicated request sessions are
expected, as in Wave 6: do not embed these writes in unrelated pending work.

At most one canonical attendance is created per session through this boundary.
A sequential or concurrent duplicate returns 409 without replacing the link.
A new record is created inside the same transaction as its link, not attached
from an arbitrary client-provided record ID. PostgreSQL READ COMMITTED concurrency
was tested. This is a boundary guarantee, not an added database unique constraint.

## Forms and clinical content

Selection uses stored line module + ATENDIMENTO_SESSAO + active status. Exactly
one active form must exist, and its type must be LONGITUDINAL. Missing, duplicate
or wrong-type configuration fails explicitly. Active field names must be unique.
No form ID is hardcoded.

The public Neuro/Cardio payload remains narrativa / proximos_passos. Narrative
is stripped in registrar-atendimento as before; next steps remain a list of
strings. No new score, interpretation, clinical option vocabulary or rule was
introduced. Supplying next steps without a configured field is rejected rather
than silently discarded. Required metadata fields are checked; a future form
requiring additional content needs an explicit payload contract, not silent loss.

Tests use form IDs 105, 206 and 909 to demonstrate configuration-based selection.
A synthetic third line traverses Care Plan → objective → agenda → generated
session → attendance without modifying Sessions Core.

## State and historical behavior

Vocabulary is unchanged: AGENDADA, CONFIRMADA, EM_ANDAMENTO, REALIZADA, FALTOU,
CANCELADA, REAGENDADA. Implemented transitions remain:

- confirmar: AGENDADA → CONFIRMADA;
- iniciar: CONFIRMADA → EM_ANDAMENTO and current start time;
- registrar-atendimento: requires EM_ANDAMENTO and does not change it;
- finalizar: EM_ANDAMENTO → REALIZADA with current date/end time;
- reagendar: AGENDADA/CONFIRMADA → REAGENDADA with reason only.

Finalize still does not require attendance. Attendance and finalize remain
separate requests. No cancellation workflow, successor generation, automatic
rescheduling, history overwrite or professional reassignment was added.

Closed PTS or inactive current patient-line membership does not change historical
identity. UNASSIGNED ancestry can be read and undergo existing nonclinical state
transitions when clinic identity is valid; new attendance is rejected. No repair
or inference is performed. Inconsistent linked record identity is rejected.

## registrar-evolucao compatibility

The alternate endpoint remains available and preserves EM_ANDAMENTO/REALIZADA.
It shares locking, uniqueness, validation and persistence with attendance.
Client patient/module/form must match canonical ancestry and the resolved active
attendance form. Origin must be PROFISSIONAL; authorship comes from authentication.
Valid legacy clinical date and response structure are preserved. Foreign or
inactive fields and duplicate answers are rejected. An arbitrary module/form can
no longer override session identity. New correction/versioning is out of scope.

## Generic longitudinal PATCH guard

Before Daily Record dispatch or generic mutation, the existing record is locked
and checked for Session linkage. Linked canonical attendance returns 409 for all
generic PATCH changes, including patient/module/form replacement and clinical
answer replacement. The core generic update helper uses the same guard.

The record lock is acquired before the link check so a record cannot become
visible between an earlier link check and later mutation. Unrelated records
retain their existing update behavior, demonstrated by tests. The Daily Record
route fixture now includes the existing sessions table for this dependency.

No generic correction endpoint or broad longitudinal authentication redesign
was introduced. Generic longitudinal GET authentication and unrelated legacy
routes remain outside this patch-focused Wave 7 change.

## Frontend adaptation

Frontend baseline: `homolog`, `9812969892e54a71fc05c08a48af2bb86b180734`.
A separate worktree/branch isolates the change from that checkout.
Only src/services/sessoesAssistenciais.js changes: six direct axios calls now
use the existing authenticated api instance. API base URL comes from that
instance; endpoint paths, arguments, returned data and UI remain unchanged.
/minhas already used api and retains its behavior.

This adaptation was started only after the full backend suite passed.
Backend and frontend must be released together in a separately authorized rollout
because the old client omits authorization on the newly protected routes.

## Validation

No application DB was used. Tests run with source mounted read-only inside the
existing docker-api Python 3.9 runtime. The dedicated PostgreSQL 16 container has
no published ports and no external network; tests own temporary UUID schemas.

Characterization before refactor: 24 tests passed (23 imported Care Plan tests
plus the effective Neuro attendance characterization). Test discovery was then
corrected to import fixture modules without rediscovering their TestCase classes.
Focused session tests passed before the full run; final tree adds 23 session/
HTTP/contract tests and 4 PostgreSQL tests (27 new tests total).

PostgreSQL focused command:

```sh
docker run --rm --network container:integra-wave7-test-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e SESSION_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1/postgres docker-api python -m unittest discover -s tests -p test_sessions_postgres.py -v
```

Result: 4 passed. Concurrent attendance yields one success/one 409 and one record.
Attendance versus finalize respects lock ordering: if finalize wins, attendance
rejects the performed state; otherwise both succeed separately. No partial
attendance persists. Four failure checkpoints are exercised in PostgreSQL and
SQLite: first row flush, responses flush, linkage flush and commit failure.

Final backend command:

```sh
docker run --rm --network container:integra-wave7-test-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e SESSION_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1/postgres -e CARE_PLAN_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1/postgres docker-api python -m unittest discover -s tests
```

Result: 214 discovered, 211 passed, 3 skipped. Skips are the preexisting Wave 5
migration tests requiring their own WAVE5_TEST_POSTGRES_URL. All Wave 6 PostgreSQL
and Wave 7 tests ran. Neuro, Daily Record, ClinicalReading, Care Plan, Timeline,
interventions and existing consumer regression tests passed.

Changed Python files compiled with docker-api `python -m compileall -q`, directing
bytecode to /tmp/wave7-cache. No Python 3.10-only syntax was introduced.

During development the first full run exposed an incomplete SQLite fixture
(missing existing sessions table), fixed by extending that fixture. The initial
lock-observation test also matched the trailing SQL too narrowly; it was corrected
to observe the actual PostgreSQL lock wait without requiring that suffix.
Subsequent focused PostgreSQL and full runs passed.

## Limits and deferred debt

- No migration, application schema change, backfill or clinical data repair.
- Historical objective text remains live context; no snapshots/versioning.
- No attendance correction workflow: generic PATCH is intentionally rejected.
- An attendance success followed by a failed separate finalize can require a
  finalize retry. Existing frontend flow is preserved; no new retry UX introduced.
- Form option vocabularies and timezone semantics were not redesigned.
- No deployed UI/production integration test or report rendering was performed.
- No Report, Cockpit, Daily Record, WhatsApp or Responsible App redesign.
- No protection is claimed for external SQL writers bypassing these boundaries.

## Frontend verification and local commit

Frontend worktree: /private/tmp/integra-wave7-front.
Branch: feature/multiline-wave-7-sessions-attendance.
Commit: `919a4a59ad1ea8980eaaccb753e68181463bcd91`.
Only the authorized session client file changed. The original homolog checkout
and package lockfile were not changed.

The slow local dependency copy was cancelled. Dependencies were installed from
the existing lockfile with no version changes:

```sh
npm ci --cache /private/tmp/integra-wave7-npm-cache --no-audit --no-fund
npm run build -- --outDir /private/tmp/integra-wave7-front-build
./node_modules/.bin/eslint src/services/sessoesAssistenciais.js
```

All commands exited 0. Vite 7.3.1 transformed 861 modules and completed the build.
Warnings: output directory outside project root; generated JS chunk above 500 kB.
No bundle optimization was attempted in this authentication-only scope.

A Node smoke check executed the seven client functions using the existing api
interceptor and a synthetic Axios adapter. It confirmed authentication header,
endpoint paths, unchanged attendance payload and returned data, without network
requests or real tokens. The frontend ESLint check passed.

The final backend suite passed before this frontend-only modification; no backend
source was changed afterward. git diff --check passed in both worktrees. The
synthetic PostgreSQL container was stopped and removed after testing. No merge,
push or deployment was performed.
