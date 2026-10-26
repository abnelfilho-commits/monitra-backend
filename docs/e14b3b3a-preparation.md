# E14B.1 / 3B.3A — preparation and transport coordination

Baseline: homolog, 4a36ee8e85c2e33742d4a211244a9d2bb77c21f0.
No migration. Canonical head remains e14b3b2_comunicacao.

## Contract

prepare(db, followup_id, manual=False) remains caller-committed. It obtains
transport coordination before canonical care locks, reloads the followup and
rejects changed destinations. It checks pending/uncertain executions, recipient
and contextual communication barriers, E12C, clinical scope and scheduling.
Only this followup's expired OPEN conversations are expired. Creation is allowed
only when no OPEN conversation remains for that followup.

The still-existing uq_wcc_aberta_telefone requires a temporary compatibility guard:
an OPEN row for another followup with the exact phone blocks preparation even
if temporally expired. That row is NOT expired or otherwise modified. No schedule
is advanced on that refusal. eligible_ids uses the same conservative exclusion.
This is not full support for concurrent same-phone conversations. The future
index-removal gate must remove this guard together with safe routing activation.
The per-followup unique index also remains unchanged.

Automatic creation retains its weekly schedule behavior. Manual preparation
ignores the future schedule but never advances it. No changes to attribution,
clinical dates, questions, SIM, PARAR, or communication events.

## Ordering

Entry commands with idempotency acquire their operation key first. Full emitter /
transport plans are sorted and acquired before legacy raw-phone compatibility
locks and before canonical care/followup/conversation/receipt/audit locks.
Communication barriers need no separate row lock: their append and read/write
operations share the same transport serializer, including proven aliases.
The complete old/new phone set is declared before a configuration change.
Raw compatibility locks also have bounded waits and roll back on timeout/deadlock.
No retries or HTTP occur in the coordinator.

Manual/auth preflight checks the SAME write permission without row locks;
permission is revalidated under canonical care locks after coordination. This
is not a bypass flag exposed to API consumers. Revocation locks conversations
before appending its evidence. Daily Record FOR NO KEY UPDATE is unchanged.

Ingress changes are lock acquisition ONLY. Explicit reference resolution and
legacy dispatch remain identical. Lock-only evidence collection does not confer
identity and lets the existing resolver refuse invalid evidence normally.
No multiline resolver or new PARAR command is connected to ingress.

## Identity and attempts

Cross-followup blocking attempts use exact emitter and exact or directly proven
Meta destination aliases. Same-followup uncertain executions remain blocking even
if the emitter/destination changes. Pending manual requests have no emitter
snapshot: retain conservative blocking for matching proven destinations or the
same followup rather than infer a historical emitter. 12/13 lock-key contention
is never used as an identity match.

## Operational limitations

Code should not be mixed with old processes: old writers do not share every new
operation key. No HML activation is included. This stage does not prove universal
absence of deadlocks; external identity/grant writers and future routing callers
must retain canonical ordering. Unknown outcomes remain reconciliation-only.
No persistent database, Docker configuration, Meta, frontend, or deployment changes.

## Validation

Final results and sanitized log paths are reported in the delivery. Tests use
owned disposable databases on the preexisting isolated PostgreSQL 18 resource,
127.0.0.1:55620. No production/homologation/demo database is a test target.

Final local validation: 339 distinct PASS, 0 FAIL, 0 ERROR, 0 SKIP.
308 main/new tests + 31 legacy tests, no overlap. All 322 baseline test IDs
are present; 17 new test IDs. PostgreSQL 18.6, Python .venv-e12.
Logs: /private/tmp/e14b3b3a-verified.log and
/private/tmp/e14b3b3a-legacy.log. Main database inventory restored exactly;
legacy runner removed e14b_legacy_cc27b4e51edf400c896f54c3b382a98f.
Earlier runs exposed two corrected integration regressions (reference refusal and
write-authorization preflight) and invalid expired-fixture timestamps; final
rerun passed all scenarios without weakening constraints. Existing LibreSSL
warning persists. Syntax and diff checks pass. No commit/push/deploy.
