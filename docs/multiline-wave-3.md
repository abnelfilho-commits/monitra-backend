# Wave 3 — Daily Record Contract V1.0

Baseline: `57779f778a5c843376161b9e989651583acc1d00` (approved Wave 2).
Branch: `feature/multiline-wave-3-daily-record`. No Wave 4 work, deployment,
operational schema migration or form metadata change.

## Institutional contract

`DailyRecordSubmission(patient_id, requested_care_line, reference_date, origin,
actor, payload)` carries structural context and a copied, line-specific dictionary.
`requested_care_line=None` permits automatic resolution only when unambiguous.
The resolver verifies application status, active persisted module/patient linkage
and ACTIVE `daily_record` capability. Both registered lines already have it.

`ActorRef(type, id)` distinguishes PROFESSIONAL, RESPONSIBLE and SYSTEM. A responsible
actor requires a positive responsible ID. A professional ID means `usuarios.id`,
not `profissionais.id`. SYSTEM has no foreign-key actor ID. An unavailable professional
ID is explicitly `None` for legacy routes that supply no authenticated identity;
no user is fabricated and no new authentication policy is inferred.

Origin describes the channel: PROFISSIONAL, RESPONSAVEL_APP,
RESPONSAVEL_WHATSAPP, SISTEMA. The submission and result keep that distinction.
For compatibility with existing Neuro reads and WhatsApp duplicate checks, both
responsible origins currently persist as RESPONSAVEL. This is lossy persisted
channel attribution; the contract itself does not collapse the origins.

`DailyRecordResult(record_id, patient_id, care_line, reference_date, origin,
created_at)` contains the resolved CareLineDefinition. New rows receive their
creation timestamp from PostgreSQL. Historical nullable creation timestamps remain
nullable on update, rather than being replaced with now. ClinicalReading, score,
risk, protocol and narrative are not fields of this result.

`reference_date` is the explicit clinical date, never the creation timestamp.
Professional Cardio's legacy adapter supplies `date.today()` because its public
payload has no date. No provider or SQL insert generates the clinical date.
Generic professional Neuro keeps user-selected dates. Neuro responsible submissions
preserve today/yesterday restrictions. No universal date or duplicate policy is added.

## Service and provider boundary

`DailyRecordService.create(db, submission)` and `update(db, record_id, submission)`
resolve the care line, dispatch through a small provider mapping, and own commit and
rollback. Callers must provide a session dedicated to the operation; unrelated
pending work must not share this transaction. Authorization remains with the channel.

Providers expose `prepare` and `persist_projection`; neither commits. Core contains
no clinical fields, thresholds, risk scales or clinical aliases. Provider registration
and line implementation are the extension points for a future care line.

Forms must be active, belong to the resolved module and have type REGISTRO_DIARIO.
Zero forms is an explicit error; multiple active forms is an ambiguity error. No
unordered first-form fallback exists. Fields must be active and belong to that exact
form. Missing fields and duplicate active names fail explicitly. Physical IDs are
internal persistence details; legacy HTTP adapters translate incoming field IDs only
after verifying their selected-form membership.

## Canonical persistence and transaction

Canonical current submissions are longitudinal headers plus answer rows. The shared
`persistir_registro_longitudinal` primitive adds/flushed headers and adds typed answers
without committing or logging clinical values. The old public helper delegates to it
and retains its commit and post-commit assessment hook for old callers.

Institutional writes: resolve/prepare → header/answers → flush → provider projection
→ flush → materialize result → one commit. Any failure before successful completion
rolls back. No service refresh is performed after commit. Legacy response adapters
may still query the saved row to reconstruct their existing response shapes.

Update locks the record, prohibits patient/module/form reassignment, replaces answers
and refreshes/clears the supported Cardio projection in the same transaction. A failed
update retains previous answers and projection. Creation actor columns remain creation
attribution, not an edit audit log. The existing professional frontend supplies
PROFISSIONAL origin on edits; that behavior and selected-date changes are preserved.
No revision-history schema or new authorization model is introduced.

## Neuro preservation

The provider resolves nine named fields rather than IDs 34–42. It reuses the existing
responsible payload schema for type validation/coercion, without new questionnaire
ranges or enum thresholds. Existing values, including null answers, are retained.
Evacuation/Bristol channel behavior is preserved; the provider does not infer new
visibility metadata or silently clear a supplied Bristol value. Professional editing
already permits its supplied values; WhatsApp still controls its own conditional flow.

Responsible duplicate checks retain patient/module/form/date/shared RESPONSAVEL scope,
not responsible-user scope. New contract origin variants are also recognized.
Check-before-insert is not concurrency-safe idempotency and is not claimed as such.
No mandatory retry key or uniqueness constraint is added.

Neuro engine and ClinicalReading are untouched and are not invoked during writes.

## Cardio mapping

The institutional payload supports exact fields:
- numeric: glicemia_jejum, glicemia_pos_prandial, pressao_sistolica,
  pressao_diastolica, peso, altura;
- text: atividade_fisica, sono, humor.

Numeric values must be finite. Values are not rounded across engine thresholds.
The local PostgreSQL numeric answer column is unconstrained numeric despite the ORM's
Numeric(12,2) declaration; PostgreSQL tests include 179.999 to protect the existing
calculation and reading. HML numeric precision/scale must be checked explicitly.

`atividade_fisica` text is retained because the active API schema, legacy writer,
canonical engine and Wave 2 provider establish that representation. It is NOT
converted into the metadata's boolean interpretation. `sono` is not an alias of
`qualidade_sono`. No medication, food-adherence or observations alias is introduced.

Score, risk, protocol and narrative call the unchanged Cardio engine functions.
Only usable engine inputs trigger interpretation; no usable data produces null
interpretation, not fabricated low risk. Cardio trend remains unavailable in Wave 2
ClinicalReading and is not calculated here.

The provider prepares direct measurement/interpretation compatibility columns from
the same values persisted as answers, then writes them before the service commit.
Omitted supported projection values are cleared on replacement updates. Height has
an answer but no added direct column. No new database column is created.

The professional compatibility adapter forwards the supported effective clinical
fields. Previously ineffective payload fields (including medication/adherence names
without corresponding active Cardio fields) are not given new clinical mappings.
The strict institutional API rejects unsupported field names. Fields outside this
supported subset must receive a separately validated canonical representation before
being added; the current form's 33 fields are not all claimed as supported inputs.

## Route compatibility

Migrated:
- POST /registros-longitudinais/ for Daily Record forms;
- PATCH /registros-longitudinais/{id} for Daily Record forms;
- POST /responsavel/pacientes/{id}/registros for Neuro;
- POST /cardiometabolico/registro-diario.

Existing response shapes are retained. The legacy generic HTTP adapter accepts the
established professional origin; it is not a generic responsible-authentication
adapter. Invalid identity/form/field combinations fail rather than attaching data
to a different patient/line/form. Active linkage is now required through Wave 1.
Assessment and other non-Daily-Record generic routes retain the legacy helper.

Responsible Neuro authentication, active relationship/patient checks and date errors
remain. Creator ID is now persisted; the existing response shape remains unchanged.
No authorization dependency was removed. Generic/professional Cardio routes still
lack an authenticated actor dependency: this is existing security debt, not authorization
provided by the clinical provider. ActorRef alone is not proof of authorization.

## Approved exclusion and remaining debt

**CARDIO-DR-OBS-001 — Define and validate the canonical representation of general
Cardio Daily Record observations before migrating the Responsible Cardio write path.**

POST /responsavel/pacientes/{paciente_id}/registros-cardio is unchanged by explicit
human approval. It continues accepting/persisting observacoes. No mapping to
sintomas_gerais, intercorrencias or another field was introduced. No value is discarded
or rejected on this route. Full Cardio channel convergence is NOT claimed.
Its direct-only observations remain legacy primary data, outside the new provider's
supported projection subset. Existing records are not backfilled or reinterpreted.

Other known limitations:
- WhatsApp conversation, webhook, outbound messages and existing writer remain Wave 4.
- Old internal generic helper callers can still bypass the institutional boundary;
  no claim is made that every legacy write/edit path is eliminated.
- Existing direct Cardio values outside the supported subset are not migrated.
- Neuro read endpoints and WhatsApp still contain legacy form/field constants.
- Professional Neuro timeline deletion still targets legacy /registros/{id}; this
  confirmed storage mismatch is backlog, not tested through destructive deletion.
- No retry/idempotency guarantee, edit audit history, actor database constraint or
  institutional authorization redesign was added.
- WhatsApp's existing clinical-content logging is unchanged; the shared primitive no
  longer prints answer values. New boundary errors do not log clinical payloads.

## HML compatibility gate — no deployment authorized

Before any separately approved HML rollout, compare local and HML:
1. registros_longitudinais columns, types, precision/scale, defaults and constraints;
2. respostas_registro types, precision/scale, constraints and indexes;
3. active Neuro Daily Record form and all nine named fields;
4. active Cardio form and supported exact field names, including text/boolean mismatch;
5. active patient/module links required by resolution and consumers of legacy routes.

HML was not accessed or verified. No operational migration, metadata edit, trigger,
constraint, data migration or destructive patient-data test occurred. PostgreSQL tests
create synthetic fixtures only inside a disposable, network-isolated PostgreSQL 16
container with tmpfs storage and no host ports or operational volumes.

## Validation commands and results

Final results: 81 tests passed in the full suite (Wave 1: 17; Wave 2: 27;
Neuro characterization: 3; Wave 3: 34). All 34 Wave 3 tests also passed against
the disposable PostgreSQL 16 instance. Python 3.9 compilation and diff checks passed.
Test commands are reproducible from the
worktree using the already available local `docker-api` image (Python 3.9).

```sh
PYTHONPYCACHEPREFIX=/private/tmp/integra-wave3-pycache python3 -m py_compile app/services/daily_record/*.py app/services/daily_record/providers/*.py app/services/registros_longitudinais.py app/routers/cardiometabolico.py app/routers/registros_longitudinais.py app/routers/responsavel_registros.py tests/test_daily_record*.py

docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:///:memory: -v /private/tmp/integra-wave1:/workspace:ro -w /workspace docker-api python -m unittest discover -s tests -v

docker run -d --rm --name integra-wave3-pg --network none --tmpfs /var/lib/postgresql/data -e POSTGRES_USER=wave3 -e POSTGRES_DB=wave3_test -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16-alpine

docker run --rm --network container:integra-wave3-pg -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:///:memory: -e WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test -v /private/tmp/integra-wave1:/workspace:ro -w /workspace docker-api python -m unittest discover -s tests -p 'test_daily_record*.py' -v

docker stop integra-wave3-pg
git diff --check
```

The fixture URL is intentionally restricted to the disposable test database. Each
PostgreSQL case uses an isolated synthetic schema. No operational database URL is used.
Initial environment failures: host Python lacked SQLAlchemy and its default cache path
was not writable; compilation used a temporary cache and tests used the existing Docker
runtime. HTTP tests initially found httpx absent, so a dependency-free ASGI harness was
used. Its SQLite cross-thread fixture was corrected with StaticPool/check_same_thread.
These were resolved environment/test-fixture failures, not suppressed test results.
