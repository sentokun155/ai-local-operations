# GWI-0010-T006 Task Request

Task Key: `GWI-0010-T006`
Task Name: `Codex-native Unity Plugin Capability Audit`
Stage: `investigation / design input`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

Codex Desktop / native Codex surfaceでのみ観測できるUnity Pluginについて、その公開tool surface・package/manifest・実際のUnity接続方式を調査し、Local Operations MCPでどこまで同等Capabilityを再現できるか判断可能にする。

このTaskは **Local Operations → codex app-server Worker経路では実行しない**。
Unity Pluginが実際に見えているCodex-native / Desktop側で実行する。

T005のUnity観測はapp-server Worker経路のCapability evidenceとして保持するが、Unity Pluginの存在・能力・利用可否についての結論には使わない。

## Questions

1. Unity Pluginの正確なplugin名 / ID / version / originは何か。
2. Codexのどのsurfaceで利用可能か。
3. Pluginが公開するTool一覧・description・input schema・output schemaは何か。
4. Skill / plugin.json / mcp.json / manifest / local package root等のmetadataを取得可能か。
5. Unity Editorとの通信方式は何か。
   - local MCP server
   - Editor extension
   - CLI
   - IPC / socket / HTTP
   - other
6. Editor起動済み前提か。
7. project選択・Editor version照合はどう行うか。
8. EditMode / PlayMode testを実行できるか。
9. test result / console / Editor.log / compilation stateを取得できるか。
10. timeout / cancel / busy Editor / compile failure / package import等をどう扱うか。
11. Local Operations MCPで同等tool boundaryを再現できるか。
12. 既存Pluginをそのまま使う方がよいCapabilityと、Local Operations側へ再実装すべきCapabilityは何か。

## Investigation order

### 1. Tool catalog observation

Unity Pluginが公開するtool familyを列挙する。

各toolについて最低限:
- exact tool name
- description
- arguments / schema
- return structure
- read-only / mutation / long-running classification

Tool名だけで内部実装を推測しない。

### 2. Plugin package / metadata

Codexから安全に確認可能なら:
- plugin ID
- marketplace / local origin
- plugin package root
- `plugin.json`
- `mcp.json`
- Skills
- hooks / scripts
- referenced MCP endpoint / executable

private DB manipulationやUI automationで無理に取得しない。

### 3. Read-only / low-effect probes

可能なら低副作用Toolから実測する。

候補:
- current Unity connection / status
- Editor version
- current project path / project identity
- compile state
- console read
- test list / discovery

project変更、asset編集、package変更、scene保存などは行わない。

### 4. Test capability probe

Pluginにtest実行Capabilityがあり、現在接続中Unity projectで安全な既存testを実行できる場合のみ、最小のread-mostly test probeを行ってよい。

ただし:
- 新しいtestを追加しない
- sourceを変更しない
- packageを変更しない
- project upgradeしない
- license/login操作しない
- failing stateをcleanupしない

安全に実行できる既存testが無い場合はschema / behavior observationまででよい。

## Surface separation

成果物では必ず以下を分ける。

| Surface | Meaning |
|---|---|
| Local Operations app-server Worker | T005で監査した現在のWorker route |
| Codex-native / Desktop | 本TaskでUnity Pluginを観測するsurface |
| Local Operations Host | 将来MCP/host runnerを実装する場合のexecutor |
| ChatGPT Controller | 次action判断・host tool開始主体 |

`Codexで使える` をsurface未指定で記述しない。

## Comparison output

Create:

`work/gwi-0010/design/t006/GWI-0010-T006_UNITY_PLUGIN_CAPABILITY_MATRIX.md`

最低限:

| Capability | Codex-native Unity Plugin | app-server Worker | Local Operations MCP reproducibility | Recommended route |
|---|---|---|---|---|

Create:

`work/gwi-0010/design/t006/GWI-0010-T006_UNITY_PLUGIN_REPLICATION_DESIGN.md`

含める:
- plugin architecture observed / inferred / unknownの区別
- MCPで再現する場合のcandidate tools
- reuse existing Plugin vs Local Operations adapter vs hybrid比較
- EditMode / PlayMode routing
- result / log / compile state retrieval
- Editor/process lifecycle
- package / license / concurrency considerations
- bounded implementation recommendation

Create final:

`work/gwi-0010/GWI-0010-T006_RESULT.md`

Result vocabulary:
- `PASS / UNITY_ROUTE_DECISION_READY`
- `HOLD / PLUGIN_SURFACE_INSUFFICIENT`
- `HOLD / UNITY_CONNECTION_UNAVAILABLE`

## Important boundaries

Do not:
- use Local Operations `dispatch_codex_task` to execute this Task
- modify Local Operations production runtime
- modify Worker Pool state
- change Unity project source/assets/packages
- commit/push from Codex
- use Computer Use / ChatGPT Web UI automation
- reverse engineer private binary internals
- bypass plugin permissions or hidden/private storage

Allowed repository mutation:
- Task-owned Result/design documents in `sentokun155/ai-local-operations` worktree only

Git persistence after completion remains Controller / Local Operations responsibility if this native surface can leave the repository worktree changes visible to the existing finalize route; otherwise report the exact persistence limitation instead of inventing a workaround.

## Relation to T004/T005

- T004 remains HOLD until its full supported-environment verification and route/tool-filtering decision are completed.
- T005 is PASS only for routing-decision readiness on the app-server Worker side.
- T006 prevents Unity routing from being finalized based only on the wrong execution surface.
- Host Validation V0 / Python-uv implementation remains a separate likely follow-up after this Unity Plugin audit.
