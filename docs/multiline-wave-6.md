# Wave 6 — Care Plan Multi-Line

Baseline: `274e4040760ee462ff87aad199f352df5392fc49`.
Implementation branch: `feature/multiline-wave-6-care-plan`.

## Boundary and identity

`CarePlanService` is the shared write/read boundary for PTS, objectives and
agenda. The existing ORM, tables and HTTP payloads remain in use. No clinical
rules, provider hierarchy, schema migration or frontend changes were added.

Ancestry is PTS.modulo_id → objective → agenda → session. Agenda's direct
pts_id must agree with its objective. Writes reject generated sessions whose
patient differs from the PTS patient. No duplicated module columns were added.

New PTS resolves the existing modulo_id through CareLineResolver. An omitted
line resolves only when exactly one active supported patient line exists.
Ambiguity is HTTP 409; other care-line errors retain their institutional code
in HTTP 400 detail. The service does not introduce a care-plan capability flag.
Historical ID operations use the stored module and registry, not current links;
deactivating a patient link does not silently reclassify a historical plan.

## Reads and legacy NULL

`list_plans` without a line is explicitly the patient-wide legacy list, including
NULL. `list_scoped` resolves a line (or rejects ambiguity) and excludes NULL.
GET /pts/paciente/{id} preserves the legacy list; optional modulo_id selects
the scoped list. No arbitrary active plan is selected by the new boundary.

NULL remains UNASSIGNED. New plans cannot be NULL. Historical reads tolerate it.
Closing an unassigned PTS is safe and allowed without assigning a line;
reopening, objective writes, agenda writes and scheduling require an assigned
supported line and reject otherwise. No backfill or repair is performed.

The preexisting PTSService Report Engine compatibility reader is unchanged.
Its patient-wide active-plan selection remains a deferred Report Engine concern;
it is not the new institutional scoped read API.

## Transactions and active plan invariant

At most one ATIVO PTS per patient and assigned line through the approved write
boundary. Create locks the persisted patient with SELECT FOR UPDATE before
checking conflicts. Reopen and close lock patient first, then refresh/lock PTS.
Create/reopen conflict checks occur after acquiring the patient lock.

The transaction wrapper owns a single commit after the complete write, or
rollback on any failure. Helpers flush but never commit. Dedicated request
sessions should be used; these writes must not be embedded in unrelated pending
writes. PostgreSQL READ COMMITTED was used in concurrency tests. The deployed
isolation configuration must preserve that contract. SQL writers bypassing
this boundary are not protected by a unique index: none was approved or added.

## Authorization and actor

All PTS/objective/agenda/scheduling routes now use get_usuario_atual and the
existing assert_clinica_access helper. Its ADMIN behavior is unchanged;
ADMIN_CLINICA is not global. Existing resource authorization follows persisted
ancestry to patient.clinica_id, not client-supplied patient identity.

PTS.criado_por_usuario_id is the authenticated usuario.id. Assigned planning
professional remains profissionais.id. These namespaces are never equated.

## Catalog and mutation

Create/update validate active activity with module explicitly matching PTS,
active occupation linked through atividade_ocupacao, and active professional
with matching occupation and patient clinic. NULL activity module is not
universal. Updates repeat validation. Historical GET does not require current
catalog activity and can display inactive resources.

Objective text, priority and status retain existing semantics; no reassignment
or text snapshot/versioning was introduced. Changes to text can still affect
current contextual presentation in legacy session/report readers.

Planning changes never update generated sessions. Changes to professional,
dates, duration, frequency and quantity remain changes to planning only.
Professional replacement is rejected if an existing session has no professional
of its own, because legacy readers would otherwise reinterpret its author via
the agenda fallback. No session regeneration or cancellation is implicit.

Deletion of agenda with any generated session is HTTP 409, before ORM cascade.
Agenda mutation/deletion and scheduling confirmation use the same agenda row
lock. Confirmation keeps this lock through SchedulingService's existing commit,
preventing confirmation/deletion races. PTS close never changes child history.
The legacy frequency response now supplies db to montar_response_agenda.

## Scheduling and compatibility

Scheduling algorithms, session generation, request/response formats and existing
SchedulingService commit remain unchanged. Routes first authorize and validate
ancestry/catalog through the Care Plan boundary. Request session closure releases
locks for read-only suggestions and pre-write validation failures.

Neuro/Cardio modulo_id payloads, paths, statuses, list response fields,
cronograma_confirmado and sessoes_geradas remain compatible. Security/integrity
rejections explicitly authorized by the frozen contract are intentional.
No frontend, clinical engine, Timeline, Cockpit or Report implementation changed.

## Validation actually executed

All Docker mounts of the source were read-only. Application databases were not
used for tests. A disposable PostgreSQL 16 container with no published ports or
external network hosted UUID-named synthetic schemas, removed after each test.

Compilation (Python 3.9, exit 0):

```sh
docker run --rm --network none -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONPYCACHEPREFIX=/tmp/wave6-cache docker-api python -m compileall -q app/services/care_plan_service.py app/routers/pts.py app/routers/agenda_cuidados.py app/routers/scheduling.py tests/test_care_plan.py tests/test_care_plan_postgres.py
```

Focused run: `python -m unittest discover -s tests -p test_care_plan.py -v`
in docker-api: 21 tests passed at that stage. Two additional cases (future line /
inactive application definition and inactive linkage/catalog) passed in the final
suite, giving 23 isolated Care Plan tests in the final tree.

PostgreSQL focused run: `python -m unittest discover -s tests -p test_care_plan_postgres.py -v`
in docker-api sharing the disposable PostgreSQL network namespace: 5 passed.
Cases cover concurrent create, concurrent reopen, create versus reopen, observed
PostgreSQL lock waiting, and agenda deletion versus scheduling confirmation.

Final command:

```sh
docker run --rm --network container:integra-wave6-test-pg -v /private/tmp/integra-wave1:/work:ro -w /work -e PYTHONDONTWRITEBYTECODE=1 -e CARE_PLAN_TEST_POSTGRES_URL=postgresql://postgres@127.0.0.1/postgres docker-api python -m unittest discover -s tests
```

Result: 187 discovered; 184 passed; 3 skipped. The skips are preexisting Wave 5
migration tests requiring WAVE5_TEST_POSTGRES_URL. All 28 new Wave 6 tests ran.
Existing Neuro, Timeline, clinical reading, daily record and intervention tests
passed. Report PTS compatibility and scheduling HTTP contracts are covered.
The available suite is not a full deployed UI or PDF rendering acceptance test.

The first isolated test attempt could not import TestClient because httpx is not
installed in docker-api. Tests were adapted to the existing direct ASGI harness
pattern; no dependency was added. Subsequent targeted and full runs passed.

`git diff --check` passed. No application restart, application migration or deploy.

## Deferred limitations

- No protection against external SQL writers that ignore the patient lock.
- Legacy Report Engine patient-wide selection remains unchanged by scope.
- Session execution/attendance transaction debt and broader session-route ACL
  remain outside this Care Plan wave.
- Frontend catalog filtering remains unchanged; invalid selections are rejected
  by the backend.
- Historical objective text is not snapshotted.
- CARDIO-DR-OBS-001 and Responsible Cardio convergence are unchanged.
- Local application DB remains separate from the synthetic test schema; this
  mission does not apply the previously approved Wave 5 migration there.
