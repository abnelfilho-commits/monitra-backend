# Wave 4 — institutional Timeline V1

Baseline: 21f40ac0378adc2a9dd6541e2d03e20d36369325.
Owner: app.services.timeline_service.TimelineService. No competing service.
Supporting models and six collectors live in app/services/timeline; they do not
own aggregation, authorization, transactions or clinical interpretation.

## Public paths

- `TimelineService.get_events(db, TimelineQuery(...))`: institutional events.
- `TimelineService.get_timeline(db, patient_id)`: retained Report acquisition profile,
  full history and original count semantics, including incorrectly classified legacy
  longitudinal entries. These dictionaries are NOT institutional TimelineEvents.
- `TimelineService.get_neuro_legacy_timeline(db, paciente_id)`: relocated Neuro
  acquisition profile. The existing HTTP endpoint delegates to this owner. Fields,
  numeric/string/bool conversions, detail IDs, source selection, full-history counts
  and creation-based visible ordering remain unchanged.
- Existing Cardio HTTP Timeline remains untouched and isolated. Its incorrect
  defaults/BMI-risk/persistence labels have not been copied to any new helper.

No new HTTP endpoint is introduced. Institutional access is a Python service API.
Callers must authorize patient context before calling the service. No source decides
permissions. Existing legacy authentication debt remains unchanged. A future HTTP
surface must reuse get_usuario_atual plus an explicitly selected existing patient/
clinic ACL pattern; ADMIN and ADMINISTRADOR helper semantics were not unified.

## Contract and scopes

TimelineEvent includes source_type/source_id, patient_id, optional resolved care_line,
care_line_association, one of five event types, title, optional clinical reference
date/time/precision, optional created_at, summary, origin, namespaced actor and copied
metadata. IDs are positive integers. No concatenated event ID is required.

Five types: DAILY_RECORD, INTERVENTION, ASSESSMENT, SESSION_COMPLETED, DIAGNOSIS.
Six identities: LONGITUDINAL_RECORD, GENERIC_INTERVENTION, CARDIO_INTERVENTION,
CLINICAL_ASSESSMENT, ASSISTENTIAL_SESSION, DIAGNOSIS.

PATIENT includes every collected patient event, including UNASSIGNED and unknown
persisted modules. CARE_LINE requires an explicit registry identifier, includes
matching EXPLICIT/DERIVED only, and excludes UNASSIGNED. Registry resolution does
not consult current active patient links: historical events must not disappear when
links or definitions are deactivated. Unknown module IDs remain in metadata with
care_line=None; no fake definition is created. Explicit/derived provenance remains
explicit/derived even when the application cannot resolve that persisted identity.

Generic interventions and diagnoses are UNASSIGNED. Longitudinal/assessment module
identity is EXPLICIT. Cardio intervention association is DERIVED from its specialized
source. Sessions derive module through agenda -> PTS only when PTS patient matches;
otherwise UNASSIGNED. No collector emits TRANSVERSAL.

## Sources and clinical boundary

Daily Record requires formulario.tipo=REGISTRO_DIARIO and matching form/record module.
Inactive historical forms/fields are not suppressed. ASSESSMENT and LONGITUDINAL
attendance forms are excluded from this institutional source. Answers must belong
to the record form. Duplicate answers are retained as separate factual rows rather
than reduced using MAX or arbitrary first-row selection.

Daily Record metadata exposes canonical answer values, not legacy direct Cardio
risk/score/protocol/BMI columns. No risk, trend, protocol, state or interpretation is
calculated, defaulted or inferred. No patient height is queried. Current ClinicalReading
is never applied to historical records. A missing summary/interpretation stays absent.
Assessment summary and classification/score are persisted assessment facts, not new
calculations. Intervention/diagnosis descriptions are source-authored content.

Actor namespaces distinguish usuarios, profissionais, responsible identities and a
physician represented only by authored name. The specialized Cardio profissional_id
is labeled by its source column rather than guessing its foreign identity namespace.
Conflicting creator columns are retained as source_actors metadata, without selecting
one as authoritative. This is not an edit-audit or authorization contract.

## Temporal semantics and exact ordering

Daily Record: clinical data_registro, DATE. Generic intervention: persisted
 data_intervencao date/time, DATETIME. Cardio intervention: no clinical reference;
created_at only. Assessment: linked record clinical date when available; execution
is separate metadata. Session: actual completion date/time when available; scheduled
execution is not invented as actual completion. Diagnosis: clinical date, DATE.

No midnight is fabricated for date-only data. A persisted midnight in a real timestamp
is retained. Missing clinical dates/times stay missing. Offsets remain attached to
original timestamps/time values. Naive values remain naive.

The ascending Python sort key implements:
1. negative clinical-date ordinal, or creation-date ordinal fallback; undated last;
2. negative presence of clinical reference (reference before fallback);
3. negative presence of clinical time (known time before date-only);
4. negative wall-clock microseconds of clinical time;
5. source_type lexical ascending;
6. numeric source_id ascending.

This is the approved calendar/clock ordering, NOT a claim of absolute UTC chronology
across unknown timezones. Creation time-of-day is not substituted for clinical time.
Legacy profiles keep their old ordering separately.

## Bounded reads and performance

FULL_HISTORY is the default. BOUNDED requires a positive limit and returns the prefix
AFTER all sources have been merged and globally ordered. No independent provider pages
are concatenated. Duplicate identities or another patient's event fail explicitly.

This is bounded OUTPUT, not bounded database work. Current sources use seven reads
(two for daily records; one per other source), followed by in-memory global sorting.
Concrete cursor pagination, indexes, snapshot semantics and large-history optimization
remain post-V1 work. No scalability improvement is claimed for source acquisition.

## Compatibility and debt

Report provider, knowledge engines and templates are unchanged. Full array/count
semantics remain in get_timeline. Neuro endpoint retains its old acquisition rules,
including labels for non-daily longitudinal records. The institutional path alone
uses corrected classification. Removal of these compatibility inaccuracies requires
separate approval because consumers use counts and clinical-display fields.

The Cardio legacy UI still has null-to-zero/green/default behavior and clinical
misinterpretation. This wave neither migrates that frontend nor claims correction of
its existing endpoint. CARDIO-DR-OBS-001 and the Responsible Cardio route remain
untouched. No Intervention write consolidation or historical data backfill occurred.

A future care line using existing structural sources requires registry definition and
metadata, not edits to aggregation. New source types require an explicit extension;
this is not an open-ended plugin/event-store framework.

## Tests and environment

Synthetic SQLite source fixtures exercise all six collectors; legacy fixtures prove
shape/count preservation, including the Report provider and Neuro HTTP ASGI facade.
No operational patient records were queried or written. No API restart occurred.
No dependency was added; no httpx is required.

Host Python 3.9 compilation passed. Host unit execution failed before tests because
SQLAlchemy is not installed. Tests run using the existing Docker Python 3.9 image,
network disabled and repository mounted read-only. Existing Pydantic deprecation
warnings originate in unchanged schemas.

Commands:

```sh
PYTHONPYCACHEPREFIX=/private/tmp/integra-wave4-pycache python3 -m py_compile app/services/timeline/*.py app/services/timeline_service.py app/routers/timeline.py tests/test_timeline.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_timeline.py

docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:///:memory: -v /private/tmp/integra-wave1:/workspace:ro -w /workspace docker-api python -m unittest discover -s tests -p test_timeline.py -v

docker run --rm --network none -e PYTHONDONTWRITEBYTECODE=1 -e DATABASE_URL=sqlite:///:memory: -v /private/tmp/integra-wave1:/workspace:ro -w /workspace docker-api python -m unittest discover -s tests -v
```

Final results: 24 focused Timeline tests passed; full suite 105 passed (Wave 1: 17,
Wave 2: 27, Wave 3: 34, Neuro characterization: 3, Timeline: 24). Compilation
passed under host Python 3.9. No PostgreSQL execution test was performed in this
Wave; collectors were exercised using isolated SQLite fixtures and typed temporal
contract tests. PostgreSQL schema/runtime parity remains part of the rollout gate.

## Pre-HML gate — no deployment authorized

- Verify deployed backend commit and Professional frontend version.
- Compare all six source table schemas, timestamps and nullable fields.
- Verify form type/code, historical metadata and module consistency.
- Verify session -> agenda -> PTS patient/module derivation.
- Verify unknown module behavior and no accidental TRANSVERSAL attribution.
- Verify full-history graphs/counts and Report counts against legacy fixtures.
- Verify Neuro card fields, dates and detail-navigation IDs.
- Verify the chosen existing ACL per ADMIN/ADMINISTRADOR/ADMIN_CLINICA/PROFISSIONAL
  before exposing a new HTTP surface; do not infer authorization from a query ID.
- Keep Cardio null/UI migration explicit; no Core clinical fallback is permitted.
- Inspect query costs and indexes before claims of production scalability.

No database migration, index, event table, materialized view, frontend modification,
clinical engine change, HML/PROD access or deployment is part of this implementation.
