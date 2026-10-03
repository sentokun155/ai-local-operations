# GWI-0010-T003 Task Request

Task Key: `GWI-0010-T003`
Task Name: `Worker Recovery and Production Runtime Bring-up`
Stage: `implementation / integration`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

現在のDevelopment runtimeを使って次を実装し、実環境で使える状態にする。

1. ChatからQUARANTINED Workerを復旧できる。
2. `C:\Dev\ProdEnv` をLocal Operations Production runtimeとして整備できる。
3. このTask完了後、Chatからworker-01 / worker-02を復旧できる。
4. Production Pluginを起動して最低限pingできる状態まで持っていける。

運用ルールや将来の自動化policyは作らない。現在の個人ツール運用に必要な機能だけ実装する。

## Current facts

- Worker root: `C:\Dev\WorkerRoot`
- Worker count: 5
- Development runtime: `C:\Dev\DevEnv`
- Production runtime target: `C:\Dev\ProdEnv`
- Dev profile: `local-operations-dev`, port 8081
- Prod profile: `local-operations`, port 8080
- T002の `finalize_codex_task` はChat経由E2EまでPASS済み。
- worker-01 / worker-02 は過去probeのResultを保持したままQUARANTINED。
- worker-03 / 04 / 05 はFREE。
- Codexはworktreeを編集し、Local Operationsがcommit / normal pushする。
- Production向けのmain固定、immutable checkout、promotion gate等は不要。

## 1. Worker recovery

MCP Toolとして以下を追加する。

`recover_quarantined_worker(worker_id: str)`

用途は、QUARANTINED Workerのlocal成果を確認・保存して再利用可能にすること。

### Behavior

- 対象WorkerがQUARANTINEDでなければ現在状態を返す。
- stateに残る work_identity / task_key / repository / branch / thread / turn を利用する。
- target repositoryがcleanならWorkerをFREEへ戻す。
- target repositoryに変更があり、紐づくCodex turnがcompletedなら:
  - T002 finalizeと同じGit persistence処理を再利用する。
  -変更をcommit。
  - requested branchへnormal non-force push。
  - final agent message / changed paths / commit SHA / push statusを返す。
  - cleanになればWorkerをFREEへ戻す。
- push/commitに失敗した場合はlocal成果を保持してQUARANTINEDのまま返す。
- force push / reset --hard / clean -fdxは使わない。
- generic recovery frameworkは作らない。

既存finalizeロジックを可能な限り共通化し、QUARANTINED用に同じGit処理を複製しない。

### Current probes

実装後に以下を実環境でrecover可能にする。

- worker-01 / GWI-0010-PROBE-002
- worker-02 / GWI-0010-PROBE-003

probeの診断Resultは保存する方針。不要だから削除するのではなく、可能ならcommit/pushしてFREEへ戻す。

## 2. Production runtime bring-up

ChatからProduction runtimeを整備できる用途限定Toolを追加する。

Candidate:
`prepare_production_runtime(branch: str)`

### Behavior

- targetは固定で `C:\Dev\ProdEnv`。
- repositoryは固定で `sentokun155/ai-local-operations`。
- ProdEnvが存在しなければclone。
- 存在するならorigin identityを確認し、local未保存変更が無ければfetch。
-指定branchをcheckoutし、fast-forward可能なら更新。
- branchは `main` 固定にしない。Chatが指定したbranchを使う。
- DevEnvには触れない。
- Production profile `local-operations` が存在する場合、commandがProdEnvを指すように確認/更新し、Production Tunnelをrestartする。
- health/readyを確認してresponseへ返す。
- profileが存在しない、またはTunnel IDが無い場合は、その不足だけを返す。Tunnel IDを推測しない。
- `CONTROL_PLANE_API_KEY` の値は表示しない。
- worker leaseが存在すること自体をProduction restartのblocking条件にしない。WorkerはDev/Prod runtimeとは独立している。
- clean-checkout purityやmain-only policyを追加しない。

既存 `scripts/restart-prod.ps1`, `scripts/setup.ps1`, `scripts/_runtime-common.ps1` にmain固定や不要なProduction gateが残っており、この実装に関係する部分は簡素化する。

## 3. Development runtime reflection

実装とtests完了後:

- current GWI branchへnormal non-force push。
- Development runtimeをcurrent candidateへ更新し、Dev Tunnelをrestartできるなら実施する。
- Sandbox等でhost runtime更新ができない場合は、無理な迂回をせず、その一点だけCompletion Reportに明記する。

Tool schema変更後、Dev Pluginで以下が見える状態が最終目標:

- `recover_quarantined_worker`
- `prepare_production_runtime`

## 4. Tests

必要最小限。

- quarantined + clean → FREE
- quarantined + completed task + Result変更 → commit/push → FREE
- persistence failure → QUARANTINED維持、local成果保持
- wrong/nonexistent worker
- ProdEnv absent → clone / requested branch
- ProdEnv existing → requested branch fetch/ff
- dirty ProdEnv →変更保持してHOLD
- Prod profile command targets ProdEnv
- Production restart / ready responseはsubprocess mockで確認
- existing dispatch/finalize tests regressionなし

full suiteを1回実行。

## 5. Practical verification

T003実装後にDevelopment runtimeで:

1. Tool catalogにrecovery / production prepareが出ることを確認。
2. worker-01をrecover。
3. worker-02をrecover。
4. 5 WorkerがFREEになったことを確認。
5. `prepare_production_runtime(branch="gwi-0010-ai-local-operations")` を実行。
6. Production runtimeがREADYになることを確認。
7. Production `Local Operations` Pluginで `ping` が成功することを確認。

このTask自身でChatGPT UI操作は不要。最終のTool invocationは呼出元Chatが行う。

## 6. Repository reflection

- Draft PR #1へnormal non-force反映。
- mergeしない。
- force pushしない。
- Completion Reportは簡潔でよい。

Report:
- recovery Tool schema
- production Tool schema
- tests
- Dev runtime反映可否
- implementation commit
- PR URL
-このChatで次に呼ぶべきTool
