# P0-S1 biometric enrollment quarantine implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans`
> task-by-task. Steps use checkbox syntax for tracking.

**Status:** Complete

**Goal:** Prevent every public HTTP or conversational visual request from
creating or attaching a biometric face profile until P0.5 supplies explicit
local administration, consent, and authorization policy.

**Architecture:** Keep the image contract, scene-description path, SQLite face
schema, and stored profiles intact. Both public enrollment paths return one
fixed unavailable outcome before any enrollment service is called. A name,
face, phrase, or `VISION_ENABLED` must not authorize enrollment.

**Tech stack:** Python 3.12, FastAPI, pytest, existing vision module.

## Global constraints

- Work from a new feature branch, never directly on `main`.
- Preserve the WAV and public audio response contracts.
- Do not delete face profiles, entities, facts, or migrations.
- Do not add login, roles, consent storage, a public admin API, dependencies,
  cloud calls, controller/tool code, or P0.5 authorization.
- `VISION_ENABLED` remains availability only, not authorization.

## Required reading

1. `AGENTS.md`.
2. `docs/architecture/README.md` and `identity-and-access.md`.
3. `docs/plans/p0-s-hardening-design.md`.
4. `server/src/server/routers/vision.py` and `vision/perception.py`.
5. `tests/integration/test_vision_endpoint.py` and
   `tests/integration/test_vision_dialog.py`.

## Permitted file scope

| File | Permitted change |
|---|---|
| `server/src/server/routers/vision.py` | Quarantine the two public enrollment paths only. |
| `tests/integration/test_vision_endpoint.py` | Replace HTTP enrollment-success assumptions with quarantine coverage. |
| `tests/integration/test_vision_enroll_service.py` | Align existing endpoint integration coverage with the quarantine boundary. |
| `tests/integration/test_vision_dialog.py` | Replace conversational enrollment routing coverage with quarantine coverage. |
| `docs/architecture/p0-s-hardening-audit.md` | Record P0-S1 disposition after verification. |
| `docs/architecture/current-state.md` | Update only the enrollment status after merge. |
| This plan | Record observed RED/GREEN and final gates. |

Changing `vision/faces.py`, `vision/perception.py`, schemas, settings,
`.env.example`, or character prompts is out of scope unless a test proves the
router-only quarantine cannot prevent both calls. Stop instead of expanding.

## Interface decision

Define this private constant in `routers/vision.py`:

```python
_BIOMETRIC_ENROLLMENT_UNAVAILABLE = (
    "Face enrollment is temporarily unavailable pending local administration and consent policy."
)
```

`POST /vision/enroll` returns HTTP 503 with that detail without reading the
upload or invoking `vision.enroll_person`. A `/vision/respond` request whose
text matches `vision.wants_enroll(text)` keeps its existing 200 response
envelope but passes the same fixed text as perception guidance; it does not
call `vision.enroll_from_frame` or `perceive_scene` for that request.

## Tasks

### Task 1: Quarantine direct HTTP enrollment

**Files:** `tests/integration/test_vision_endpoint.py`,
`server/src/server/routers/vision.py:96-135`.

- [x] **Step 1: Write the failing no-write test.**

```python
@pytest.mark.integration
def test_enroll_is_quarantined_without_calling_enrollment(
    client: TestClient, vision_on: None
) -> None:
    with patch("server.routers.vision.vision.enroll_person", new_callable=AsyncMock) as enroll:
        response = _post_enroll(client, _FAKE_JPEG)

    assert response.status_code == 503
    assert response.json()["detail"] == _BIOMETRIC_ENROLLMENT_UNAVAILABLE
    enroll.assert_not_awaited()
```

- [x] **Step 2: Observe RED.**

```powershell
uv run pytest tests/integration/test_vision_endpoint.py::test_enroll_is_quarantined_without_calling_enrollment -v
```

Expected: FAIL because the endpoint currently invokes `vision.enroll_person()`.

- [x] **Step 3: Implement the minimal router guard.**

After the existing `VISION_ENABLED=false` response, return HTTP 503 with the
fixed detail before reading the image or calling the enrollment service.

- [x] **Step 4: Observe GREEN plus endpoint regression.**

```powershell
uv run pytest tests/integration/test_vision_endpoint.py -v
```

Expected: PASS; image validation remains covered and `/vision/enroll` performs
no biometric write.

### Task 2: Quarantine conversational visual enrollment

**Files:** `tests/integration/test_vision_dialog.py`,
`server/src/server/routers/vision.py:158-182`.

- [x] **Step 1: Write the failing quarantine test.**

```python
@pytest.mark.integration
def test_vision_respond_quarantines_enrollment_phrase(client: TestClient) -> None:
    response = _post_respond(client, _FAKE_JPEG, "aprende mi cara, soy Felipe")

    assert response.status_code == 200
    vision.enroll_from_frame.assert_not_awaited()
    vision_module.perceive_scene.assert_not_awaited()
    assert (
        llm.generate_response.await_args.kwargs["perception"] == _BIOMETRIC_ENROLLMENT_UNAVAILABLE
    )
```

- [x] **Step 2: Observe RED.**

```powershell
uv run pytest tests/integration/test_vision_dialog.py::test_vision_respond_quarantines_enrollment_phrase -v
```

Expected: FAIL because the router currently awaits `vision.enroll_from_frame()`.

- [x] **Step 3: Replace only the enrollment branch.**

```python
if vision.wants_enroll(text) is not None:
    perception = _BIOMETRIC_ENROLLMENT_UNAVAILABLE
else:
    perception = await perceive_scene(image_bytes)
```

Keep the existing exception degradation and `process_text_turn()` response path
for non-enrollment scene questions.

- [x] **Step 4: Observe visual-dialog GREEN.**

```powershell
uv run pytest tests/integration/test_vision_dialog.py -v
```

Expected: PASS; ordinary scene dialogue remains available and an enrollment
phrase cannot create a profile.

### Task 3: Record the boundary and verify the repository

**Files:** `docs/architecture/p0-s-hardening-audit.md`,
`docs/architecture/current-state.md`, this plan.

- [x] **Step 1: Record the verified disposition.**

State that both public paths are quarantined, existing data was preserved, and
P0.5 remains responsible for future enrollment policy.

- [x] **Step 2: Run final gates.**

```powershell
just lint
just typecheck
just test
just audit
git diff --check
```

Expected: every command exits zero. Record exact test count and duration.

- [ ] **Step 3: Commit after scope review.**

Stage only the permitted implementation, tests, and documentation files, then
use the Conventional Commit message:
`fix(vision): quarantine public biometric enrollment`.

## Acceptance criteria

- No public `POST /vision/enroll` request invokes `vision.enroll_person()`.
- No public `/vision/respond` enrollment phrase invokes
  `vision.enroll_from_frame()`.
- Ordinary `/vision/respond` scene description remains available when vision is
  enabled.
- The denial does not echo an attacker-supplied name or claim a profile exists.
- Existing SQLite biometric data remains untouched.
- All listed quality gates pass.

## Rollback

Revert the quarantine commit only if it breaks the non-enrollment vision
contract. Do not restore either public enrollment path as a workaround; open a
follow-up decision instead.

## Completion record

- RED observed: the direct-path test received HTTP 200 and the conversational
  test observed one `enroll_from_frame()` await before the router guard existed.
- GREEN: the two new no-write tests passed; the vision endpoint/dialog/service
  regression set passed `25/25`.
- A first full suite run exposed three legacy success/rejection expectations in
  `test_vision_enroll_service.py`; they were converted into additional
  quarantine checks without changing face services or stored data.
- Final verification: `just lint`, `just typecheck`, `just test`, and
  `just audit` exited zero. The final `just test` reported `496 passed in
  30.76s`.
- Remaining boundary: this does not provide enrollment. P0.5 must define local
  administration, consent, authorization, and audit before a new write path.

## Operational handoff prompt

```text
MODO:
IMPLEMENT

OBJETIVO:
Implementar docs/plans/0002b-biometric-enrollment-quarantine.md exactamente.
Revalidar main y auditar ambos caminos públicos de enrolamiento facial antes de
editar. Ejecutar exclusivamente P0-S1; no comenzar P0-S2, P0.3 ni P0.5.

RESTRICCIONES:
- No trabajar directamente sobre main.
- No agregar dependencias, login, roles, consentimiento persistente ni API admin.
- No alterar contrato de audio ni borrar datos legacy.
- Probar RED/GREEN para HTTP y enrolamiento conversacional.
- Ejecutar los quality gates del plan y no afirmar éxito sin comandos completos.
```
