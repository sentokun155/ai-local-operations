# GWI-0010-T017 Task Request — Worker Python Runtime 診断とHost環境整理

## Work Identity

- Work Key: `GWI-0010`
- Work Name: `Chat→Codex MCP Dispatch / Local Worker Pool`
- GWI Authority: `sentokun155/ai-dev-control#16`

## Task Identity

- Task Key: `GWI-0010-T017`
- Task Name: `Worker Python Runtime 診断とHost環境整理`
- Task Stage: `Investigation / Host Maintenance`
- Logical Role: `Host Maintenance / Investigation Actor`
- Execution Surface: **Desktop Codex**
- Desired Task Title: `GWI-0010-T017 Worker Python Runtime 診断とHost環境整理 — 調査 / Host Maintenance`

## Repository / Branch

- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T017_TASK_REQUEST.md`

このTaskはLocal Operations Worker Poolへdispatchしない。
Desktop CodexをHost側調査・保守Actorとして使用する。

## Persistence / Delivery

`REMOTE_REFLECTION_REQUIRED`

Task-owned repository output（Result、必要なderived operational knowledge、必要ならbounded scripts/docs変更）は、self-verification後に通常commit / non-force push / remote HEAD確認 / changed-content re-readを行う。

Host-local environment mutationとRepository persistenceは別物として扱う。
Gitのremote reflectionがHost cleanupやACL/runtime変更のAuthorityを自動生成しない。

禁止:
- force push / force-with-lease
- rebase / reset / cleanによるRepository成果の暗黙破棄
- merge
- Production promotion
- secret値のcommit / report
- active Worker task stateの無断破棄

## Background / Problem

Host側では次が成立している。

- `C:\Dev\DevEnv\.venv\Scripts\python.exe`
- Python `3.13.14`
- Host user `DESKTOP-U5FJ9NG\sennn`
- T014–T016 candidateに対してHostからPython 3.13 testを実行可能

一方、Local OperationsからdispatchされたCodex Workerでは繰り返し:

- configured Python 3.13+ interpreterを起動できない
- `uv` cache access denied
- project dependenciesを満たすPython test環境に到達できない

ため、Worker自身ではrequired verificationを完了できずHumanがHost PowerShellから再実行している。

このTaskの目的は「一時的にHost Pythonを代用する」ことではない。

**Human操作なしでWorker verificationを再現可能にするため、Host / Worker Python実行環境の差を診断し、最小で安定したruntime構成を成立させる。**

同時に、過去の開発で残ったlocal artifactをinventoryし、安全性が証明できるものだけ整理する。

## Required Reads

最低限:

- Repository root `AGENTS.md`
- `README.md`
- `work/gwi-0010/VALIDATION_KNOWLEDGE.md`
- `work/gwi-0010/GWI-0010-T004_RESULT.md`
- `work/gwi-0010/GWI-0010-T014_TASK_REQUEST.md`
- `work/gwi-0010/GWI-0010-T015_TASK_REQUEST.md`
- `work/gwi-0010/GWI-0010-T016_TASK_REQUEST.md`
- `src/local_mcp/dispatch.py`
- `src/local_mcp/worker_pool.py`
- `pyproject.toml`
- `.python-version`
- `uv.lock`
- runtime scripts under `scripts/`

GWI Current Stateは`sentokun155/ai-dev-control#16`から確認する。

## Hard Preservation Boundary

このTaskでは、以下を**削除・reset・clean・release・overwriteしない**。

- `C:\Dev\WorkerRoot\worker-01\...` — T013
- `worker-02` — T014 / QUARANTINED
- `worker-03` — T014 failed candidate
- `worker-04` — T015 failed candidate
- `worker-05` — T016 failed candidate

これらはread-only inventory対象にはできるが、cleanup対象ではない。

また:

- `C:\Dev\ProdEnv` はread-only inspectionのみ。
- Production Tunnel/profile/runtimeをrestart・rewriteしない。
- `CONTROL_PLANE_API_KEY`、Codex credentials、Tunnel credentials、token値を表示・保存しない。
- Pipeline descriptor / bearer token等Unity credentialを読まない。
- Windows security設定を広範囲に緩和しない。

## Phase A — Diagnose / Inventory

Phase Aでは原則read-only。
cleanupやACL変更を先に行わない。

### A01 — Record actual execution identities

最低限、次を比較する。

Host:
- Windows user / SID
- shell executable/version
- Python executable/version
- uv executable/version
- relevant env path **names/paths only; secret values excluded**

Worker:
- Windows user / SID（既知: `CodexSandboxOffline`を実測で再確認）
- effective HOME / USERPROFILE / LOCALAPPDATA / APPDATA
- Python discovery result
- uv discovery result
- filesystem access behavior

### A02 — Diagnose Host Python 3.13 access

調査対象:

`C:\Dev\DevEnv\.venv\Scripts\python.exe`

確認:

- executable ACL
- parent directoriesのtraverse/read/execute ACL
- Python DLL / stdlib / site-packages access
- Worker identityから起動不能になる最初のfailure point
- access deniedなのか、sandbox/policy/process creation制約なのか、依存DLL/pathなのか

ACLを見る場合、secretや無関係ユーザ情報をResultへ過剰記録しない。

### A03 — Diagnose uv/cache failure

`uv`について:

- executable path/version
- effective cache directory
- cache ownership / ACL
- Worker identityでread/write/createできるか
- project-local / global cache依存
- access deniedのexact filesystem boundary

cache pathは実測から解決し、一般論で決め打ちしない。

### A04 — Compare candidate runtime topologies

最低限、以下を比較する。

1. **Host DevEnv shared**
   - Workerが `C:\Dev\DevEnv\.venv` を共有
2. **Per-Worker environment**
   - 各Worker clone/runtime内に独立venv/cache
3. **Dedicated Worker Runtime**
   - 例: Host管理のWorker専用Python/uv runtime + Worker-safe cache
   - pathは調査結果から決定し、例をそのまま採用しない

比較軸:
- reliability
- ACL simplicity
- dependency consistency
- concurrent Worker use
- disk usage
- update/maintenance cost
- cleanup/reproducibility
- Local Operationsからの自動検証適合性

最も単純で安定した構成を選ぶ。
personal toolであるためproduction-style machineryを追加しない。

### A05 — Local environment inventory

以下を調査対象に含める。

Known:
- `C:\Dev\DevEnv`
- `C:\Dev\ProdEnv`（read-only）
- `C:\Dev\WorkerRoot`
- legacy migration input `C:\Dev\local-mcp`

Discover:
- obsolete / duplicate Python venvs
- uv caches
- stale Local Operations logs/temp/runtime artifacts
- stale Codex projectless workspaces
- obsolete checkout / workspace candidates
- other clearly related local artifacts found from current config/history

Codex workspace path等は設定・filesystem evidenceから発見する。推測pathを削除しない。

各candidateを必ず次のいずれかへ分類:

- `ACTIVE_REQUIRED`
- `OBSOLETE_SAFE_TO_REMOVE`
- `UNRESOLVED_PRESERVE`

分類根拠も記録する。

### A06 — Cleanup safety criteria

`OBSOLETE_SAFE_TO_REMOVE` にできるのは、少なくとも次を説明できる場合。

- 現在のruntime/config/Taskから参照されていない
- Gitで必要sourceの唯一copyではない
- active Worker task/evidenceではない
- credentials/evidenceの唯一copyではない
- 再生成可能、または明示的に不要
- 削除してもDev/Prod/Workerの現在状態を壊さない

不明なら `UNRESOLVED_PRESERVE`。

## Phase B — Bounded Remediation / Cleanup

Phase Aの結果を先にTask Resultへ記録してから実行する。

### B01 — Python runtime remediation

Phase Aで選定したtopologyを最小範囲で実現する。

目標:

**少なくとも1 Worker contextから、人間のHost PowerShell操作なしにPython 3.13+でrepository testsを起動できること。**

許可される候補:
- Worker-safe dedicated Python/uv environmentの準備
- bounded ACL adjustment
- Worker-specific cache/config path
- repository/local runtime scripts/configの小変更

禁止:
- Users/drive全体への広範囲ACL緩和
- Everyone FullControl等
- security boundaryの無効化
- Production環境の変更
- arbitrary generic shell MCP exposure

ACL変更を選ぶ場合は、対象path / principal / required rightを最小化し、変更前後を記録する。

### B02 — Safe cleanup

`OBSOLETE_SAFE_TO_REMOVE` のみcleanup可能。

cleanup前に対象一覧をResultへ固定する。

cleanup後:
- path不存在またはexpected reduced stateを確認
- active runtimeが壊れていないことを確認
-削減した概算容量を報告可能なら報告

`UNRESOLVED_PRESERVE` は触らない。

### B03 — Repository updates

調査で恒久的に有用な知見は、必要なら:

- `work/gwi-0010/VALIDATION_KNOWLEDGE.md`
- README
- bounded runtime/setup script
- config example

へ反映してよい。

ただしmachine-specific secret/path detailを不要にCanonical化しない。

## Verification

### V01 — Host baseline

Hostで:
- Python 3.13+
- supported pwsh 7+
- current DevEnv integrity

を確認。

### V02 — Worker Python proof

Desktop Codexから、Host-side tooling / Worker identity contextを使い、少なくとも1つのWorker execution contextで次を実証する。

- Python `>=3.13` 起動
- repository dependencies import
- harmless focused test実行

active T013–T016 Workerを変更しない方法を使う。
既存active Worker Slotを再利用する必要がある場合はSTOPし、別のfixture/sandbox routeを準備する。

### V03 — Local Operations relevant tests

Repository変更があれば、対象に応じてfocused testsを実行。

### V04 — Cleanup verification

削除した各artifactについて、active referenceが失われていないことを確認。

### V05 — No secret exposure

Result / diff / commitにsecret値やcredential materialがないことを確認。

## Result / Evidence

作成:

`work/gwi-0010/GWI-0010-T017_RESULT.md`

最低限:

- Verdict
- Host / Worker execution identity comparison
- Python failure root cause
- uv/cache failure root cause
- chosen Worker runtime topology + alternatives
- inventory table:
  - path/category
  - classification
  - reason
  - action taken
- cleanup results
- Worker Python 3.13 verification
- repository changes
- unresolved items
- final commit / remote HEAD

Verdict:

- `PASS / WORKER_PYTHON_RUNTIME_AND_HOST_CLEANUP_READY`
- `HOLD / PYTHON_ROOT_CAUSE_UNRESOLVED`
- `HOLD / WORKER_RUNTIME_VERIFICATION_INCOMPLETE`
- `HOLD / CLEANUP_SAFETY_UNRESOLVED`

Cleanup未実施でもPython runtime goalが成立し、cleanup candidatesがすべて安全に`ACTIVE_REQUIRED / UNRESOLVED_PRESERVE`へ分類された場合、cleanupしなかったこと自体はFAILにしない。

## Completion Boundary

PASSは以下を意味する:

- HumanがPowerShellから毎回testを代理実行しなくてもよいWorker Python execution pathが実証された
- local cleanupが安全に限定された
- remaining itemsが明示された

PASSは次を意味しない:

- T013–T016 failed candidate disposal完了
- Worker Pool FREE化
- Unity lifecycle fix完了
- Production更新
- GWI-0010 Global Acceptance

次はController Tooling / failed-candidate dispositionとWorker Pool recoveryへ戻す。
