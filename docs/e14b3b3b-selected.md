# E14B.1 — 3B.3B: dormant selected conversation orchestration

Baseline fef4fc6a6ee228a2e1aa3d2716e56d07710bfb2d; branch homolog.

`whatsapp_selected.process_selected` is an INACTIVE transaction owner. It is not
imported by ingress, routers or a feature flag. It returns a reply, never invokes
HTTP or deliver_reply. Operational dispatch, PARAR, templates, schedules and
communication transitions are unchanged. No migration or index removal.

## Selection and execution

Frozen Selection captures kind/line, institution (legacy clinica namespace),
patient/person, followup or responsible, conversation, emitter, transport sender,
message/reference, evidence IDs and a state digest. Navigation adds the complete
patient plan. Transport identifiers are in memory only; audit excludes them.
The selection is not an authorization token. The service rebuilds it under locks
before executing a canonical selected handler. Callers cannot supply a Selection.

Explicit reference is emitter+wamid, validated against transport identity and the
exact linked conversation, eligibility and prior authorization. Unknown, stale,
ineligible or contradictory references never fall back. Without reference the
existing 3A read-only resolver supplies all candidates. Multiple eligible
candidates are refused. Historical/incompatible candidates do not start a menu.
PARAR is persistently refused by this dormant path pending its separate stage.

Legacy clinical execution reuses processar_mensagem(selected=...) and never does
phone lookup. Mental execution reuses receive(conversation_id). Invalid selection
is an audited refusal; handler failures roll back receipt, decision and effects.

## Navigation

Only an existing unique INICIO/SELECIONAR_PACIENTE session may resume, with a unique
active responsible and all active patient links eligible. No eligible competing
clinical conversation may exist. All patient identities are locked before links
and session. Patient selection can only pick from this declared set. Navigation
is not clinical authorization; the canonical handler revalidates the selected
patient and line. Fresh-menu fallback remains a safe refusal
NAVEGACAO_REQUER_PLANO: this stage never creates a legacy session implicitly.

## Locks, replay, persistence

Read a clean proposal; declare operation + full emitter/transport set through
coordinate_many, including original and proven transport destinations. Rebuild
candidate set after transport locks; changed sets are refused without new locks.
Acquire selected canonical care locks (Daily Record NO KEY UPDATE preserved),
rebuild again, check communication barrier/E12C, then insert receipt and execute.
The canonical handler only reacquires already-held identity locks. Audit and
receipt commit with effects, without intermediate commits. Same message_id uses
the existing ingress operation key. Exact replay returns stored response; changed
fingerprint returns 409. v1 receipt compatibility is retained without allowing a
new explicit reference to match an old unreferenced receipt. No automatic retry.

Existing receipt result codes retain target-link semantics; precise outcomes,
candidates, selection and executed target are in whatsapp_resolucoes JSON.
No new values in schema constraints are needed. The head stays
e14b3b2_comunicacao; both open-conversation unique indexes remain.

## Limits / 3B.3C dependencies

No activation, no PARAR integration, no complete operational support for multiple
open mental conversations on the same phone. Legacy institution IDs remain in
the legacy clinic namespace; no new institutional crosswalk is inferred.
Future activation must coordinate every writer, integrate communication
interruption, and remove the phone index only under the approved deployment gate.
Mixed old/new processes are not an approved activation scenario. Tests do not
prove universal absence of deadlocks, particularly against external identity
writers that do not share the canonical locks. Fresh navigation creation remains
explicitly refused until its identity plan is implemented and validated.

## Executed validation

PostgreSQL 18.6, owned disposable databases only on 127.0.0.1:55620.
376 distinct PASS, zero final FAIL/ERROR/SKIP: all 339 baseline IDs plus 37 new.
Main run: 329 PASS (308 baseline + 21 preliminary new); final selected run: 37
PASS; legacy run: 31 PASS. The 21 preliminary IDs overlap the final selected
run and are counted only once. No overlap with the legacy run.
Logs: /private/tmp/e14b3b3b-tests.log,
/private/tmp/e14b3b3b-selected-complete.log,
/private/tmp/e14b3b3b-legacy.log. Database inventories preserved and owned
databases removed. Intermediate fixture failures were corrected without weakening
constraints or E12C: shared synthetic phones, unbound transport evidence, and
renewed authorization evidence timestamp after phone-change revocation.
Final tests include real PostgreSQL lock wait, concurrent replay, changed
selection refusal, rollback, navigation, 12/13 proof, clinical barriers and
isolation between patients and institutions. Syntax and diff checks passed.
Existing urllib3/LibreSSL warning remains. No external HTTP, persistent migrations,
commit, push, deploy or production ingress activation.
