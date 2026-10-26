# E14B.1 / 3B.1 — transaction lock coordination

No migration or resolver activation. No changes to prepare, selection, PARAR,
consent, scheduling or the existing unique indexes.

## Contract

`whatsapp_locks.acquire(session, resources, timeout_ms=...)` receives the complete
advisory plan. Resources sort by phase, namespace and tuple of string parts;
duplicates are acquired once. All callers must use the same namespaces and
stable string representations of IDs. Phases are operation idempotency (10),
emitter/transport (20), communication barrier (30), care identity (40),
followup/conversation (50), requests/attempts/receipts (60).

These are advisory coordination resources, NOT substitutes for canonical row
locks or persistence uniqueness. Acquire the full plan before row locks. Preserve
canonical institution/identity/followup locks, and Daily Record responsible,
patient, link, record order with FOR NO KEY UPDATE. Do not replace these helpers
or add stronger locks. Further adoption at ingress, authorization and preparation
requires the 3B.2 call-site audit. This stage integrates only transport message
correlation. Communication barriers do not yet exist.

Recipient lock keys are emitter-scoped. A 13-digit Brazilian number beginning 55
with a ninth digit at position 5 shares contention with the 12-digit form.
This is deliberately conservative SERIALIZATION, never evidence of identity,
lookup aliases, authorization or a modification of stored numbers.

State is scoped to the root Session transaction. Repeated resources are harmless;
a newly requested resource below the acquired order rolls back and fails. The
plan must be acquired before savepoints. Autoflush is suppressed. Optional
lock_timeout is transaction-local and restored after successful acquisition.
PostgreSQL deadlock, lock timeout or cancellation rolls back the transaction and
raises a sanitized LockUnavailable. There is no retry, commit or external IO.
Existing code outside this coordinator can still violate ordering; the API cannot
inspect arbitrary previously acquired row locks. Do not claim global deadlock
freedom. It requires PostgreSQL and is not a SQLite lock abstraction.

## D9.2 integration

The deployed message advisory-key algorithm is unchanged. Callback batches take
all sorted emitter/wamid locks before persistence. Invitation acceptance now
takes the message lock before conversation and attempt rows, then records the
same acceptance/evidence and correlates early callbacks. No clinical state
changes. HTTP remains outside the transaction. Failure after external acceptance
uses the existing INCERTO/EM_EXECUCAO protection, never automatic resend.

## Remaining work (3B.2)

Adopt full operation and transport plans before all canonical row locks; validate
evidence-key set changes before external IO; harmonize existing phone locks across
entry points; implement communication barriers and durable text outbox separately.
Do not activate multiline routing or remove global phone uniqueness in this stage.

## Tests

`tests/test_whatsapp_locks.py` uses the existing owned migrated PostgreSQL fixture.
Covers reversed plans in two concurrent connections, blocking until commit,
variant contention and timeout, rollback of transactional DDL, recovery without
retrying IO, emitter independence, transaction reset/idempotent acquisition,
late-order rejection, existing message key compatibility and NO KEY UPDATE SQL.
Existing delivery/status suites cover callback correlation, delivery concurrency,
duplicate events and uncertain outcomes. No actual Meta requests are performed.
