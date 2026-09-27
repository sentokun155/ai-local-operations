# GWI-0010-T010 Task Request

Task Key: `GWI-0010-T010`
Task Name: `Unity Host Discovery Diagnostics V0`
Stage: `implementation / connectivity diagnosis`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

T009のHost probeで `unity status` が2回とも `success=true / instanceCount=0` だったため、
「Editor自体が現在いない」「EditorはいるがPipelineがreadyでない」「Host processからだけdiscoveryできない」
をread-onlyで切り分ける。

新しい汎用runnerやUnity execution APIは作らない。
既存 `probe_unity_host_connectivity()` を最小限拡張する。

## Known evidence

T008 direct/native:
- Unity CLI `1.0.0-beta.9`
- `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`
- project `C:\Users\sennn\2D_RPG_Project6_git`
- Editor `6000.3.9f1`
- state `ready`
- direct/native Windows user `DESKTOP-U5FJ9NG\sennn`

PROBE-009 app-server Worker:
- same CLI path/version
- Worker user `DESKTOP-U5FJ9NG\CodexSandboxOffline`
- `unity status` => zero instances

T009 Host live probe:
- Host user `DESKTOP-U5FJ9NG\sennn`
- same CLI path/version
- `unity status` exit 0 / success=true / zero instances
- repeated once with same result

Unity official skill/docs note:
- `status` attaches to already-running GUI Editor with Pipeline.
- `pipeline list` is the diagnostic command for Pipeline availability / Safe Mode.
- sandboxed agents can hide a running Editor, but Host probe is currently observed under `sennn`, not `CodexSandboxOffline`.

## Change

Extend existing `probe_unity_host_connectivity()` only.

### A. Bounded Editor process presence

Add one read-only Windows process observation sufficient to answer:
- is at least one `Unity.exe` Editor process currently present?
- if safely obtainable, return PID(s), capped to a small bounded count.

Do not return command lines, arguments, environment, tokens, or unrelated processes.

Use a bounded platform-native mechanism. Do not add a generic process-listing tool.

### B. Pipeline diagnostic

When Unity CLI is available, run read-only:

`unity pipeline list --format json --no-banner --non-interactive`

Parse only bounded fields needed to distinguish:
- no Editor / no Pipeline candidate
- Editor visible but Pipeline absent/not ready
- Pipeline candidate/connection visible
- Safe Mode / compile-related state if structured output exposes it

Do not return raw stdout/stderr.
Unknown or credential-like fields must be ignored.

### C. Existing status probe

Keep:
`unity status --format json --no-banner --non-interactive`

Do not change T008 identity match semantics.

### D. Diagnostic classification

Return an additional bounded field such as `diagnosis` with one of:

- `EDITOR_PROCESS_ABSENT`
- `EDITOR_PRESENT_PIPELINE_NOT_VISIBLE`
- `PIPELINE_VISIBLE_STATUS_EMPTY`
- `DIRECT_MATCH`
- `SAFE_MODE_OR_PIPELINE_UNAVAILABLE`
- `DIAGNOSTIC_UNRESOLVED`

Names may be adjusted for implementation clarity, but keep the classes distinct.

Do not claim sandbox causality unless directly supported.

## Tests

Add focused mocked tests for:
- no Unity process + status empty
- Unity process present + status empty
- pipeline list identifies candidate while status empty
- direct match remains PASS
- credential-like/raw fields not returned
- process command lines never returned
- timeout/failure stays bounded

Run available focused/non-live tests.

## Boundary

Do not:
- start/stop/restart Unity
- run Unity command/list/eval/test
- install/update Pipeline
- change Unity project/packages/assets
- configure Unity MCP
- run `unity mcp`
- inspect process command lines
- dump environment
- change Production
- add generic shell/process execution
- directly call real Host probe from Worker

## Persistence

Codex Worker implements source/tests/result only.
Local Operations finalize owns commit/push.

## Result

Create:
`work/gwi-0010/GWI-0010-T010_RESULT.md`

Final:
`GWI-0010-T010 <PASS|HOLD> — Host discovery diagnostics ready; <summary>`

After finalize + Dev runtime refresh, Controller Chat will call the existing Host probe once.
