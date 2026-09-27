# GWI-0010-T005 Task Request

Task Key: `GWI-0010-T005`
Task Name: `Worker Execution Capability Audit and Validation Routing`
Stage: `investigation / design input`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

T004で判明した「Codex Workerはsource編集できるが、Repositoryが要求する正式な検証環境を必ずしも使えない」Gapを、Python固有問題としてではなく**Worker / Codex execution capability全体の問題**として調査する。

将来のUnity Repository（DCCF / Unity 6000.1.x）でEditMode / PlayMode test、batchmode test、Package Manager依存等を扱うことも前提に、Capabilityを実測・分類し、次にどのValidation execution pathを実装すべきか判断可能なRepository-backed design inputを作る。

このTaskではgeneric runnerやUnity runnerをまだ実装しない。

## Context

T004 Result:

- Codex Workerはrepository worktree editを実行できる。
- observed Windows sandboxではCodex自身の通常Git metadata writeが成立しない事例がある。
- T004ではPython >=3.13 + locked dependency環境をWorkerで再現できず、full suiteが完走しなかった。
- fallback Python 3.12では一部testsは実行できたが、`mcp` dependency不足で主要modulesがimportできなかった。
- networkからdependency/interpreterを取得する試行は拒否された。
- T004候補自体はLocal Operations finalizeによりcommit / push済み。
- 現行normal dispatchはrepository-only contract boundaryを持つ。

T005はT004のHOLDを直接PASSへ昇格するTaskではない。
まず再発し得るCapability gapを一般化して調査する。

## 1. Capability classes

各Capabilityを最低限以下に分類する。

### A. ACTOR_LOCAL

Codex Worker自身がnormal implementation Task内で安全・安定して実行可能。

例候補:
- repository file read/edit
- bounded test command
- local compiler/interpreter
- read-only Git
- repository-local script

### B. HOST_EXECUTED

Codex Workerから直接は不安定・不可・不適切だが、Local Operations / Controller側のbounded host toolで実行するのが適切。

例候補:
- locked dependency environment preparation
- Python/uv environment setup
- Unity Editor batchmode tests
- dotnet/MSBuildなどhost toolchain
- test artifact / log collection
- long-running external processes
- network-dependent restore/install

### C. HUMAN_OR_EXTERNAL

自動実行に適さない、Human Decisionや外部認証が必要、または現時点では安全に自動化しないもの。

例候補:
- GUI-only interaction
- interactive login/license acceptance
- Human judgment
- unsupported destructive repair

分類は推測ではなくEvidenceとlimitationsを添える。

## 2. Audit targets

少なくとも以下を調査する。

### Filesystem / repository

- repository worktree read
- repository worktree write
- repository外read
- repository外write
- temporary directory
- symlink/junctionの扱い
- ignored files
- large file / generated artifact placement

### Git

- `git status`, `diff`, `log`, `show`, `rev-parse`
- `git add`
- commit
- branch checkout/switch
- fetch
- push

mutating Git probeはこのTaskで実行しない。
既存Evidenceとsafe read-only probesからCapabilityを分類する。

### Process execution

Safe read-only/version probesで可能な範囲を確認:

- PowerShell / pwsh
- cmd
- Python
- uv
- dotnet
- MSBuild if present
- Unity / Unity Hub if discoverable
- Git
- Node/npm if present
- Codex CLI

process起動可否、PATH、environment inheritance、working directory、timeoutを観測する。

### Python / dependency resolution

- project要求Python version
- Workerから利用可能なPython
- `uv run --locked` の成立条件
- uv cache access
- offline dependency availability
- network dependency download可否
- existing Development environmentをWorkerから安全に共有可能か
- shared venv / shared uv cacheが適切か

既存DevEnvをWorker taskから変更しない。

### Network

safe probeまたは既存sandbox/app-server configから:

- outbound network availability
- package registry access
- Git remote accessの経路
- MCP / app/plugin経路との違い

network enableを変更しない。

### MCP / Plugin / external tools

- Codex app-server Taskに見えるtool families
- per-task filtering / plugin disable capability
- Local Operations PluginがCodex側に見えるか
- repository-only contractとtool exposureの差

T004の調査を再利用し、重複調査は避ける。

### Long-running processes

- timeout / cancellation semantics
- child process survival
- process tree cleanup
- output/log capture
- scheduler/controllerがpollingすべきprocess type

実際に長時間processを放置しない。

## 3. Unity-specific future requirement

将来DCCFでUnity testを自動実行する要件を明示的に考慮する。

Current known product facts:

- Windows PC
- Unity 6000.1.x
- URP
- Entities 1.3
- Unity Test Frameworkを将来Validationへ利用する可能性がある

調査項目:

- Unity Editor executable discovery方法
- Unity Hub依存の有無
- `-batchmode`, `-runTests`, `-testPlatform EditMode`, `PlayMode`, `-testResults`, log output
- Unity projectをWorker cloneから開く場合の `Library/`, `Temp/`, `Logs/` 等生成物
- Package Manager / package cache
- ライセンス/認証
- 同一Unity installationを複数Workerが使えるか
- 複数Workerで同時にUnity Editorを起動した場合の競合
- EditModeとPlayModeのresource/time差
- test XML / Editor.log等をResultとしてどう回収するか
- timeout / hung Editor / crash recovery
- Unityのversion mismatch検出
- 2Dhakusura専用仕様をLocal Operations generic contractへ埋め込まない境界

このTaskでは2Dhakusura repositoryを変更しない。
Unity project testも実行しない。
installed Unityの存在確認やversion discoveryがread-onlyで安全なら実施してよい。

## 4. Desired architecture decision

調査後、少なくとも次を判断する。

### Question A

PREPAREを単にGit checkout準備ではなく、

`repository is ready for its declared validation capability`

まで拡張すべきか。

### Question B

Local Operationsにgenericなbounded Validation Toolを作るべきか。

例:

`run_repository_validation(...)`

ただし無制限shell runnerにはしない。

### Question C

Unityはgeneric validation adapterで扱うか、明示的なUnity adapter / toolにするか。

例:

`run_unity_tests(repository, branch, mode, ...)`

### Question D

Repositoryごとのvalidation command / required toolchainをどこで宣言するか。

候補を比較:

- repository-owned config
- Worker Pool config
- Local Operations hard-code
- Task Request
- other bounded registry

二重Authorityを作らない。

### Question E

dependency/networkが必要な場合、誰がenvironmentを準備するか。

- Codex sandbox
- Local Operations host
- pre-provisioned Worker
- shared immutable cache
- Human/manual

## 5. Evidence / probe policy

目的はCapabilityを理解することであり、sandboxを突破することではない。

Allowed:

- version / path discovery
- read-only environment inspection
- repository-local tests that do not require missing dependency install
- app-server public schema/config read
- existing Evidence reuse
- harmless temporary files under Task repository or OS temp when required

Do not:

- change firewall / sandbox / OS policy
- install system-wide software
- modify DevEnv / ProdEnv
- modify Worker Pool state intentionally
- invoke Production runtime tools
- run Worker recovery
- launch Unity project tests
- mutate another repository
- use Computer Use / GUI automation
- bypass network restrictions
- commit/push from Codex

## 6. Output

Create:

`work/gwi-0010/design/t005/GWI-0010-T005_CAPABILITY_MATRIX.md`

Include a table with at least:

| Capability | Observed Actor-local status | Evidence | Limitation | Recommended route |
|---|---|---|---|---|

Create:

`work/gwi-0010/design/t005/GWI-0010-T005_VALIDATION_ROUTING_DECISION.md`

Include:

- recommended ACTOR_LOCAL / HOST_EXECUTED / HUMAN_OR_EXTERNAL boundary
- proposed validation lifecycle
- Python/uv recommendation
- Unity recommendation
- generic vs Unity-specific runner decision
- environment/cache recommendation
- concurrency considerations
- next implementation Task(s), but do not create them automatically

Create final:

`work/gwi-0010/GWI-0010-T005_RESULT.md`

Result vocabulary:
- `PASS / ROUTING_DECISION_READY`
- `HOLD / EVIDENCE_INSUFFICIENT`
- `HOLD / CAPABILITY_CONFLICT`

PASS requires enough Evidence to choose the next bounded implementation direction.
It does NOT require all capabilities to be available.

## 7. Tests

This is an audit/design Task.

Do not require project full suite as a completion condition because inability to run it is part of the subject under investigation.

Run only probes/tests needed to support capability claims.

Record:
- command/probe
- exit status
- whether it mutated persistent state
- relevant stdout summary
- limitations

Do not treat missing dependency as test failure of the product under test; classify it as environment capability evidence.

## 8. Completion report

Final agent message:

`GWI-0010-T005 <PASS / ROUTING_DECISION_READY | HOLD / ...> — <one-line conclusion>`

Include in Result:
- capability summary
- most important newly found limitations
- Unity readiness conclusion
- recommended next implementation boundary
- whether T004 verification can be closed by that future path
