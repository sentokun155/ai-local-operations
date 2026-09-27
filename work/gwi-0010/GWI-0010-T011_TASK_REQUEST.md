# GWI-0010-T011 Task Request

Task Key: `GWI-0010-T011`
Task Name: `Unity Host Pipeline Handshake Verification`
Stage: `implementation / connectivity verification`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

Local Operations Host から対象Unity Editor / Pipelineへ実際に到達できるかを、
`unity status` のlockfile結果だけに依存せず、固定projectへのread-only Pipeline handshakeで確認する。

同時に、T010の `unity pipeline list --format json` parserをUnity公式documented JSON shapeへ合わせて修正する。

このTaskはConnectivity確認のみ。
Unity capability catalogの内容評価、Unity test、project mutationは行わない。

## Known evidence

T008 direct/native:
- Unity CLI `1.0.0-beta.9`
- project `C:\Users\sennn\2D_RPG_Project6_git`
- Editor `6000.3.9f1`
- `unity status` => ready

PROBE-009 app-server Worker:
- same CLI path/version
- sandbox user `DESKTOP-U5FJ9NG\CodexSandboxOffline`
- `unity status` => zero instances

T010 Host live probe:
- Host user `DESKTOP-U5FJ9NG\sennn`
- Unity.exe process present, PID 5352
- `unity pipeline list` command succeeded and candidateCount=1
- `unity status` => success=true, instanceCount=0
- diagnosis = `PIPELINE_VISIBLE_STATUS_EMPTY`

Official Unity docs:
- `unity status` reads Pipeline lockfiles/heartbeat and is a fast readiness surface.
- `unity list --project-path <project>` queries the connected Editor through Pipeline and is introspection-only.
- `unity pipeline list --format json` reports Safe Mode via:
  - `data.summary.instancesInSafeMode`
  - `data.instances[].safeMode.detected`
- sandboxed agents can get false negative Editor discovery; do not infer Editor absence from status alone.

## Change existing tool only

Extend existing:
`probe_unity_host_connectivity()`

Do not create a generic runner or separate arbitrary Unity command tool.

### A. Fix Pipeline JSON parsing

Parse the documented structured paths from `unity pipeline list --format json`.

At minimum:

- `data.summary.instancesInSafeMode`
- `data.instances[]`
- each instance:
  - project/projectPath if present
  - pid if present
  - safeMode.detected if present
  - Pipeline/package readiness/status fields that are documented or observed in tests
- summary/candidate count

Keep all returned fields allowlisted.
Do not return raw payload.

If the actual installed CLI shape differs from docs, parser may support both documented and existing bounded shapes, but must not infer unknown fields.

### B. Add direct read-only Pipeline handshake

Run:

`unity list --project-path C:\Users\sennn\2D_RPG_Project6_git --format json --no-banner --non-interactive`

Purpose:
- establish whether Host can directly query the target Editor's Pipeline server.

Do not return the tool catalog itself.
Parse only:

- command exit code
- envelope success if present
- whether a valid tool/catalog collection was returned
- bounded tool count
- target project identity if returned
- structured error code(s), sanitized/bounded

Do not expose:
- tool descriptions
- schemas
- arbitrary command names unless needed to validate envelope shape
- raw stdout/stderr
- tokens/credentials

### C. Connectivity verdict

Add a bounded field such as `pipelineHandshake`:

- `CONNECTED`
- `NOT_CONNECTED`
- `SAFE_MODE`
- `UNRESOLVED`

and refine diagnosis.

Expected logic:

1. If `unity list --project-path ...` succeeds with a valid catalog:
   - Host→Pipeline→Editor connectivity is established.
   - overall connectivity disposition may be `HOST_PIPELINE_CONNECTED` even if `unity status` is empty.
2. If list fails and Pipeline diagnostic says Safe Mode:
   - classify `SAFE_MODE_OR_PIPELINE_UNAVAILABLE`.
3. If Unity.exe exists and pipeline list sees target but list handshake fails:
   - classify `PIPELINE_VISIBLE_HANDSHAKE_FAILED`.
4. Do not claim sandbox causality unless directly supported.

### D. Preserve existing status behavior

Keep `unity status` observation and T008 ready identity check.
Do not remove previous diagnostics.

## Tests

Add/update mocked tests for:

- documented Safe Mode JSON:
  `data.summary.instancesInSafeMode > 0`
- per-instance `safeMode.detected=true`
- list handshake success with catalog but status empty
- list handshake failure with safe mode
- list handshake failure with Editor process + pipeline candidate
- no raw catalog/schema/tool descriptions returned
- secret-like fields are stripped
- timeout/failure bounded
- previous DIRECT_MATCH behavior remains

Run whatever Worker-side tests are available.
If Python remains unavailable, record them as NOT RUN and rely on Controller Host live probe after finalize. Do not attempt to repair Python environment in this Task.

## Boundary

Do not:
- execute any Unity tool from the catalog
- run `unity command`, eval, test, build
- modify Unity project/assets/packages
- install/upgrade Pipeline
- configure/start Unity MCP
- start/stop/restart Editor
- change auth/license
- inspect command line/accessToken
- add generic shell/process runner
- modify Production

## Persistence

Worker implements source/tests/result.
Local Operations finalize owns commit/push.

## Result

Create:
`work/gwi-0010/GWI-0010-T011_RESULT.md`

Final:
`GWI-0010-T011 <PASS|HOLD> — Host Pipeline handshake probe ready; <summary>`

After finalize + Dev runtime refresh, Controller Chat calls existing
`probe_unity_host_connectivity()` once.

The Controller then decides:
- `HOST_BRIDGE` if direct Pipeline handshake succeeds.
- remain HOLD if handshake fails or is unresolved.
