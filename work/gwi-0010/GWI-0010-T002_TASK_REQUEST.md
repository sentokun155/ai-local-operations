# GWI-0010-T002 Task Request

Task Key: `GWI-0010-T002`  
Task Name: `Codex Result Persistence and Intake V0`  
Stage: `implementation / integration`  
Role: `Local Operations lifecycle completion`

Repository: `sentokun155/ai-local-operations`  
Branch: `gwi-0010-ai-local-operations`  
Tracking Issue: https://github.com/sentokun155/ai-dev-control/issues/16  
Draft PR: https://github.com/sentokun155/ai-local-operations/pull/1

## 1. Goal

T001で成立した Fixed Local Worker Pool / logical repository routing / Codex app-server dispatch に、Codex完了後の **Repository Persistence / Result Intake** を追加する。

正常系を次の責務分離へ変更する。

```text
Chat
→ Local Operations: PREPARE
→ Codex: EXECUTE
→ Local Operations: PERSIST
→ Local Operations / Chat: INTAKE
→ Local Operations: RELEASE
```

Codexはleased Worker内の対象Repository worktreeを編集する。Codex自身に `.git` 更新、commit、push、ChatGPT通常chatへの直接送信を要求しない。

Local OperationsがCodex完了後の変更を検証し、boundedなGit操作でcommit / non-force push / remote readbackを行い、Chatが取得可能なResultを返した後、安全にWorkerを再利用可能にする。

## 2. Authority / current knowledge

実装前に必ず以下を読む。

- root `AGENTS.md`
- root `README.md`
- `work/gwi-0010/ENTRY.md`
- `work/gwi-0010/VALIDATION_KNOWLEDGE.md`
- `work/gwi-0010/GWI-0010-T001_TASK_REQUEST.md`
- Tracking Issue #16
- current Draft PR #1
- current source/tests

T001 historical Task Requestは変更しない。

root `AGENTS.md` の **Personal-tool proportionality rule** を本Taskにも適用する。理論上の完全性だけを理由に状態・gate・Evidenceを増やさない。

## 3. Human-confirmed runtime

- Development runtime: `C:\Dev\DevEnv`
- Production runtime: `C:\Dev\ProdEnv`
- Worker root: `C:\Dev\WorkerRoot`
- Worker count: `5`
- Worker config: `%LOCALAPPDATA%\LocalOperations\worker-pool.json`
- Supported operational shell: PowerShell 7+ / `pwsh.exe`
- Development Plugin: `Local Operations Dev`
- Development profile: `local-operations-dev`

Productionへcandidateを導入しない。

## 4. Confirmed findings that supersede earlier assumptions

### 4.1 app-server Task is a Codex Task, not a ChatGPT chat

Local Operationsから `thread/start` / `turn/start` したTaskはCodex側のTask一覧に表示された。

Codex Desktopで開くと「別のアプリで開いています」と表示される場合があり、Local Operations app-serverが外部clientとしてthreadを保持していることと整合する。

このTaskをChatGPT通常chatと同一surfaceとして扱わない。

### 4.2 Direct Codex → ChatGPT chat return is unavailable

PROBE-001 / PROBE-003で、app-server Task contextから利用可能なTool catalogを確認した。

確認結果:
- ChatGPT chat一覧取得 capability: absent
- ChatGPT chat message送信 capability: absent
- generic UI automationは専用chat return routeとして採用しない

よってCodex自身に「呼出元Chatへ送信」を要求する設計を正常系にしない。

### 4.3 Codex subagents are available

PROBE-004で実測確認:

```text
VERDICT: PASS
SPAWN_AGENT: present
WAIT_AGENT: present
MESSAGE_TOOL: send_message
CLOSE_AGENT: absent
CHILD_STARTED: yes
CHILD_RESULT: GWI-0010-PROBE-004 SUBAGENT_OK
```

Root Codex Taskは必要に応じてsubagentを使用可能。

本Taskではsubagent数やorchestration policyを新設しない。既存Codex capabilityとして利用を妨げないことだけを維持する。

### 4.4 workspace-write edits files but does not provide the required Git persistence route

PROBE-003ではResultファイル自体はworktreeへ作成できたが、`git add` が `.git/index.lock` の作成拒否で失敗した。

またdispatch manifestのauthority boundaryによりpushも実施されなかった。

したがって正常系を以下にしない:

```text
Codex
→ edit
→ git add
→ commit
→ push
```

採用する責務分離:

```text
Codex
→ edit / test / Result
→ completed

Local Operations
→ validate
→ commit
→ non-force push
→ remote readback
```

### 4.5 Current release behavior exposes the missing phase

CodexがResultやsource変更をworktreeに残した状態で現行 `release_codex_worker` を実行すると、Local Operationsはデータを破棄せずWorkerをQUARANTINEDにする。

これは安全側の既存behaviorとして維持する。

Current observed recovery input:
- worker-01: PROBE-002由来でQUARANTINED
- worker-02: PROBE-003由来でQUARANTINED
- worker-03以降: safe release経路を確認済み

T002では既存local-only成果を勝手に削除しない。

## 5. Lifecycle V0

### 5.1 PREPARE — Local Operations

既存T001のWorker allocation / repository preflightを監査して再利用する。

正常系:

1. FREE Workerをatomicにlease。
2. logical repositoryから対象cloneを解決。
3. expected remote identityを確認。
4. `git fetch origin`。
5. exact requested branchをcheckout。
6. remote branchとlocal branchを確認。
7. safeな場合だけfast-forward。
8. divergence / local-only commit / unexpected dirtinessならHOLDまたはQUARANTINED。
9. Task Requestのtracked / committed blobを照合。
10. dispatch baseline commitを保存。
11. 対象Repository rootをCodex cwdとしてdispatch。

単純な `git pull` にmerge/rebaseの暗黙挙動を持たせない。

既存実装がこの要件を既に満たす部分は再実装しない。

## 6. EXECUTE — Codex

Codexの責務:

- Task Requestを読む
- source / docs / tests / Repository-backed Result等、Taskで必要なworktreeファイルを変更
- test / verificationを実行
- 必要ならsubagentを使用
- final agent messageを返す
- turnをcompletedにする

Codexの正常責務に含めない:

- `git add`
- `git commit`
- `git push`
- force push
- merge
- deployment / publication
- ChatGPT通常chatへの直接送信

Task Requestが古い前提でCodex自身へcommit/pushを要求している場合でも、Local Operations経由実行ではPersistence責務をLocal Operations側へ正規化できる設計にする。過去Task Requestを遡及変更しない。

## 7. PERSIST — Local Operations

用途限定のbounded operationを追加する。

Candidate tool name:

`finalize_codex_task`

名称は実装上の一貫性が改善する場合のみ変更可。その場合READMEとTool schemaを同期する。

### 7.1 Required input

最低限:

- `worker_id`
- `work_identity`
- `task_key`
- explicit confirmation that persistence is requested

Chatがlocal absolute pathを指定する必要はない。

### 7.2 Pre-persistence gate

Local Operations自身が最低限確認:

- Workerが指定TaskへLEASED中
- saved dispatch identity一致
- acknowledged thread / turn一致
- Codex turn statusが `completed`
- exact target repository / branch一致
- sibling managed Repositoryにunexpected変更なし
- target worktreeの変更一覧を取得可能
- dispatch後にremote branchが予期せず進んでいない
- force / destructive recovery不要

remoteが進んだ / divergenceした場合は、勝手にforce / rebase / resetせずHOLDする。

### 7.3 Change handling

Codexが作ったtarget Repositoryのworktree変更をRepository-backed成果としてpersistする。

- Git ignored runtime/cache/credential stateをstageしない。
- `.git`自体を操作対象ファイルとして扱わない。
- repositoryの既存secret/runtime deny boundaryを維持。
- 明らかなcredential / runtime artifactを検出した場合はcommitせずHOLD。
- sibling Repository変更は自動commitしない。
- unexpected local-only dataを自動削除しない。

Personal toolであるため、汎用的な巨大policy engineや細粒度path allowlist systemを新設しない。具体的riskを防ぐ最小のvalidationにする。

### 7.4 Commit

Local Operations host processがtarget Repositoryでbounded Git persistenceを行う。

- exact current task branchのみ
- normal commit
- Task identityを説明可能なcommit message
- amend不要
- branch deletionなし
- remote変更なし

Codex subprocessへGit metadata write authorityを広げることで解決しない。

### 7.5 Push

- exact configured remote / exact requested branch
- normal non-force pushのみ
- force / force-with-lease禁止
- push reject時はHOLD
- unexpected remote advancement時はHOLD

### 7.6 Remote readback

push成功だけで完了にしない。

最低限:

- local HEAD
- remote target branch HEAD
- commit identity
- Repository-backed ResultがTaskで生成された場合、その存在を確認可能

正常系ではlocal persisted commitとremote branch HEADの一致を確認する。

## 8. INTAKE — Local Operations / Chat

CodexからChatGPT通常chatへの直接送信を要求しない。

Local OperationsがCodex app-server `thread/read` を使用し、Chatが取得可能なbounded Resultを返す。

Candidate:
- `finalize_codex_task` のresponseへResult Intakeを統合
- または責務が明確になるなら read-only `get_codex_task_result` を追加

不要なTool分割はしない。

最低限Chatへ返せる情報:

- status
- work identity / task key
- worker id
- thread id / turn id
- Codex turn status
- final agent message（利用可能な範囲）
- changed paths summary
- persistence status
- persisted commit SHA
- remote HEAD
- Repository-backed Result locator(s)を説明可能な場合そのlocator
- HOLD reason / recovery hint

secret / credential / raw auth情報を返さない。

### 8.1 No automatic Chat callback in T002

Codex / Local Operationsから既存ChatGPT chatを自動再開するcallback routeは本Taskで作らない。

T002の完了条件は:

```text
Chat
→ Local Operations tool call
→ completed Codex Taskをfinalize / intake
→ Resultを同じChat turnへ返せる
```

まで。

future eventでHuman操作なしにChat/Management Cycleを再開する責務はGWI-0009等のowner scopeと調整する。本Repositoryへauto-continuation policyを持ち込まない。

## 9. RELEASE — Local Operations

正常系:

```text
Codex completed
→ persistence requested
→ validation
→ commit
→ non-force push
→ remote readback
→ Result Intake available
→ clean baseline restore
→ FREE
```

変更がないread-only TaskはPersistence commit不要でsafe release可能。

変更があるのにPersistence未完了ならFREEへ戻さない。

unsafe stateでは既存通りQUARANTINEDし、local-only dataを消さない。

既存 `release_codex_worker` と新finalize operationの責務が重複する場合、例外を積み増さず構造を簡素化する。Personal-tool proportionality ruleに従い、最小の明瞭なlifecycleにする。

## 10. Quarantined probe recovery

T002実装後、Development runtimeで既存probe由来Workerを確認する。

少なくとも:

- worker-01 / PROBE-002
- worker-02 / PROBE-003

既存local Result / worktree変更をinspectしてから扱う。

- 必要な診断Resultは回収する。
- 不要と判断したprobe-only変更を破棄する場合も、何を破棄するかを明示してから行う。
- `reset --hard` / `clean -fdx` を盲目的な回復手段として使わない。
- recovery後、safeならFREEへ戻す。

このrecoveryはPersistence / quarantine recovery pathの実環境確認として利用してよい。

## 11. Codex executable discovery follow-up

本Taskはdispatch / completion lifecycleを実修正するため、同じaffected areaにある既知のCodex discovery不足もproportionality ruleに従い再評価する。

Confirmed:
- Codex Desktop付属CLIは存在する
- example observed version: `codex-cli 0.158.0-alpha.2.1`
- `codex app-server --help` は成功
- 通常PowerShell PATHには `codex` が無く、Local Operationsが `shutil.which("codex")` のみを使うと `CODEX_UNAVAILABLE` になった
- Dev processへ一時PATHを継承するとdispatch成功

Minimal acceptable remediation:
- explicit configured executable overrideをサポートするか、
- setup/runtime診断でCodex Desktop executableをstableに解決するか、
- それと同等に「Dev runtimeが実際に使用するCodex executable」を説明可能にする

versioned internal pathをRepositoryへ固定しない。

起動不能時は、PATH not found / process start failure / initialize failureを診断上区別できることが望ましい。ただし過剰なdiagnostic frameworkを作らない。

## 12. Tests

### 12.1 PREPARE regression

- logical repository route維持
- exact branch fetch / checkout / ff-only
- wrong remote / divergence / dirty baselineで安全停止
- Task Request blob identity維持
- duplicate dispatch semantics維持

### 12.2 Persistence unit/integration

最低限:

- completed Task + changed target worktree → commit可能
- exact task branchへnon-force push
- remote readback成功
- remote advanced / divergence → HOLD、forceなし
- sibling repository変更 → commitせずHOLD/QUARANTINE
- forbidden runtime / credential artifact → commitせずHOLD
- Git persistence失敗 → local成果を破棄せずHOLD/QUARANTINE
- no-change Task → commit不要でrelease可能

### 12.3 Result Intake

- `thread/read includeTurns=true` からtarget turnを確認
- final agent messageをbounded responseへ反映
- persisted commit / remote HEADをresponseへ反映
- unavailable itemを捏造しない
- secretを返さない

### 12.4 Release

- successful persistence後にdefault baselineへ安全復帰
- Worker FREE
- persistence未完了のdirty WorkerをFREEにしない
- unsafe stateの自動削除なし

### 12.5 Codex discovery

supported Dev runtimeから:
- actual executable resolution
- `--version`
- app-server initialize

を最低1回検証する。

## 13. Development E2E

Productionを変更せず、`Local Operations Dev` で1件の専用fixture/probeを通す。

Required flow:

```text
Chat-equivalent logical dispatch
→ Worker lease
→ fetch / exact branch sync
→ Codex Task start
→ Codex writes a harmless Repository-backed Result file
→ turn completed
→ Local Operations finalize
→ commit
→ non-force push to disposable/probe branch or fixture remote
→ remote readback
→ Result Intake response
→ baseline restore
→ Worker FREE
```

実GWI-0006 / GWI-0009 Taskをimplementation probeとして勝手に使用しない。

追加で、既に確認済みのsubagent capabilityを壊していないことを軽量に確認してよいが、subagent framework自体の新設は不要。

## 14. Tool catalog / Dev deployment

Tool schemaを変更したら:

1. source/tests/docs更新
2. normal non-force repository reflection
3. `C:\Dev\DevEnv` をcandidate revisionへ安全に同期
4. `scripts/restart-dev.ps1`
5. ChatGPT Web → `Local Operations Dev` → 管理 → ツールの更新
6. new/updated Toolが見えることを確認
7. actual Chat → Dev Plugin E2Eを実施

Productionへcandidateを反映しない。

## 15. Documentation

README / AGENTS / VALIDATION_KNOWLEDGE / ENTRYのうちaffected内容を同期する。

最低限READMEへ:

- PREPARE / EXECUTE / PERSIST / INTAKE / RELEASE
- Codexはworktree編集、Local OperationsはGit persistence
- ChatGPT chat direct callbackは存在しない
- subagent capabilityはCodex Task内で利用可能
- persistence HOLD / quarantine recovery
- Codex executable discovery
- Dev E2E手順

を説明する。

古い「Codexがcommit/pushまで担当する」正常系記述がある場合は更新する。

## 16. Bootstrap constraint for T002 itself

T002は、まさに「Codex完了後のLocal Operations Git persistence」を実装するbridge Taskである。

したがってT002自身の最初の実装runでは、未実装のfinalize機能へ自己依存しない。

初回reflectionは既存の明示的・非forceなRepository write routeで行い、どのrouteを使ったかCompletion Reportに記録する。

T002完成後のE2Eから新しいPersistence routeを使用する。

## 17. Repository reflection

実装完了後:

- branch: `gwi-0010-ai-local-operations`
- normal non-force update only
- remote HEAD readback
- critical changed-file readback
- Draft PR #1 update
- Tracking Issue #16へResult receipt
- mergeしない
- Productionへpromoteしない

## 18. Completion Report

必須:

- audited current lifecycle
- confirmed probe findingsをどう反映したか
- final PREPARE / EXECUTE / PERSIST / INTAKE / RELEASE contract
- added/changed MCP Tool schema
- Git persistence safety boundary
- remote advancement / divergence behavior
- Codex executable resolution方式
- Result Intake response example
- quarantined probe recovery result
- unit/integration/full suite results
- Development E2E receipt
- persisted commit / remote readback evidence
- Worker FREE evidence
- remaining limitation: automatic Chat callback未実装
- implementation commit SHA
- remote HEAD
- PR URL
- Issue receipt URL
- T002自身のbootstrap reflection route

## 19. Stop / HOLD

以下は推測で進めずHOLD:

- target repository / branch / lease identityを一意に確定できない
- Codex turn completionを確認できない
- remote divergenceをnon-destructiveに解消できない
- persistenceにforce / destructive cleanupが必要
- unexpected sibling repository変更がある
- secret / credential混入の疑いがある
- local-only workを破棄しないと続行できない
- Production変更が必要
- auto-continuation policyなどGWI-0009 owner scopeの判断が必要
