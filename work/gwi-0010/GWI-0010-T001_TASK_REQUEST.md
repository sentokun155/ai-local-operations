# GWI-0010-T001 Task Request

Task Key: `GWI-0010-T001`  
Task Name: `Repository Migration and Fixed Local Worker Pool V0`  
Stage: `implementation`  
Role: `implementation / local integration`

Repository: `sentokun155/ai-local-operations`  
Branch: `gwi-0010-ai-local-operations`  
Tracking Issue: https://github.com/sentokun155/ai-dev-control/issues/16

## 1. Goal

現在ローカル専用で存在する `C:\Dev\local-mcp` のLocal Operations MCP prototypeを監査し、secret / credential / runtime stateを除く必要な実装をこのRepositoryへ移行する。

そのうえで、Chatがlocal absolute pathを知らなくてもRepository-backed TaskをCodexへdispatchでき、local checkoutが依頼ごとに無制限増加しないよう、**固定Local Worker Pool V0**を実装する。

同時にLocal Operations自身を安全に開発・検証できるよう、Worker Planeとは独立したDevelopment / Production runtime checkoutとTunnelを成立させる。

## 2. Superseded assumption

以前の実装依頼では、logical repositoryから既存checkout / Codex native workspaceを発見するWorkspace Resolutionを主候補としていた。

この前提は本Taskで一部supersedeする。

新しいHuman-confirmed方針:

- 固定数のWorker Slotを用意する。
- 各Slotにはmanaged Repository群の独立cloneを配置する。
- Taskごとに新しいcheckoutを無制限生成しない。
- dispatch時にFREE Slotをleaseし、そのSlot内の対象Repositoryを使用する。
- Task完了後に安全性を確認してclean baselineへ戻し、Slotを再利用する。
- Git worktreeはV0必須ではない。
- Local Operations runtimeはWorker Slot外へ分離する。
- Development / Production MCP runtimeを分離する。

前回実装済みのCodex app-server adapter、DispatchReceipt、duplicate ledger、model compatibility、Task Request identity validation等は、Current Stateを監査して再利用可能なら保持する。先に削除・再実装しない。

## 3. Mandatory current-state audit

実装前に最低限次を確認する。

### 3.1 Repository side

- このTask Request
- root `AGENTS.md`
- root `README.md`
- `.gitignore`
- GWI-0010 Tracking Issue
- existing Draft PR #1

### 3.2 Existing local prototype

`C:\Dev\local-mcp` をreadして、現在の実装・tests・README・dependency・起動方法を確認する。

少なくとも次の既存behaviorを確認する:

- `ping`
- `ping2`
- `dispatch_codex_task`
- Codex app-server thread / turn start
- DispatchReceipt
- model / reasoning effort validation
- duplicate / uncertain dispatch ledger
- Task Request Git blob / branch / commit verification
- Secure MCP Tunnel起動前提
- current tunnel-client profile / startup behavior

### 3.3 Do not import local-only state

以下はRepositoryへコピーしない。

- API key / Tunnel key / GitHub token
- Codex credential
- `.env`
- runtime SQLite ledger
- local logs
- Worker/checkout実体
- venv / cache
- temp Evidence

## 4. Repository migration

現在local-onlyで必要なsource / tests / documentation / dependency metadataを本Repositoryへ移行する。

移行後は、本Repositoryのcommitted sourceをLocal Operations implementationのCanonical sourceとする。

Local `C:\Dev\local-mcp` を直接編集し続ける二重Authorityを正常運用にしない。

Historical prototypeからRepositoryへimportした後、Development / Production runtimeはそれぞれGit checkoutとしてCanonical Repository revisionから更新する。

## 5. Runtime topology

### 5.1 Canonical source

`sentokun155/ai-local-operations`

### 5.2 Development runtime

Absolute runtime checkout:

`C:\Dev\DevEnv`

Purpose:
- candidate / GWI branch revisionの動作確認
- Development MCP server
- Development Tunnel
- ChatGPT `Local Operations Dev` Pluginから利用

Profile:

`local-operations-dev`

Development Tunnel IDはProductionと別にする。

### 5.3 Production runtime

Absolute runtime checkout:

`C:\Dev\ProdEnv`

Purpose:
- accepted / main revisionの安定運用
- Production MCP server
- Production Tunnel
- ChatGPT `Local Operations` Pluginから利用

Profile:

`local-operations`

Production Tunnel IDはDevelopmentと別にする。

### 5.4 Worker/runtime separation

Worker Slot内の `ai-local-operations` cloneは実装作業場所。

Development / Production MCP serverをleased Worker Slotから直接起動しない。

通常flow:

```text
Worker Slotで実装
→ commit / non-force push
→ C:\Dev\DevEnv をcandidate revisionへ安全に同期
→ Development Tunnel再起動
→ Local Operations Devで検証
→ acceptance / merge
→ C:\Dev\ProdEnv をaccepted mainへ安全に同期
→ Production Tunnel再起動
```

Dev / Prod runtime checkoutでunexpected dirty state / divergenceがある場合、自動resetで破棄せずHOLD。

## 6. Runtime API key

標準runtime credentialはWindows User environment variable:

`CONTROL_PLANE_API_KEY`

を利用する。

Requirements:

- Repositoryへkeyを保存しない。
- `.env`へ必須保存する設計にしない。
- restart / startup scriptへkeyをcommand-line argumentで渡さない。
- keyの実値をstdout / log / Tool responseへ表示しない。
- Dev / Prodで同じRestricted Runtime keyを共有可能。
- Development / Productionは別Tunnel ID。
- 将来のDev / Prod key分離を妨げない。

`CONTROL_PLANE_API_KEY` 未設定時は安全に起動を停止し、設定不足のみを表示する。

## 7. Operational scripts

Repository-backed PowerShell scriptsを実装する。

### 7.1 `scripts/setup.ps1`

Initial setup / validation専用。

最低限:

- `C:\Dev\DevEnv` / `C:\Dev\ProdEnv` のruntime layoutを準備または検証
- expected repository identityを確認
- required tools / dependencyの存在確認
- Development / Production profile設定前提を確認
- `CONTROL_PLANE_API_KEY` の存在確認
- secret valueを表示しない
- runtime checkoutへsecretを書き込まない
- destructive recoveryをしない
- 不足事項をactionableに報告

API keyそのものをscriptへ埋め込まない。

### 7.2 `scripts/start-all.ps1`

PC起動時等の通常起動。

最低限:

- Development / Production両Tunnelを起動
- 同じenvironmentを二重起動しない
- Dev / Prodを別process / profileとして扱う
- 起動後にそれぞれのhealth / admin UI確認先を表示
- 起動失敗をenvironment別に診断可能
- 一方の失敗で他方を不必要に停止しない

### 7.3 `scripts/restart-dev.ps1`

Development専用。

- runtime: `C:\Dev\DevEnv`
- profile: `local-operations-dev`
- Production process / checkoutへ触れない
- candidate branch / revisionの実行を許容
- dirty/divergenceを破棄しない
- safe update / restart / health確認

### 7.4 `scripts/restart-prod.ps1`

Production専用。

- runtime: `C:\Dev\ProdEnv`
- profile: `local-operations`
- Development process / checkoutへ触れない
- expected accepted/main revision policyを維持
- GWI candidate branchを暗黙実行しない
- dirty/divergenceを破棄しない
- safe update / restart / health確認

### 7.5 Tool Catalog refresh documentation

MCP Tool schemaを変更した場合:

1. 対象Tunnelを再起動
2. ChatGPT Webで対象Pluginを開く
3. 管理 → ツールの更新
4. Tool listを確認
5. staleなら新規Chatで再確認

をREADMEへ残す。

## 8. Worker Pool V0

### 8.1 Worker model

固定数のWorker Slotを設定可能にする。

最低状態:

- `FREE`
- `LEASED`
- `DIRTY`
- `QUARANTINED`

1 Slotは同時に1 Taskだけへlease可能。

Worker数はコード固定値にせずconfigurationで変更可能にする。

Testsでは2 Slot等の小さいfixtureを使用してよい。

### 8.2 Worker layout

Human intent:

```text
<worker-root>/
  worker-01/
    ai-dev-control/
    ai-operations-skills/
    ai-local-operations/
    2Dhakusura/
    ...
  worker-02/
    ai-dev-control/
    ai-operations-skills/
    ai-local-operations/
    2Dhakusura/
    ...
```

全managed Repositoryを各Slotへ独立cloneする。

Codexへ渡すcwdはWorker rootではなく、対象Repository root。

同じSlot内の他Repositoryを通常Task workspaceとして渡さない。

Codex Desktop Project登録はrouting Authorityにしない。Local Operationsがresolved Repository rootをapp-server cwdとして明示する。

### 8.3 Managed repository configuration

managed Repositoryはconfigurationで定義する。

最低限:

- logical identity: `owner/name`
- clone/fetch URL
- default branch

actual local worker root / slot count等はlocal configurationとして扱い、machine-specific Worker absolute pathをRepository Canonical dataへ固定しない。

Dev / Prod runtime pathは本TaskでHumanが明示したruntime topologyとして固定する。

example config / schemaはGit管理可能。

credentialはGit管理しない。

### 8.4 Pool bootstrap

既存Slotが無い場合に、boundedな明示bootstrap手順を提供する。

bootstrapで各managed Repositoryを各Workerへclone / initializeできること。

通常dispatchのたびに新しいcloneを作らない。

bootstrapはgeneric arbitrary shell MCP Toolとして公開しない。

CLI/admin operationまたは用途限定maintenance entrypointでよい。

## 9. Dispatch input contract

正常系のChat入力からlocal absolute pathを除く。

最低限candidate:

```text
work_identity
task_key
task_name
repository            # logical owner/name
branch
task_request_locator  # repo-relative
model?
reasoning_effort?
pull_request?         # optional, if useful for preflight
```

既存explicit path modeは、互換性やlocal diagnosticのためoverrideとして残してよい。

ただし正常系でChatへlocal absolute pathを要求しない。

Tool schema変更後はREADMEへbefore/afterを記録する。

## 10. Worker allocation

dispatch時:

1. Worker Pool stateを取得。
2. `FREE` Slotを1つだけatomic/boundedにlease。
3. 同一 `work_identity + task_key` duplicate stateを確認。
4. 対象Repository cloneを解決。
5. preflight成功後にCodex dispatch。
6. DispatchReceiptへ最低限worker identity / resolved repository rootを診断可能な形で保持する。ただし不要にmachine secretを外部へ返さない。

FREE Slotが無ければHOLD。

同じSlotを2 Taskへ割当しない。

## 11. Repository preflight

対象Workerの対象Repositoryについて、Codex dispatch前に最低限確認する。

- Git repositoryである
- configured logical repository identityと一致
- `origin` / expected remoteが説明可能
- fetch可能、または明示的offline HOLD
- dirty tracked changesなし
- unexpected untracked stateがsafe reuseを阻害しない
- requested branchのremote/local状態
- local / remote divergence
- Task RequestがRepository内に存在
- Task RequestがGit tracked
- committed Git blobと一致
- repository commitを固定

### 11.1 PR-aware check

TaskにPRが明示されている場合、可能ならPR head branchとrequested branchの一致を確認する。

GitHub CLI/API等のstable local capabilityが必要で利用不能なら、無検証成功にせずcapability limitationを明示する。

PRがまだ無いTaskを必ずHOLDする仕様にはしない。

### 11.2 Preparation

安全に準備できる場合のみ:

- fetch
- requested branch checkout
- fast-forward等のnon-destructive同期

を行う。

unexpected divergence / local-only commit / dirty stateを `reset --hard` や `clean -fdx` で自動破棄して解決しない。

問題があればSlotを `DIRTY` / `QUARANTINED` としてdispatchしない。

## 12. Codex dispatch

既存の安全境界を維持する。

- Repository-backed Task RequestがCanonical
- exact repository / branch / commit / Task Request blobをmanifestへ含める
- mismatch時はCodexへHOLDを要求
- `workspace-write` sandbox
- generic shell exposureなし
- dispatchはforce-push / merge / publication / deployment Authorityを生成しない
- `DISPATCHED` は `turn/start` acknowledgementのみ

Thread nameは `Task Key + Human-readable Task Name` を維持する。

model / reasoning effort compatibility checkを維持する。

## 13. Duplicate / uncertain outcome semantics

既存 `work_identity + task_key` ledgerを維持する。

- accepted / uncertain dispatchではduplicate Taskを作らない
- explicit reject時は既存thread retryを利用可能
- pre-dispatch validation HOLDは、条件修復後の正常dispatchを永久に阻害しない

Worker leaseとdispatch ledgerのtransaction boundaryを明確にする。

dispatch failure時にSlotが永久LEASEDにならないよう、失敗classごとのstate transitionを定義する。

ただしoutcome uncertain時に誤ってFREEへ戻してduplicate dispatchを許さない。

## 14. Completion / release V0

Codex Task completionとWorker releaseを分離する。

V0でcompletionを自動観測するstable routeが無い場合、用途限定の明示release operationを追加してよい。

例:

- `get_worker_pool_status`
- `release_codex_worker`

名称は実装時に調整可能。

### 14.1 Release gate

WorkerをFREEへ戻す前に最低限確認:

- 対象Task / Worker identity一致
- working tree clean
- local-only commitなし
- required branch commitがremoteへ反映済み、またはrelease policy上明示的に安全
- Repository-backed Result / Evidence requirementがTask Requestにある場合、それを破壊しない
- Codex/app-server processが当該workspaceを実行中ではない

### 14.2 Baseline restore

release可能なら対象Repositoryをdefault branch等のclean baselineへ戻す。

安全な操作:

- checkout default branch
- fetch
- fast-forward可能な更新

禁止:

- unexpected stateに対する自動 `reset --hard`
- local-only dataを消す `clean -fdx`
- branch deletion
- force push

安全に戻せなければ `QUARANTINED`。

他managed RepositoryもTask中に変更されていないか、Slot再利用前に必要範囲で確認する。

## 15. Worker Pool persistence

Worker lease stateはlocal runtime state。

Repositoryへruntime DBをcommitしない。

SQLite等を利用してよい。

最低限保持候補:

- worker_id
- state
- work_identity
- task_key
- repository
- branch
- thread_id
- leased_at
- updated_at
- failure / quarantine reason

既存dispatch ledgerと同一DBに統合するか別DBにするかは、atomicity /責務分離を比較して決める。

## 16. Security

維持:

- Personal plugin前提
- bounded tools
- server-side validation
- no generic `run_shell`
- no secret response
- no implicit authority escalation

Worker cloneにはユーザーのGit credential helper等が利用され得るため、credentialをconfigやlogへ展開しない。

Dev / Prod Tunnel credentialは `CONTROL_PLANE_API_KEY` を環境から取得し、Repository-backed sourceやprocess command lineへsecretを展開しない。

## 17. Tests

### 17.1 Migration regression

- `ping` PASS
- `ping2` PASS
- existing dispatch prototype behavior regressionなし
- README/startup route確認

### 17.2 Runtime topology / script tests

可能な範囲でprocess invocationをmock / fixture化し、最低限:

- setupがAPI key未設定をsecret漏洩なく検出
- restart-devがProdへ触れない
- restart-prodがDevへ触れない
- Dev / Prodが別profile
- same environment duplicate startを防ぐ
- dirty runtime checkoutを破棄しない
- candidate revisionがProdへ暗黙導入されない

### 17.3 Worker Pool unit

- FREE→LEASED
- same Slot duplicate lease拒否
- no FREE Slot→HOLD
- LEASED→FREE safe release
- dirty→DIRTY/QUARANTINED
- ambiguous/missing repo→HOLD
- wrong remote→HOLD
- wrong branch/divergence→HOLD
- local-only commit→release拒否
- unexpected untracked/dirty stateを破棄しない

### 17.4 Dispatch integration

- logical repository + branch + repo-relative Task Requestだけでdispatch
- Chat/local callerはabsolute path不要
- Codex cwdはselected Workerのtarget repo root
- exact Task Request blob / commit固定
- concrete `DISPATCHED` receipt取得
- duplicate guard維持

### 17.5 Release integration

- successful probe後にexplicit/safe release
- default branchへnon-destructive復帰
- Worker再利用可能
- unsafe stateはQUARANTINED

### 17.6 E2E probe

実GWI Taskを使わない専用fixture repository / Task Requestで:

```text
Chat-equivalent logical dispatch
→ Worker allocation
→ repo preparation
→ Codex thread/start
→ turn/start
→ DISPATCHED receipt
→ bounded completion
→ release
→ Worker FREE
```

を1回通す。

GWI-0006 / GWI-0009の実Taskをimplementation probeとして勝手に実行しない。

Development runtime側でprobeする。Production runtimeへcandidate implementationを持ち込まない。

## 18. Documentation

READMEをRepository-backed operational guideとして更新。

最低限:

- Canonical source
- Dev / Prod runtime topology
- normal startup
- Tool Catalog update
- API key setup
- deployment/source-of-truth model
- configuration
- Worker layout
- bootstrap
- dispatch
- status
- release
- quarantine recovery
- duplicate semantics
- security
- troubleshooting

machine-specific secretの実値をcommitしない。

Human-confirmed runtime path `C:\Dev\DevEnv` / `C:\Dev\ProdEnv` は運用契約として明記してよい。

## 19. Repository reflection

実装・tests完了後:

1. Current branch `gwi-0010-ai-local-operations` へcommit。
2. normal non-force push。
3. remote HEAD readback。
4. changed critical files readback。
5. existing Draft PR #1を更新。
6. mergeはしない。
7. Tracking Issue #16へResult receiptを残す。

## 20. Completion report

必須:

- audited local prototype summary
- imported / excluded files
- source-of-truth migration方式
- Dev / Prod runtime topology
- Tunnel/profile separation
- API key handling
- operational scriptsと検証結果
- Worker Pool architecture
- configuration format
- state machine
- preflight behavior
- dispatch Tool schema before/after
- release Tool / admin interface
- tests and exact results
- Development E2E probe DispatchReceipt
- Worker reuse/release evidence
- security boundary
- remaining limitations
- commit SHA
- remote HEAD
- PR URL
- Issue receipt URL

## 21. Stop / HOLD conditions

次の場合は推測で進めずHOLD:

- local prototypeにsecret混入があり安全なmigration boundaryを確定できない
- Codex app-server behaviorがCurrent installed versionで確認できない
- Dev / Prod Tunnel ID / profileを安全に区別できない
- Worker cleanupにlocal-only state破棄が必要
- repository identity / branch / Task Request blobを一意に確定できない
- destructive Git操作なしでは回復できない
- Human Decisionが必要な重大trade-offが発生
