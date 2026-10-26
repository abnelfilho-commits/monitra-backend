# E14B.1 — 3B.2: communication infrastructure (local, not deployed)

## Scope / activation boundary

The live ingress still uses the previous dispatch and explicit context.id resolver.
It DOES NOT call `whatsapp_comunicacao.interrupt` or the multiline resolver.
Existing PARAR/clinical transitions in `whatsapp_mental.receive` are unchanged.
The new interruption contract is exercised directly in isolated PostgreSQL tests,
not claimed as an end-to-end deployed PARAR feature. Activation/revalidation of
candidate sets, harmonization of preparation and phone-index removal are 3B.3.
No automatic PARAR acknowledgment is sent by the new command.

The two actual application outbound callers now use the communication barrier.
Text execution intentionally stops retrying uncertain responses, including old
receipts not previously marked sent; old already-sent receipts remain skipped.

## Persistence and timeline design

Migration `e14b3b2_comunicacao`, parent `e14b3a_multilinhas`, is additive. It creates:

* `whatsapp_comunicacao_eventos`: immutable append-only communication history,
  scoped to followup OR official-emitter/recipient (hashed), chained with unique
  predecessor/root, unique operation digest and unique incoming message FK.
  Context/patient/institution are protected by composite FKs to existing entities;
  Pessoa is derived through the existing Paciente relationship, not duplicated.
* `whatsapp_resposta_execucoes`: one durable execution per incoming receipt, emitter,
  recipient, contextual/legacy conversation or navigation origin, timestamps,
  observed HTTP result and wamid. No duplicate reply/clinical-content column.

Both existing open-conversation unique indexes remain unchanged. No opt-in,
backfill, phone rewrite, historical receipt rewrite or clinical migration occurs.
Downgrade fails closed and requires an independently approved recovery procedure.

The existing contextual journey composes read sources. Generic timeline sources
represent clinical observations/attendances and are not appropriate persistence
for a communication decision. The operational ledger is therefore projected once
into `JornadaMentalDetalhe.comunicacao_whatsapp.eventos`; no parallel event copy,
Registro Diario, Registro Longitudinal, score or artificial answer is generated.
Events become visible to independent readers only after their transaction commits.

## Interruption command (dormant, transaction owned by caller)

`interrupt(db, message_id, emitter, sender, content, context_wamid=None)` requires
PARAR and a matching v2 authenticated-ingress receipt/fingerprint. It acquires the
operation and emitter/recipient coordination plan before canonical scope locks.
With context.id it requires Mental Health transport evidence and verified sender.
Without context it only uses the dormant resolver as a candidate proposal: unique
Mental Health selects that followup; ambiguity creates only a recipient barrier.
No matches/conflicting identity/legacy-only references fail closed. Brazilian
12/13 equivalence is never inferred from the serialization key.

No followup, conversation, E12C authorization, consent, PTS, session, clinical
context or institutional relationship is mutated. A distinct communication ledger
records INTERROMPIDA, origin WHATSAPP, message reference, time and the requesting
Pessoa derived from the unambiguous followup. Ambiguous barriers have NO Pessoa
assignment and produce NO individualized timeline event. Replay returns the same
event, and receipt/persistence/clinical orchestration must commit together in 3B.3.

## Explicit reactivation

POST `/saude-mental/pessoas/{pessoa}/contextos/{contexto}/whatsapp/comunicacao/reativar`
with `instituicao_id`, `Idempotency-Key` and the existing AuthorizationCreate body
(origem, obtida_em, referencia_evidencia, evidencia_sha256, evidencia_verificada).
Requires canonical ASSISTENCIAL_REGISTRAR, current E12C authorization and new
verified evidence obtained after interruption. It records REATIVADA with operator
and evidence, never silently grants E12C or changes SIM/clinical consent. A repeated
key returns its original event, not a new reactivation; changed content conflicts.
An existing revoked E12C authorization must first be addressed through its canonical
procedure. Clearing the followup interruption leaves preventive barriers intact.

`release_recipient` is an internal, explicit ADMIN-only procedure with new verified
evidence, idempotency and audit. It clears only the EXACT named preventive scope,
not aliases, other scopes or contextual authorization. There is deliberately no
public endpoint for this cross-institution administrative procedure in 3B.2.
No automatic reactivation or fabricated evidence is provided.

## Read contract and future UI (no frontend changes)

GET `/saude-mental/pessoas/{pessoa}/contextos/{contexto}/whatsapp/comunicacao`
and the existing authorized journey expose:

* estado: AUSENTE, WHATSAPP_INTERROMPIDO, SEM_INTERRUPCAO_REGISTRADA;
* acompanhamento_id, interrompido_pela_pessoa, ocorrido_em, bloqueio_preventivo;
* acompanhamento_assistencial_independente;
* eventos chronologically ordered by occurred time then ID.

Each event has COMUNICACAO_WHATSAPP_INTERROMPIDA or COMUNICACAO_WHATSAPP_REATIVADA,
Pessoa/followup/context/institution IDs, timestamp, origin, request/operator authorship
and opaque audit reference. No phone, raw message, evidence document or token is
exposed. SEM_INTERRUPCAO_REGISTRADA does NOT imply E12C authorization or permission
to send: the barrier also checks those independent contracts.

Future TimelineBemEstar presentation should merge this source with existing
check-ins by timestamp, use a communication-specific icon/type, and avoid clinical
score badges. Do not relabel the event as a check-in or include it in clinical
reading, instrument scores, management aggregates or clinical analyses.
Recommended followup/prontuario/cockpit badge: "Comunicação por WhatsApp interrompida
pela Pessoa. O acompanhamento assistencial permanece independente."
Only show "ativo" when the actual clinical state is active. Current communication
state can be fetched without loading timeline/history. Existing contextual read
permission is enforced; GESTOR alone provides no access. No management endpoint
has been extended and no individualized events are added to its payload.

## Outbound barrier and durable text execution

`coordinate` uses operation then sorted emitter/transport keys, revalidating the
set of direct proven Meta bridges before care locks. Variant contention is not
identity. `require_output` checks recipient and followup blocks, destination
relationship and canonical E12C/active followup for Mental Health. Legacy inbound
canonical authorization remains in place; global prevention also covers legacy
and unbound navigation replies. Only the two inventoried sender callers exist.

PREPARADO is committed before execution. Revalidation and EM_EXECUCAO commit form
the authorization boundary, then HTTP occurs with no transaction open. A stop
committed first prevents IO. If execution already started, its result is recorded;
the system cannot cancel already-accepted Meta IO and blocks subsequent sends.

CONFIRMADO requires one unambiguous wamid and atomic receipt timestamp/evidence.
A structured non-transient 4xx rejection may produce FALHA_DEFINITIVA. Timeout,
ambiguous success, 5xx, malformed response or commit failure produce INCERTO when
possible; otherwise durable EM_EXECUCAO survives. Neither state is retried.
PREPARADO after a process interruption is also not resumed automatically.
Commit acknowledgement loss never overwrites an already CONFIRMADO execution.

Callbacks remain independently persisted by exact Phone Number ID + wamid;
text statuses may legitimately have envio_id NULL. Internal `evidence()` reconciles
known executions with those events without converting delivered/read into clinical
consent or rewriting execution state. If wamid was lost before durability, no
association by phone/time is attempted; that outcome remains unresolved.

## Operational limits / next gate

* No global deadlock-freedom claim; all future callers need the canonical lock order.
* Complete candidate-set serialization with creation/prepare remains 3B.3. The
  dormant interruption function is not safe to activate without that integration.
* Original phone uniqueness still prevents some simultaneous Mental Health
  scenarios; do not remove it or activate multilines in this migration.
* Schema must be migrated before this code serves new read/outbound paths. No
  persistent migration/deploy has been executed here.
* Old-code rollback after creating communication blocks is NOT safe: old senders
  ignore the barriers and can retry uncertain text responses. Pause outgoing IO
  with an approved operational procedure and use a barrier-compatible rollback.
* No reconciliation automatically retries, restores, deletes or grants anything.

## Local inventory

Baseline homolog: `df9a315d4c55e898a455721f7e589d7e8a35be81`.

### Modified

* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/models/__init__.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/routers/whatsapp_mental.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/schemas/saude_mental.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/services/saude_mental.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/services/whatsapp_convite_envio.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/services/whatsapp_ingress.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/services/whatsapp_sender_service.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/tests/test_m0_baseline.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/tests/test_whatsapp_convite_persistence.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/tests/test_whatsapp_convite_status.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/tests/test_whatsapp_mental.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/tests/test_whatsapp_postgres.py`

### New

* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/alembic_canonical/versions/e14b3b2_comunicacao.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/models/whatsapp_comunicacao.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/schemas/whatsapp_comunicacao.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/services/whatsapp_comunicacao.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/app/services/whatsapp_resposta.py`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/docs/e14b3b2-comunicacao.md`
* `/Users/Abnel/Desktop/1_PROJETOS/APP/APLICAÇÃO/monitra-backend-homolog-e12/tests/test_whatsapp_comunicacao.py`

The timeline timestamp denotes the durable communication transition recorded
by the server, not a fabricated Meta client timestamp. Clinical dates are unchanged.
When the response wamid is observed before a local persistence failure, best-effort
INCERTO persistence retains it and HTTP 200 for subsequent exact-key callback
inspection. If that persistence also fails, EM_EXECUCAO remains blocking and the
missing correlation cannot be reconstructed by guessing.

## Executed validation

PostgreSQL 18.6, dedicated test resource at 127.0.0.1:55620. Owned disposable
databases were migrated and removed; no persistent application database was used.
Final full suite: 291 PASS. Final communication revalidation: 48 PASS (all overlap
with that matrix). Final Neuro/Cardio PostgreSQL suite: 31 PASS, disjoint.
Total: 322 DISTINCT PASS, 0 FAIL, 0 SKIP; 45 new communication tests over the
277-test baseline. Syntax and git diff --check passed. No commit/push/deploy.

Evidence logs (local, synthetic test data only):
* /private/tmp/e14b3b2-final.log
* /private/tmp/e14b3b2-communication-verified.log
* /private/tmp/e14b3b2-legacy-verified.log

Functional integration of new PARAR via authenticated ingress remains PENDING
3B.3, not a skipped test disguised as success. UI presentation is documented only.
The existing urllib3/LibreSSL environment warning remains; no real Meta IO ran.
