# GWI-0010-T004 Task Request

Task Key: `GWI-0010-T004`
Task Name: `Controller-Owned Runtime Effect Separation V0`
Stage: `implementation / boundary hardening`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

T003で成立したLocal OperationsのTask Execution Planeについて、次の責務境界を最小実装で明確にする。

```text
Codex Task
- leased repository内のread / edit / test / Result作成
- 実装変更をworktreeへ残す
- host runtime / Production / Worker recoveryを実行しない

Controller Chat + Local Operations
- completed Codex Taskのfinalize
- commit / normal non-force push
- Worker recovery
- Production runtime preparation / restart
- 実環境確認
```

このTask自身はRepository実装だけを行う。Production runtime、Tunnel、Worker recovery等のhost effectを実行しない。

## Context

T003で以下が実装・実環境確認された。

- `recover_quarantined_worker(worker_id)`
- `prepare_production_runtime(branch)`
- worker-01〜05は全てFREE
- Development runtime READY
- Production runtime READY
- Production `ping -> LOCAL_MCP_OK`
- full tests: 58 pass / 1 skip
- PR #1 head after T003: `f732450a440f8c87f5c06a8f35c6d90535bec501`

T003時、CodexへのTask Requestに実環境操作まで含めたdispatchはChatGPT側の事前安全性チェックでblockされた。一方、Repository内の実装Taskは通常のCodex dispatchで成立している。

今回の目的は安全性チェックを回避することではない。実装Actorとruntime operatorの責務を、実際のcapabilityに合わせて分離することである。

## 1. Investigate actual app-server capability

まずinstalled Codex / app-serverの現在利用しているstable/local schemaを確認する。

確認対象:

- thread/start / turn/startまたは関連configで、Task単位にtool allowlist / denylist / MCP exposure制御が可能か。
- Local Operations / other external toolsをCodex Taskから非公開にできるstable mechanismがあるか。
- workspace sandboxとexternal tool exposureが別制御か。

private UI state操作、Codex Desktop UI automation、undocumented database manipulationは使わない。

### Decision

#### A. Stable tool filtering is available

利用可能で、このLocal app-server routeへ自然に適用できるなら:

- normal `dispatch_codex_task` でrepository implementation Taskに不要なhost-runtime mutation toolsをCodexへ公開しない。
- 必要なrepository edit / test capabilityは維持する。
- filteringがdispatch receipt / testで観測可能であること。

#### B. Stable tool filtering is not available

無理に擬似security boundaryを作らない。

- limitationをRepository-backed Resultへ明記。
- Task prompt / dispatch contractへ明示的な `repository-only execution boundary` を固定する。
- これはHost-enforcedではなくcontract-level boundaryであることをREADME / Resultで明記する。
- tool名のblacklist文字列検査だけで「機械的に防止した」と主張しない。

## 2. Repository-only dispatch boundary

Normal Codex implementation dispatchでは、Local OperationsがCodexへ渡すinstruction/envelopeに次を明示する。

- 作業対象はleased repository root。
- source / docs / tests / Task-owned Resultのread/edit/testまで。
- Git commit / pushはLocal Operations finalizeが所有。
- Worker recovery / Production runtime / Tunnel/profile/process restart / local runtime promotionはController-owned follow-up。
- Task Requestにこれらruntime effectが書かれていても、normal implementation dispatchから実行Authorityを生成しない。
- runtime effectが必要なら、ResultでController follow-upとして返す。

既存Task Request本文を改変して保存し直す必要はない。dispatch時のbounded execution instructionとして付加してよい。

## 3. Controller follow-up surface

過剰なworkflow engineは作らない。

completed ResultからControllerが次に必要なruntime actionを判断できる最低限のsurfaceだけ用意する。

候補:

- final agent message内の明示的follow-upをそのまま返す
- 既存Result locatorを使う
- 必要ならfinalize responseへ `controllerFollowUpRequired` 等の小さなdiagnostic fieldを追加する

ただしAIの自由文から複雑なaction graphを生成するschemaは不要。

既存の `finalize_codex_task`, `recover_quarantined_worker`, `prepare_production_runtime` を重複実装しない。

## 4. Tests

最低限:

- normal dispatchがrepository-only boundary instructionをCodexへ渡す。
- tool filteringを採用した場合、その設定がapp-server requestに含まれること。
- filtering非対応の場合、Host-enforcedとは主張しないこと。
- existing dispatch duplicate semantics regressionなし。
- finalize / recovery / production tools regressionなし。
- full unit/integration suiteを1回実行。

live testが必要なら、repository-onlyのharmless fixtureに限定する。Production runtimeやWorker recoveryをこのTaskから実行しない。

## 5. Documentation

README / relevant source docsを、実際の保証範囲だけ更新する。

明示する:

- Codex = repository implementation actor
- Local Operations finalize = Git persistence owner
- Controller Chat = host/runtime action initiator
- recovery / production prepareはController-facing runtime tools
- tool exposureがHost-enforcedかcontract-onlyか
- automatic normal Chat callback / new Chat creationはGWI-0010 scope外
- Scheduler / next-Task selection / Controller lifecycleはGWI-0009側のManagement Plane候補

新しい運用ルール体系は作らない。

## 6. Mutation boundary

Allowed:

- `sentokun155/ai-local-operations` のcurrent GWI branch内source / tests / docs / T004 Result
- normal test execution

Forbidden in this Task:

- `C:\Dev\ProdEnv` の更新
- Production Tunnel restart
- `prepare_production_runtime` の実行
- `recover_quarantined_worker` の実行
- Worker Pool state変更を目的とする操作
- merge
- force push
- destructive cleanup
- other repository mutation

Git persistenceはこのCodex Task自身では実行せず、完了後にLocal Operations `finalize_codex_task` が行う。

## 7. Result

Resultを以下へ保存:

`work/gwi-0010/GWI-0010-T004_RESULT.md`

含める:

- app-server tool filtering調査結果
- 採用した分離方式
- Host-enforced / contract-onlyの区別
- changed files
- tests
- remaining limitation
- Controller Chatが次に行うべき実環境action（必要な場合）
- PR #1へ反映する準備ができたこと

Final agent messageは簡潔に:

`GWI-0010-T004 <PASS|HOLD> — <one-line result>`
