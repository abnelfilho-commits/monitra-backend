# Cockpit Profissional Multi-Line — Implementation Gate

2026-09-20. Local implementation only; no HML access, push, merge or deployment.

## Baselines and contract

Backend `8b93dc19139b80032b82c26863d283bd402c5466`; frontend
`76b6631ff84763a8a412a5277f7e7bf0e8e84dee`, branch
`codex/cardio-v1-stabilization`. Approved baselines were opened in new worktrees
`/private/tmp/integra-cockpit-backend` and `/private/tmp/integra-cockpit-frontend`.
Incomplete older worktrees were preserved; the homolog worktree was not edited.

`GET /cockpit/profissional?care_line={id}&offset=0&limit=5`
requires explicit context, even for a professional with only one line. Missing or
empty context returns 422; unknown/inactive lines return the existing institutional
400 errors; unauthorized professionals return 403. No automatic selection/fallback.
Limit is bounded to 1–100. One request produces one line, never an aggregate cockpit.

Response has `care_line`, `module_id`, capabilities, `total_pacientes`,
`pacientes_prioritarios`, `atividades_recentes`, priority pagination and a
presentation identifier. Cardio additionally carries its existing composition
under `composition`, consumed by the existing Cardio view; clinical concepts are
not normalized to Neuro fields.

## Composition and security

- `CockpitProfissionalService` authorizes with `authorized_line`, validates the
  cockpit capability and dispatches through a small composition mapping.
- Both compositions reuse `list_patients`: active patients, active linkage to the
  selected line, clinic isolation. There is no added ownership restriction through
  `Paciente.profissional_id`.
- Neuro uses institutional `ClinicalReadingService.get_readings`. Acquisition is
  batched; individual and batch providers call the same unchanged interpretation
  body. No clinical threshold, trend, alert, protocol or summary rule changed.
- Neuro priorities retain `alto_risco`/`atencao`, descending score then record count.
- Cardio delegates to the already approved `cardio_longitudinal.cockpit`, including
  its institutional reading, continuity, Priority and bounded Timeline composition.
  No Neuro engine executes for Cardio. No new trend or no-data classification.
- Institutional Timeline collectors are reused with optional line filters and
  bounded acquisition. Default Timeline/Report behavior remains unchanged.

## Activities and temporal compatibility

| Source | Line boundary | Neuro presentation date |
|---|---|---|
| Daily record | Record module and matching form module | Creation timestamp, existing clinical-date fallback |
| Generic intervention | Intervention's own module | Creation timestamp, authored date fallback |
| Assessment | Assessment's own module/patient | Creation timestamp |
| Completed session | Canonical agenda → PTS module; PTS patient must match | Realization date, scheduled-date fallback; completion time |
| Diagnosis | Diagnosis's own module; canceled excluded | Authored diagnosis date |
| Specialized Cardio intervention | Existing Cardio Timeline module filter | Existing Cardio event presentation |

Neuro retains one newest event per patient, up to five patients, with the existing
bounded candidate policy (15 per source). It is not converted to a general feed.
Cardio retains its approved chronological event feed, which may contain several
events for one patient. Reference dates remain separate from creation timestamps.
Legacy/null associations do not fall back to Neuro.

## Frontend

The professional dashboard reads the explicit URL `care_line` and presents only
lines returned by `/me`. The URL is the context, not a second global state store.
The platform's Neuro entry passes line 1 explicitly. A context-free dashboard asks
for selection and makes no cockpit request, including single-line users.

The existing Neuro layout moved to `NeuroDashboard`; Cardio reuses its existing
view. Changing line remounts the view. Both loaders reject stale responses after
unmount. Cardio makes no session/PTS requests and professional Cardio now uses the
shared endpoint. Administrative Cardio calls remain unchanged. Neuro priority,
recent activity and quick-action links explicitly retain Neuro context.

## Validation evidence

- `python -m unittest discover -s tests -p test_professional_cockpit.py`: **11 PASS**
  on disposable PostgreSQL 18.
- `python -m unittest discover -s tests`: **357 PASS, zero skips**, 32.132 s.
  Includes line authorization, ClinicalReading, longitudinal/priority, Timeline,
  Report/PDF, Daily Record concurrency, WhatsApp and migrations regression.
- PostgreSQL query measurement: Neuro **14 → 14**, Cardio **16 → 16** after adding
  50 patients. No query per patient/reading/source. Recent collectors are bounded;
  clinical history needed by the unchanged Neuro algorithm is still loaded in batch.
  This is a query-count regression test, not a production load benchmark.
- `node tests/professional-cockpit.cjs`: **9 browser scenarios PASS**, Chrome,
  synthetic intercepted HTTP responses. Covers explicit context, both line-switch
  directions, delayed responses both directions, widgets, links, single/multi-line,
  and no incompatible requests. Backend HTTP behavior is independently exercised
  through FastAPI ASGI against real disposable PostgreSQL; no external API was used.
- `npm run build`: **PASS**, 867 modules. Existing bundle-size warning remains.
- `npx eslint` on the eight affected JS/JSX implementation files: **PASS**.
- Python **3.9.25**, in-memory `compile`: **13 affected/provider/Timeline files PASS**.
- AST comparison against approved backend: all unchanged Neuro clinical functions
  identical; extracted `analisar_registros` body identical to the previous
  `analisar_paciente` interpretation body.
- `alembic heads`: **8c01a0d1a004 (head)**, one head, no database connection.
- `git diff --check` in both worktrees: **PASS**.

Full backend command used the existing `docker-api` Python 3.9 image, a read-only
mount of this worktree, `PYTHONDONTWRITEBYTECODE=1`, and network namespace of
`integra-remediation-pg18`. No shared database was connected. Environment:

```text
REMEDIATION_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
CARDIO_GATE1_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
CARE_PLAN_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
SESSION_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
WHATSAPP_TEST_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
CARDIO_GATE3_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
CARDIO_GATE4_POSTGRES_URL=postgresql+psycopg2://gate1@127.0.0.1/gate1_test
WAVE3_TEST_POSTGRES_URL=postgresql+psycopg2://wave3@127.0.0.1/wave3_test
WAVE5_TEST_POSTGRES_URL=postgresql+psycopg2://wave5@127.0.0.1/wave5_test
```

These are fixed synthetic disposable test roles, not deployment credentials.
Frontend browser command used `PLAYWRIGHT_MODULE` pointing to the installed local
Playwright runtime and local Vite at `http://127.0.0.1:5176`, with
`VITE_API_URL=http://127.0.0.1:8998` intercepted by the test.

Initial regressions exposed a shared-session query change and a test using the old
cockpit interface. The session enrichment is now opt-in, and the intervention test
preserves newest-per-patient behavior while asserting own-line exclusion. A fixture
missing its required physician field and ambiguous browser locator were corrected.
The final complete suite passed; failed intermediate runs are not counted as PASS.

## Scope and remaining debt

**COCKPIT GESTÃO MULTI-LINE — revisão futura obrigatória.** The Gestão service and
route body are unchanged. This implementation does not claim Gestão isolation.

No new migration. Approved Alembic history, remediation SQL, Daily Record lock
order, APP/WhatsApp concurrency, webhook authorization and Report Engine code are
unchanged. HML was not accessed. No push, merge, deploy or new wave was performed.
The frontend bundle warning and existing Pydantic deprecation warning are outside
this bounded correction. HML smoke remains a separate, future authorized step.

Gate: **PASS** for the local implementation and requested regression matrix.
