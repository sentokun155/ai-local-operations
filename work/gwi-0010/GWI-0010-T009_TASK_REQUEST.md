# GWI-0010-T009 Task Request

Task Key: `GWI-0010-T009`
Task Name: `Local Operations Host Unity Connectivity Probe V0`
Stage: `implementation / connectivity verification`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

Local Operations Host process自身から、現在起動中のUnity Editor / Pipeline instanceへread-onlyで到達できるかを確認できる、用途限定のHost probeを追加する。

目的はUnity機能実装ではなく、T008 / PROBE-009で未解決だった **HOST_BRIDGE connectivity** を実測すること。

汎用shell runner、Unity command executor、test runnerは作らない。

## Known baseline

T008 direct/native surface:

- Unity CLI path: `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`
- Unity CLI version: `1.0.0-beta.9`
- Project: `C:\Users\sennn\2D_RPG_Project6_git`
- Editor: `6000.3.9f1`
- state: `ready`
- observed Pipeline port: `7800` at that time

PROBE-009 app-server Worker:

- same Unity CLI path/version
- Windows identity: `DESKTOP-U5FJ9NG\CodexSandboxOffline`
- `unity status --format json --no-banner --non-interactive`
- exit 6 / success=false / count=0

Therefore Worker route is not currently proven to reach the Editor.

## Tool

Add exactly one bounded MCP tool:

`probe_unity_host_connectivity()`

No input parameters.

### Behavior

Run from the Local Operations Host process environment.

1. Record safe Host identity facts:
   - Windows account name
   - USERPROFILE
   - LOCALAPPDATA
   - APPDATA
2. Resolve Unity CLI:
   - prefer `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe` only if it exists
   - otherwise PATH lookup
   - do not search entire disks
3. Run:
   - `unity --version`
   - `unity status --format json --no-banner --non-interactive`
4. Parse and return only bounded fields:
   - status
   - hostUser
   - userProfile
   - localAppData
   - appData
   - unityCliPath
   - unityCliVersion
   - unityStatusExitCode
   - success
   - instanceCount
   - for each returned instance only:
     - state
     - projectPath
     - editorVersion
     - pid
     - pipelinePort if present
5. Do not return raw command line, raw environment, credentials, accessToken, token-like values, or full raw JSON.
6. If status output contains unknown credential-like fields, ignore them.
7. Timeout should be short and bounded. On timeout return HOLD; do not kill unrelated processes.

### Verdict helper

The tool may additionally return:

- `DIRECT_MATCH` if a ready instance matches T008 project path + Editor version.
- `NO_INSTANCE`
- `CLI_UNAVAILABLE`
- `STATUS_FAILED`
- `IDENTITY_MISMATCH`

PID/port are observational and may change. Match primarily on project path + Editor version + ready state.

## Supported MCP route observation

Without writing configuration, also inspect the installed Unity CLI help/documentation enough to report:

- whether a `unity mcp` command exists
- whether it exposes a stdio server mode or configure command
- exact documented command names only

Do not run any configuration-changing command.

This information belongs in Result documentation, not necessarily in the tool response.

## Tests

Add focused tests using subprocess mocks/fixtures:

- direct ready instance parsing
- zero instances
- CLI unavailable
- nonzero status
- credential-like extra fields are not returned
- only bounded environment fields returned
- T008 project/version match logic

Run focused tests and any existing suite that is available in the Worker environment.
Do not broaden scope to solve T004 Python environment gap in this Task.

## Boundaries

This Codex Task must not:

- invoke the new Host tool against the real machine
- run Unity status from the Worker as evidence for Host connectivity
- modify Unity project/assets/packages
- configure Unity MCP
- run Unity tests
- modify Dev/Prod runtime
- restart tunnels
- perform Worker recovery
- add arbitrary command execution
- commit/push directly

Codex implements source/tests/docs only. Local Operations finalize performs Git persistence.

## Practical verification after implementation

After Controller finalizes this Task and the Human refreshes the Dev Plugin catalog:

1. Controller Chat calls `probe_unity_host_connectivity()`.
2. Compare Host result with T008 direct baseline and PROBE-009 Worker result.
3. Select:
   - `HOST_BRIDGE` if Host sees the same ready project/editor.
   - otherwise keep HOLD and investigate supported Unity stdio MCP route.

## Result

Create:
`work/gwi-0010/GWI-0010-T009_RESULT.md`

Final agent message:
`GWI-0010-T009 <PASS|HOLD> — host connectivity probe implementation ready; <summary>`
