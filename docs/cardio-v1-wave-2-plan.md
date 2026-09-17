# WAVE 2 — AS-IS + EXECUTION PLAN

2026-09-17. Plano/AS-IS histórico, anterior à implementação.
CARDIO-DR-OBS-001 e a correção transversal WhatsApp foram posteriormente aprovados.
Implementação e Gate técnico isolado concluídos; configuração real Meta pendente.
Consulte cardio-v1-wave-2-checkpoint.md para decisões finais e evidências.
Gate 1 permanece fechado.

## Confirmed AS-IS

- Professional Cardio endpoint (`app/routers/cardiometabolico.py:1333`) invokes
  DailyRecordService via call_write. It has no authenticated user dependency and
  supplies an anonymous professional ActorRef. It translates only NUMERIC/TEXT
  provider fields, despite its schema accepting other fields.
- Professional form (`src/pages/cardiometabolico/RegistroDiarioCardiometabolico.jsx`)
  sends `observacoes` (lines 114-115); the translation above omits it.
- APP route (`app/routers/responsavel_cardio.py:41`) validates responsible-patient
  linkage but writes its own SQL. It explicitly persists `observacoes` into
  registros_longitudinais (lines 138,158,177). Its answer field lookup is by name
  without form scope (lines 199-207), which requires correction.
- `app/services/daily_record/providers/cardio.py:8-18` accepts only its enumerated
  measurements/text fields; `observacoes` is not supported. `prepare` invokes
  resolve_fields, requiring each answer key to exist in the active form.
- Read-only metadata check on 2026-09-17: active Cardio Daily Record form ID 1
  includes numeric glicemia_jejum, pressao_sistolica, pressao_diastolica and peso.
  Neither observacao nor observacoes exists among its active fields. The existing
  registros_longitudinais.observacoes column is text. No records were read.
- Previous explicit decision remains documented in `docs/multiline-wave-3.md:146`:
  CARDIO-DR-OBS-001 requires representation validation before migrating the
  Responsible Cardio write path; no invented alias, rejection or loss of value.
- WhatsApp currently selects a patient/date but writes Neuro through
  ResponsavelRegistroService with hardcoded module/form IDs. It needs explicit
  care-line resolution before questionnaire dispatch; preserve Neuro answers.
- APP and WhatsApp institutional origins currently collapse to RESPONSAVEL in
  DailyRecordService. Channel provenance needs an explicit persisted solution
  while preserving existing Neuro compatibility reads.
- WhatsApp's public test endpoint and POST webhook lack sender authenticity
  enforcement; raw message/response logging exposes clinical payload. These are
  directly relevant safety corrections, not authorization to send test messages
  to real recipients or alter secrets.

## Smallest execution plan after representation validation

1. Authenticate professional Cardio writes; validate clinic/patient/line through
   the existing access boundary; propagate actual user identity.
2. Preserve clinical thresholds and existing form measurements. Normalize empty
   numeric UI inputs without turning missing observations into low/stable risk.
3. Resolve the Cardio APP form/fields within its active care line; preserve its
   accepted observations exactly under the representation selected below.
4. Reuse the institutional DailyRecordService for converged writes; retain
   transaction and duplicate-date contracts, with synthetic rollback tests.
5. Add explicit WhatsApp care-line selection only when patient context is
   ambiguous; use line-owned questionnaire dispatch. Preserve Neuro rules and
   validate responsible/patient links again before persistence.
6. Preserve channel provenance independently of care line. Protect webhook and
   diagnostic routes; never exercise real outbound delivery in tests.
7. Validate Portal/APP/WhatsApp against the same synthetic longitudinal storage,
   explicit actor/context, current ClinicalReading and isolated Timelines.
8. Keep Cardio interventions independent of PTS; retain the ownership/authorship
   behavior already validated in Gate 1. No new clinical indicators.

## Historical decision request: CARDIO-DR-OBS-001 (resolved: option A approved)

This is a current field contract, not a problem caused by old test records.
Deleting the current mass does not resolve the input mismatch.

The code cannot simultaneously migrate the accepted APP payload unchanged into
its current provider and preserve `observacoes`: the provider rejects this key,
while excluding the key loses the APP value and perpetuates Portal omission.
The prior decision forbids creating metadata or guessing an equivalent field.

Reviewable options:

A. Validate the **existing registros_longitudinais.observacoes text column** as
   the canonical line-specific storage for general Cardio observations. Extend
   the provider to preserve that field separately from questionnaire answer
   keys, with no alias to symptoms/intercurrences and no effect on scoring.
   No new form metadata would be needed. This is the smallest technical change,
   but changes its status from excluded legacy field to validated domain input.

B. Approve a distinct canonical Cardio questionnaire field `observacoes`, with
   its own explicitly validated semantics and compatibility with the existing
   column. Requires a separately authorized metadata change; no invented alias.

C. Keep the explicit Responsible route exclusion. Its existing value remains
   preserved, but full provider convergence cannot be claimed; the Portal's
   accepted-and-omitted observations still need a product decision.

At the time of this initial plan no option was implemented. Option A is now implemented.
No observations were discarded, renamed or migrated.
No shared database changes, frontend Wave 2 changes, outbound messages or deploy.

## Wave 1 handoff

Backend: 04b036b9f63004657c1cb3d43742afd5961e92d4.
Frontend: dcedac7 (full hash in repository history).
Report: docs/cardio-v1-wave-1-checkpoint.md.
231 full-suite tests passed, zero skipped; Python 3.9 compile 233 files;
four browser diagnosis journeys plus intervention/Timeline and ACL checks passed;
frontend build/lint and both diff checks passed. Shared DB untouched.
