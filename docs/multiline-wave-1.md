# Multi-Line foundation — Wave 1 checkpoint

Status: PASS WITH OBSERVATIONS. No Wave 2 work, deployment, migrations, frontend
changes, or changes to existing clinical code.

## Implementation and boundaries

The six existing foundation files were reviewed and retained. Definitions are frozen,
with defensively copied, read-only capability mappings and validated enum statuses.
Only ACTIVE supports an operation; missing capabilities are UNAVAILABLE. Registry
lookup accepts case-insensitive code/slug and integer/numeric-string module ID.
Duplicate IDs and aliases (including code/slug collisions) fail at construction.
An explicitly empty registry stays empty.

Resolution queries existing PacienteModulo and ModuloClinico models, filtering both
active flags and deduplicating module IDs in SQL. It neither writes nor commits.
Application-inactive and unregistered lines are excluded from automatic selection.
A synthetic third-line test proves the resolver needs no line-specific modification.
CareContext remains an in-memory value with seven fields; care_line must be a
CareLineDefinition and origin uses the four CareOrigin values. It does not itself
verify linkage: callers obtain the definition from resolve first.

The resolver is not an authorization boundary. Callers remain responsible for
patient/clinic access and actor permissions. No existing endpoint imports this package.
Dates on patient links are not assigned new lifecycle semantics: existing active flags
are authoritative. reference_date is context metadata, not a historical-resolution query.

## Error precedence

Explicit request: unknown identifier → CARE_LINE_NOT_FOUND; application inactive →
CARE_LINE_INACTIVE; capability not ACTIVE → CARE_LINE_CAPABILITY_NOT_SUPPORTED;
no active joined patient/module record → PATIENT_CARE_LINE_NOT_FOUND.
Thus an inactive database module produces PATIENT_CARE_LINE_NOT_FOUND, preserving
existing foundation semantics. No patient existence information is separately queried.

Automatic selection: no eligible active links → PATIENT_CARE_LINE_NOT_FOUND;
active links but none supports requested capability → CARE_LINE_CAPABILITY_NOT_SUPPORTED;
more than one compatible distinct line → AMBIGUOUS_CARE_LINE. Exactly one returns it.
Empty capability strings are unsupported rather than silently disabling validation.
Exception codes are institutional; Portuguese messages are descriptive, not API keys.
HTTP mapping is deferred.

## Capability evidence

ACTIVE means current implementation exists, not that a future canonical provider has
been built or that every clinical path has been validated. Existing declarations were
retained after review against branch code (not uncommitted main-checkout changes).

| Capability | Neuro | Cardio | Repository evidence |
| --- | --- | --- | --- |
| daily_record | ACTIVE | ACTIVE | routers/registros_diarios.py, services/responsavel_registro_service.py; routers/responsavel_cardio.py and cardiometabolico.py POST /registro-diario |
| clinical_engine | ACTIVE | ACTIVE | services/neuro_engine.py; services/cardiometabolico_engine.py |
| clinical_reading | ACTIVE | PLANNED | services/clinical_reading_service.py exposes Neuro only; Cardio legacy reading is not the canonical contract |
| timeline | ACTIVE | ACTIVE | services/timeline_service.py; routers/cardiometabolico.py patient timeline |
| interventions | ACTIVE | ACTIVE | routers/intervencoes.py; cardiometabolico.py patient intervention GET/POST |
| whatsapp | ACTIVE | PLANNED | services/whatsapp_conversation_service.py uses existing Neuro questionnaire |
| report | ACTIVE | PLANNED | report_engine/providers/clinical_engine_provider.py calls Neuro-only ClinicalReadingService |
| cockpit | ACTIVE | PLANNED | cockpit_profissional_service.py uses risk_analytics.py / Neuro; Cardio dashboard is not institutional cockpit integration |

Paths in this table are relative to app/. Cardio can now use registry lookup, active
patient context selection, capability gates and CareContext. Existing Cardio channels
are deliberately not rewired during this wave.

## Validation

No existing Python test suite/configuration or test dependencies were found. Existing
shell smoke scripts depend on a running authenticated service and create data. Added
stdlib unittest tests with synthetic SQLite databases using actual SQLAlchemy models.
Only the two tables needed for resolution are created; SQLite foreign-key enforcement
is not enabled and no clinical patient rows are required. PostgreSQL integration and
full authenticated application regression remain untested.

Executed from /private/tmp/integra-wave1, using this Python 3.9.6 interpreter:

```sh
WAVE1_PYTHON='/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/neuro_mvp_backend/venv/bin/python'
PYTHONPYCACHEPREFIX=/private/tmp/integra-wave1-pycache "$WAVE1_PYTHON" -m compileall -q app/services/care_lines tests
"$WAVE1_PYTHON" -m unittest discover -s tests -p 'test_care_lines.py' -v
"$WAVE1_PYTHON" -m unittest discover -s tests -v
docker run --rm --network none --read-only --tmpfs /tmp -e DATABASE_URL=sqlite:///:memory: -e PYTHONDONTWRITEBYTECODE=1 -v /private/tmp/integra-wave1:/wave1:ro -w /wave1 --entrypoint python docker-api:latest -m unittest discover -s tests -v
git diff --check
```

Results: compilation passed; targeted suite 17 tests passed; combined suite 20 tests
passed locally and in Docker. Initial compilation failed solely because macOS selected
a non-writable cache directory; setting PYTHONPYCACHEPREFIX resolved it. Docker used an
existing local image, no network, no service restarts, and no operational database.
The tests override DATABASE_URL to in-memory SQLite before model import.

Three Neuro characterization tests preserve empty-input behavior, sensory thresholds,
and combined sleep/feeding/intestinal observations. These are limited regression
checks, not complete clinical validation. Diff review confirms all pre-existing app
files outside care_lines are byte-for-byte unchanged relative to main.

## Relevant debt and checkpoint

- No pre-existing isolated automated regression suite was found.
- Patient-module rows have no uniqueness constraint; resolver now tolerates duplicates.
- Cardio has specialized legacy channel persistence and duplicated dashboard/engine
  calculations. These were consulted for capability evidence only; consolidation is later work.
- Registry persistence IDs 1/2 follow the supplied contract; deployment environments
  must maintain that mapping. Application capabilities do not override persisted state.

Work was isolated in /private/tmp/integra-wave1 on
feature/multiline-wave-1-foundation because the original checkout is on main with
unrelated uncommitted work. That work was left untouched. The six remote foundation
commits (1ba56a2 through c6e1b7a) were preserved. Review the branch at this checkpoint;
Wave 2 can be planned after human validation, but has not begun.
