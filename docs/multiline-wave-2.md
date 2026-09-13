# Wave 2 — ClinicalReading V1

## Scope and public interface

Wave 2 adds the institutional reading contract and providers without altering the
Neuro or Cardio clinical engines, routes, models, report knowledge rules, timeline,
cockpit, WhatsApp, or frontend. No migration or operational database access is needed.

```python
from app.services.clinical_reading import ClinicalReadingService

reading = ClinicalReadingService().get_reading(
    db=db, patient_id=patient_id, requested_line="CARDIO"
)
```

`requested_line` accepts the identifiers supported by Wave 1: code, slug, or module
ID. Omission is allowed only when one active compatible patient line resolves.
The service invokes CareLineResolver with `clinical_reading`, then dispatches through
an application-composition mapping of code to callable. A callable taking
`(Session, patient_id, CareLineDefinition) -> ClinicalReading` is the provider contract.
There is no new provider inheritance hierarchy or shared clinical algorithm.

Callers must enforce existing patient/clinic/actor authorization before calling this
application service. The resolver validates active linkage and capability; it is not
a replacement for access control. No new HTTP route or access path is introduced.
Provider functions are internal line adapters, not authorized channel entry points.

Existing care-line exceptions propagate. A missing registered provider raises
CareLineCapabilityNotSupported. Unexpected database failures are not disguised as
no-data readings. The service performs no commit, clinical persistence or logging.

## Contract

ClinicalReading is a frozen dataclass with these fields:

| Field | Meaning |
| --- | --- |
| patient_id | Required institutional patient ID |
| care_line | Resolved CareLineDefinition |
| reference_date | Clinical date of the latest observation selected for the current reading; None when no record exists |
| risk | Optional unnormalized line-authored domain classification |
| trend | Optional line-authored value; Cardio always None in Wave 2 |
| summary | Optional existing line-authored narrative |
| metadata | Per-instance dictionary of explicitly selected line-specific values |
| clinical_state | Optional line-specific state object |
| evidence | Optional scoped specialized evidence |
| alerts | Optional line-authored message list |

Nested metadata and optional collections are defensively copied. They remain mutable
within each reading, but do not alias provider inputs or other readings. Fields cannot
be rebound. Providers emit only selected scalar/list/dictionary values, not ORM rows,
sessions or unbounded raw records. Score and protocol are not universal fields.

Reference date is neither execution time nor creation time. This interface has no
historical cutoff/as-of input. Do not use it to imply historical report evaluation.
A selected record without usable answers retains its clinical date while explicitly
returning unavailable interpretation; the reader does not substitute an older reading.

## Neuro mapping and preservation

The provider invokes unchanged `neuro_engine.analisar_paciente` once.

| Contract | Existing result |
| --- | --- |
| reference_date | ultimo_registro |
| risk | risco_atual, including sem_dados |
| trend | tendencia, including sem_dados |
| summary | resumo_clinico |
| clinical_state | momento_clinico |
| alerts | alertas |
| evidence | eixo_dominante.base_sustentacao, explicitly scoped as axis_analysis, when present |

`resumo_clinico` is the existing current clinical panel narrative, preserving its
recent-record semantics. `status_resumido` and `interpretacao` remain separately
available in metadata. Existing report knowledge consumers use raw risk/trend/state,
so their selection and narrative behavior are unchanged by this summary choice.

Metadata also retains pontuacao_risco, protocolo, prioridade, eixo_dominante,
painel_clinico, total_registros and source. Axis evidence is not represented as a
complete risk-score explanation. No observation means reference_date=None and the
existing Neuro sem_dados classifications, explanatory text and state are retained.
No scoring, trend, state, protocol, alert, axis or summary algorithm changed.

## Cardio source and mapping

The provider uses only checked-in modular tables: RegistroLongitudinal,
FormularioModulo, CampoFormulario and RespostaRegistro. Both current specialized
Cardio write routes contain answer-row writes; the generic longitudinal update also
changes these answers. This provides a schema-backed raw source without guessing the
migration history of legacy direct columns.

Selection:

1. Patient and module match the resolved line.
2. Form belongs to that module and has tipo=REGISTRO_DIARIO.
3. Order by data_registro descending, then record ID descending.
4. Read only answers attached to that record and that record's form.

Form active flags are not used to erase historical observations. Other lines,
assessment forms, other patients and older records are not mixed into the reading.
No measurement is carried forward from another record.

Inputs are bounded to glicemia_jejum, pressao_sistolica, pressao_diastolica, peso,
atividade_fisica, sono and humor. Numeric values come from valor_numero; text values
from valor_texto. Finite numeric values are converted to plain floats. Text is passed
unchanged to preserve the existing engine comparisons. This adds no clinical range
or category thresholds; partial usable data retains the existing engine's handling
of missing individual inputs.

The same existing functions calculate the interpretation:

- calcular_score
- classificar_risco
- definir_protocolo
- gerar_leitura_clinica

The result contains engine risk and narrative. Metadata contains current-record
measurements, score, protocol, record ID, source and availability. Clinical state,
evidence and alerts remain None. Historical-max router alerts are not included.

Cardio trend is ALWAYS None, with metadata explaining that clinical validation is
pending. Neither existing trend algorithm, dashboard label, demo scoring nor timeline
BMI overwrite participates. No clinical thresholds changed.

No daily record produces risk=None, trend=None, summary=None and reference_date=None.
An empty latest record, wrong-form-only answers, ambiguous duplicate fields or invalid
typed answers produce unavailable interpretation, with an explicit availability
reason. Duplicate values are not arbitrarily merged. No older record is substituted.

### Deliberate data limitation

Direct-only legacy records, missing/mislinked answers and stale persisted derived
values are not treated as a trustworthy fallback. Such records may yield unavailable
readings despite a legacy endpoint displaying values. This is a deliberate source
policy, not a statement that deployed databases have been audited. The inspected ORM
does not declare the Cardio-specific direct columns; no schema history is invented.
No data migration or attempt to repair legacy records is included.

## Report compatibility

`app.services.clinical_reading_service` remains an import-compatible facade.
`get_neuro_reading` and `build_report_context` are explicitly legacy compatibility
methods returning the original raw Neuro dictionary. The report mapping accepts
NEURO as before and preserves its existing unsupported-module ValueError behavior.
These legacy methods retain their previous caller-side access/link validation behavior;
new consumers must use get_reading, which resolves through Wave 1.

The unchanged actual ClinicalEngineProvider is tested against full raw engine results.
No report knowledge engine has been switched to the new contract. Cardio report and
cockpit capabilities remain PLANNED. Activating clinical_reading does not enable them.

## Clinical versus continuity risk

No continuity service, days-without-records calculation, abandonment status or
operational priority is imported by the new package. An old Cardio observation can
still have the unchanged clinical engine classification; its age is not a clinical
risk input. Neuro's existing clinical rule prioridade is retained only as specialized
metadata. Continuity remains the responsibility of existing assistential services.

## Tests and exact execution

Working directory: `/private/tmp/integra-wave1` (retained worktree name; now on Wave 2).
Interpreter: existing Python 3.9.6 venv, SQLAlchemy 2.0.46. No dependencies added.

```sh
WAVE2_PYTHON='/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/neuro_mvp_backend/venv/bin/python'
PYTHONPYCACHEPREFIX=/private/tmp/integra-wave2-pycache "$WAVE2_PYTHON" -m compileall -q app/services/clinical_reading app/services/clinical_reading_service.py app/services/care_lines/registry.py tests
"$WAVE2_PYTHON" -m unittest discover -s tests -p test_clinical_reading.py -v
"$WAVE2_PYTHON" -m unittest discover -s tests -p test_care_lines.py -v
"$WAVE2_PYTHON" -m unittest discover -s tests -p test_neuro_regression.py -v
"$WAVE2_PYTHON" -m unittest discover -s tests -v
docker run --rm --network none --read-only --tmpfs /tmp -e DATABASE_URL=sqlite:///:memory: -e PYTHONDONTWRITEBYTECODE=1 -v /private/tmp/integra-wave1:/wave2:ro -w /wave2 --entrypoint python docker-api:latest -m unittest discover -s tests -v
git diff --check
git diff 5e4d9da --exit-code -- app/services/neuro_engine.py app/services/neuro_clinical_rules.py app/services/eixos.py app/services/cardiometabolico_engine.py app/services/report_engine app/routers app/models alembic
```

Results: compilation passed; new tests 27 passed; Wave 1 tests 17 passed; existing
Neuro tests 3 passed; complete suite 47 passed locally and in disposable Docker.
Diff checks passed and protected code paths are unchanged relative to Wave 1.
Wave 1's capability test now supplies its own PLANNED Cardio fixture, retaining the
same assertion semantics while the real Cardio reading capability becomes ACTIVE.

Tests exercise actual Cardio ORM queries against synthetic SQLite tables. No real
patients are used and SQLite foreign-key enforcement is not enabled in fixtures.
Neuro mapping and report compatibility execute the actual engine with its database
loader replaced by deterministic records; existing Neuro SQL is unchanged.
Tests also reject legacy/operational import dependencies and assert no invocation of
the unvalidated Cardio engine trend. PostgreSQL execution and authenticated end-to-end
flows have not been tested. No live services were restarted.

## Debt intentionally deferred / checkpoint

- Conflicting Cardio endpoint trend/risk presentation remains in legacy routes. It is
  excluded from the institutional path, not silently changed for current users.
- Direct-column/answer duplication and legacy dataset consistency remain unresolved.
- Cardio narrative wording and all clinical thresholds remain unchanged, including
  narrative claims based on single records; clinical review is separate work.
- Existing report/analytics/cockpit Neuro coupling remains outside this wave.
- No unused helper was removed: elimination offered no necessary benefit to the new
  path and was not justified by regression coverage of the legacy endpoints.

Wave 2 stops at human review. No Wave 3 / DailyRecordProvider work, frontend changes,
migrations, deployment, merge or push is included.
