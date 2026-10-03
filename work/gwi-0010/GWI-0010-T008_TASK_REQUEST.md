# GWI-0010-T008 Task Request

Task Key: `GWI-0010-T008`
Task Name: `Unity Connectivity Path Investigation`
Stage: `investigation / connectivity preflight`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

Unity Plugin / Unity CLIのCapabilityを広く調べる前に、**現在のLocal Operations経路から、Humanが既にNative Codexで接続確認したUnity Editor / Pipelineへ接続できる経路を特定する。**

このTaskの主題は「何ができるか」ではなく「どう接続するか」である。

## Human-confirmed baseline

過去の手動確認で、次は成立済みとして扱う。

- Unity Editorを起動した状態でNative Codexへ手動依頼すると、Unity側へ接続できることをHumanが確認済み。
- Codex-native環境にはUnity Plugin package / Unity CLIが存在する。
- T006ではEditor未起動状態だったため `unity status` が `STATUS_NO_INSTANCES` となった。
- T006のHOLDは「Unity Plugin方式が不可能」という意味ではない。

このHuman-confirmed baselineを再証明するためだけの大規模再調査はしない。

必要なexact Evidenceが後からRepositoryへ追加された場合は、それを補助Evidenceとして利用してよい。

## Primary question

次の各surfaceから、同じ起動済みUnity Editor / Pipelineへ到達できるか。

1. **Codex-native / Desktop**
   - 既にHuman-confirmed baselineあり。
   - 比較基準。

2. **Local Operations → Codex app-server Worker**
   - 現在のWorker Pool / dispatch経路。
   - Worker内からUnity CLI / Plugin / MCP endpointへ到達できるか。

3. **Local Operations Host**
   - MCP server process / host-side Pythonから、Unity CLIまたはUnity MCP/Pipelineへ直接接続できるか。
   - 将来Controller-facing bounded Toolを作る場合の候補経路。

Capability discoveryやtest executionはConnectivityが成立してからの後続Taskとする。

## 0. Connectivity gate

調査開始時に、対象Unity Editorが接続可能状態か確認する。

最低限:

- Unity Editor instanceが存在するか
- intended projectを一意に識別できるか
- Unity CLI / Pipelineからinstanceが見えるか
- Editor / project identityが期待対象か

もし対象Editorが起動していない、Pipelineがreadyでない等で接続条件が成立しない場合:

- `HOLD / UNITY_INSTANCE_UNAVAILABLE`
- 不足している条件だけを報告
- Capability調査へ進まない
- install / package change / Editor起動を勝手に行わない

## 1. Native baseline locator

Native Codex側で既に接続できる事実について、利用可能なら最小限のlocatorを記録する。

候補:

- Unity Plugin identity
- Unity CLI version
- connected project identity
- `unity status --format json` の成功状態
- 既存Human-confirmed Evidence locator

過去EvidenceがまだRepositoryに無ければ、Human-confirmed baselineとして明記し、存在しないEvidenceを作ったことにしない。

## 2. App-server Worker connectivity

Local Operationsから起動したCodex app-server Taskのsurfaceで、**read-only connectivity probeだけ**を行う。

確認:

- Unity CLI executableが見えるか
- Native Codexと同じUnity CLI binary / versionか
- `unity status --format json --no-banner --non-interactive` 相当のread-only status取得が成立するか
- connected instance count
- project identity / Editor versionを取得できるか
- Nativeで見えるinstanceと同じinstanceへ到達しているか
- environment / user profile / HOME / LOCALAPPDATA / APPDATA / PATH差が接続発見に影響していないか
- sandbox / process boundaryによりlocal IPC / socket / named pipe / localhost endpoint等が見えない可能性があるか

接続に失敗した場合は、失敗点を
- executable discovery
- process launch
- user/profile discovery
- transport
- Editor/Pipeline discovery
- permission/sandbox
に分類する。

Unity command / test / eval / project mutationは行わない。

## 3. Local Operations Host connectivity

Local Operations MCP host processから、同じUnity connection routeへ到達可能かを調査する。

優先順位:

1. 既存Unity CLIをbounded subprocessとして呼ぶ
2. Unity Pluginが利用するdocumented local endpoint / supported MCP route
3. Unity CLIが提供するsupported MCP configuration / server route

private DB、binary reverse engineering、UI automation、undocumented credential extractionは使わない。

確認:

- Local Operations hostからUnity CLIを起動できるか
- host-side environmentで同じinstanceをdiscoverできるか
- Worker surfaceとの違い
- Unity CLIがどのlocal state / user profile / endpointからinstanceを発見しているか（公開情報・observable behaviorの範囲）
- Local Operationsから直接MCP接続可能なsupported endpointがあるか
- supported MCP routeがある場合、必要なconfigurationとruntime ownershipは何か

このTaskでは設定を書き換えない。
`unity mcp configure ...` 等のwrite operationは実行しない。

## 4. Transport model

接続方式をEvidenceに基づいて整理する。

最低限候補:

- CLI → running Editor / com.unity.pipeline
- local IPC / named pipe / socket
- localhost HTTP/WebSocket
- MCP server
- other supported local transport

推測だけで断定しない。

各surfaceごとに:

| Surface | Client process | Discovery source | Transport | Connected? | Blocking difference |
|---|---|---|---|---|---|

を作る。

## 5. Connection equivalence

Native Codexで成立する接続と、app-server Worker / Local Operations Hostの接続が同一条件か確認する。

特に:

- same Windows user
- same environment/profile directories
- same Unity CLI executable
- same project
- same Editor PID/version
- same Pipeline instance
- same local transport visibility

接続成功だけでCapability equivalenceまでは主張しない。

## 6. Decision outputs

Create:

`work/gwi-0010/design/t008/GWI-0010-T008_UNITY_CONNECTIVITY_MATRIX.md`

Create:

`work/gwi-0010/design/t008/GWI-0010-T008_CONNECTIVITY_ROUTE_DECISION.md`

Decisionは次のいずれかを選ぶ。

### A. APP_SERVER_DIRECT

app-server Workerから既存Unity CLI / Pipelineへ直接接続可能。

次TaskでCapability / test probeをapp-server経路から行える。

### B. HOST_BRIDGE

Workerからは不可/不安定だが、Local Operations Hostから接続可能。

次TaskではController-facing bounded Unity connectivity / validation ToolをLocal Operationsへ実装する。

### C. SUPPORTED_MCP_ROUTE

Unityのsupported MCP endpoint/configurationをLocal OperationsまたはCodex app-serverから利用するのが最も自然。

次Taskでそのbounded setup / connectionを実装する。

### D. NATIVE_ONLY

現時点でNative Codex surfaceだけ接続可能。

その場合はNative CodexをUnity validation executorとして使い、Task RequestにGit commit / normal push / remote reflectionまで含める。

### E. HOLD

接続条件不足または経路を識別できない。

## 7. Boundaries

Do not:

- Unity project/source/assets/packagesを変更
- Unity packageをinstall/remove/update
- Editor versionをupgrade
- Unity testを実行
- arbitrary Unity command / evalを実行
- license/login/authを変更
- `unity mcp configure` 等のclient config write
- Production Local Operationsを変更
- Worker recoveryを実行
- generic shell runnerを実装
- Local Operations sourceを変更
- Computer Use / GUI automationを使う

このTaskは**調査のみ**。

## 8. Persistence

このTaskを実行するsurfaceがGit commit / push可能なら、Task-owned成果物を自分でcommitし、current GWI branchへnormal non-force pushする。

Native Codex等、Git capabilityが利用可能なsurfaceでは、Repository reflectionまでを完了条件とする。

app-server Worker経路で実行する場合は、Local Operations finalizeを使用する。

新しいreflection Toolは作らない。

## 9. Result

Create:

`work/gwi-0010/GWI-0010-T008_RESULT.md`

Result vocabulary:

- `PASS / APP_SERVER_DIRECT`
- `PASS / HOST_BRIDGE`
- `PASS / SUPPORTED_MCP_ROUTE`
- `PASS / NATIVE_ONLY`
- `HOLD / UNITY_INSTANCE_UNAVAILABLE`
- `HOLD / CONNECTIVITY_PATH_UNRESOLVED`

PASSは「connectivity routeを選べるEvidenceが揃った」ことを意味する。
Unity test capabilityやfull validation readinessのPASSではない。

Final report:
- connectivity gate結果
- surface別接続結果
- transport model
- blocking difference
- selected route
- exact Evidence / commit / remote HEAD
- next bounded Task recommendation
