# ai-local-operations

Personal Local Operations / Local MCP implementation repository. This repository owns the local host implementation for the personal Local Operations Plugin. GWI lifecycle, Human Decision policy, auto-dispatch policy, and host-independent workflow authority remain with their respective repositories.

## Canonical source and runtime checkouts

`sentokun155/ai-local-operations` is the canonical source. `C:\Dev\DevEnv` is the Development runtime checkout for candidate verification. `C:\Dev\ProdEnv` is the Production runtime checkout and runs accepted `main` only. A Worker Slot's `ai-local-operations` clone is an implementation workspace; the MCP runtime never starts from a Worker Slot.

Promotion flow: implement and commit in a Worker checkout, non-force push, fast-forward DevEnv to the candidate branch, verify through Development, then after acceptance/merge fast-forward ProdEnv to `main`. The scripts require clean checkouts and fast-forward updates. Production scripts refuse a non-`main` branch. T001 does not promote its candidate to Production.

## Local prototype audit and migration

The pre-repository prototype at `C:\Dev\local-mcp` contained `server.py`, `src/local_mcp/dispatch.py`, `tests/test_dispatch.py`, `tests/test_live_app_server.py`, `pyproject.toml`, `.python-version`, `uv.lock`, and its operational README. The MCP `ping` / `ping2` tools, app-server adapter, model and reasoning validation, `workspace-write` dispatch, DispatchReceipt, retry ledger, uncertainty guard, and committed Task Request blob validation were retained and extended here.

The prototype's `.venv`, Python cache, and machine-local runtime data are not source. No API key, tunnel credential, Codex credential, `.env`, dispatch SQLite database, Worker clone, log, cache, or temporary Evidence is committed. The old `C:\Dev\local-mcp` tree is migration input only.




## Design proportionality

This is a personal local tool. Development / Production naming separates the experimental local runtime from the normally used local runtime; it does **not** imply customer-facing deployment discipline.

Operational guards should exist only for concrete local risks such as credential exposure, destructive data loss, wrong/duplicate dispatch, Worker concurrency, or Tunnel/process collision. Production-style immutability, clean-checkout enforcement, strict promotion machinery, or exact revision equality are not goals by themselves.

If an existing mechanism is later found to be unnecessarily strict, do not create churn only to remove it. On the next real modification to that area, simplify it comprehensively, update tests/docs with the same change, and verify the supported runtime once.

## Supported operational shell

Local OperationsのRepository-backed operational scriptsは **PowerShell 7+ (`pwsh.exe`)** を正式な実行環境とします。

Windows PowerShell 5.1 (`powershell.exe`) は正式サポート対象ではありません。T001後の実環境確認で、UTF-8 BOMなしのscriptに含まれる日本語文字列がWindows PowerShell 5.1で誤decodeされ、`_runtime-common.ps1` のParserErrorへ連鎖することを確認しました。これはAPI keyやWorker Pool設定の問題ではありません。

PowerShell関連のRepository testsも `pwsh` を使用しているため、Humanの手動運用も同じshellへ合わせます。

確認:

```powershell
$PSVersionTable.PSVersion
$PSVersionTable.PSEdition
```

期待値はPowerShell 7以上かつ `PSEdition = Core` です。

「Windowsで検証済み」だけでは互換性を主張しません。runtime依存の検証ではOSに加えてshell executable / version / PSEditionを記録します。

詳細なderived knowledgeは [`work/gwi-0010/VALIDATION_KNOWLEDGE.md`](work/gwi-0010/VALIDATION_KNOWLEDGE.md) を参照してください。

## Development and Production Tunnel profiles

| Environment | Plugin | Profile | Runtime checkout | Health/UI port |
|---|---|---|---|---:|
| Development | `Local Operations Dev` | `local-operations-dev` | `C:\Dev\DevEnv` | 8081 |
| Production | `Local Operations` | `local-operations` | `C:\Dev\ProdEnv` | 8080 |

Each profile must have a different Tunnel ID. Profile YAML references `env:CONTROL_PLANE_API_KEY`; it never stores the key value. Set the restricted Runtime key in the Windows **User** environment as `CONTROL_PLANE_API_KEY`. `scripts/setup.ps1` checks for it without displaying the value. The same restricted key may be used by both profiles.

Run from `C:\Dev\DevEnv`:

```powershell
./scripts/setup.ps1
./scripts/start-all.ps1
```

Setup validates runtime checkouts and local tools; it does not start either Tunnel. To create profiles, provide the distinct Tunnel IDs explicitly:

```powershell
./scripts/setup.ps1 -ConfigureProfiles -DevTunnelId <dev-id> -ProdTunnelId <prod-id>
```

Replacing an existing profile requires the separate `-ReplaceExistingProfiles` switch. Setup writes only Tunnel profile configuration and the environment-variable reference; it never writes the API key value. Verify profiles with `tunnel-client doctor --profile local-operations-dev --explain` and `tunnel-client doctor --profile local-operations --explain`.

The current Production checkout is intentionally left on accepted `main` while this candidate remains unmerged. If `main` does not yet contain `server.py` and the Python project, Production startup will HOLD until an accepted runtime is available.

`start-all.ps1` starts each environment independently, skips an already-running profile, and checks `/readyz`. A failure in one does not stop the other. `restart-dev.ps1` operates only on DevEnv and the Development profile. `restart-prod.ps1` operates only on ProdEnv and Production `main`. Restarts stop when a Worker lease is active. The scripts never use `reset --hard`, `clean`, force push, or branch deletion.

Finish and release tasks before restarting. Legacy explicit-path tasks are not represented in the Worker Pool lease table and must also be checked in Codex. A Tunnel restart can stop its child MCP/app-server process.

After changing MCP tool schemas: restart the corresponding Tunnel; in ChatGPT Web open its Plugin and choose **Manage → Update tools**; confirm the tool list and use a new chat if it remains stale.

Windows User environment variable changes are inherited only by newly started processes. After changing `CONTROL_PLANE_API_KEY`, `LOCAL_OPERATIONS_WORKER_ROOT`, or `LOCAL_OPERATIONS_WORKER_POOL_CONFIG`, open a new `pwsh` session as needed, restart the target Tunnel/MCP runtime, then verify the effective state through the MCP tools.

## Worker Pool V0

Copy and edit [`config/worker-pool.example.json`](config/worker-pool.example.json) to `%LOCALAPPDATA%\LocalOperations\worker-pool.json`.

Current Human-confirmed local values:

```text
LOCAL_OPERATIONS_WORKER_POOL_CONFIG=%LOCALAPPDATA%\LocalOperations\worker-pool.json
LOCAL_OPERATIONS_WORKER_ROOT=C:\Dev\WorkerRoot
workerCount=5
```

These are machine-local runtime settings. The repository keeps the example/schema, not the machine-local config file itself.

Machine-specific paths are not stored in the repository config. `workerCount` is bounded from 1 to 16. Managed repositories are bounded to 32 entries; each entry supplies `identity` (`owner/name`), `cloneUrl`, and `defaultBranch`. URLs with embedded credentials are rejected. The example lists the repositories owned or used in this workflow; edit it to match the managed set and verified default branches.

Worker layout is `<worker-root>/worker-01/<repository-directory>`. Every configured repository has an independent clone in every slot. Unique repository basenames are used; collisions use `owner--name`. Normal dispatch never creates clones. Bootstrap only fills absent paths; an existing wrong or dirty path is preserved and quarantined.

Bootstrap and status are local admin commands, not MCP shell tools:

```powershell
uv --directory C:\Dev\DevEnv run --locked python -m local_mcp.admin bootstrap
uv --directory C:\Dev\DevEnv run --locked python -m local_mcp.admin status
```

The local SQLite file `%LOCALAPPDATA%\LocalOperations\dispatch-ledger.sqlite3` stores dispatch deduplication and Worker lease state; Git ignores it. SQLite `BEGIN IMMEDIATE` makes slot selection atomic across server processes. A lease is recorded before repository preparation. The dispatch ledger and Worker state use separate table updates in the same database; failures preserve duplicate safety and quarantine uncertain repository state.

States are `FREE`, `LEASED`, `DIRTY`, and `QUARANTINED`. Only `FREE` slots can be leased. Before dispatch, Local Operations checks every managed clone's identity and clean state, fetches the requested repository, and checks out or fast-forwards only the requested remote branch. Divergence, wrong remote, unknown branch, tracked changes, or untracked files cause HOLD/quarantine without deleting data. The app-server `cwd` is the selected target repository root, never the Worker root or a sibling repository.

Release requires the exact Worker/Task lease, explicit completion confirmation, and an app-server `thread/read` result proving the acknowledged turn completed or the rejected thread has no active turn. It checks all managed repositories, verifies the requested branch is reflected on its remote, and fast-forwards the target to its configured default branch. A local-only commit, dirty state, remote mismatch, or changed sibling repository quarantines the slot. Uncertain dispatch outcomes remain leased. Release never resets, cleans, deletes branches, or force-pushes.

## MCP tools and dispatch contract

Bounded tools:

- `ping` → `LOCAL_MCP_OK`
- `ping2` → `LOCAL_MCP_OK2`
- `dispatch_codex_task`
- `get_worker_pool_status`
- `release_codex_worker`

Before migration, logical dispatch used a registered checkout or needed a local path. The normal fixed-pool route now takes only:

```text
work_identity
task_key
task_name
repository                 # logical owner/name
branch
task_request_locator       # repository-relative
model?
reasoning_effort?
```

`repository_path` and absolute-path inputs remain local diagnostic overrides. Chat does not need them. There is no generic `run_shell` tool.

Dispatch validates repository identity, branch, tracked and committed Task Request blob, repository commit, model, and reasoning effort. The manifest pins these identities. Codex receives `workspace-write`; dispatch grants no merge, force-push, publication, deployment, or destructive-cleanup authority. Thread names remain `Task Key + Task Name`.

`DISPATCHED` means the app-server acknowledged `turn/start`, not that the task completed. The receipt includes Worker ID, selected repository root for diagnosis, thread/turn IDs, and pinned commit/blob. Repeating `work_identity + task_key` returns the accepted receipt without another turn. Uncertain outcomes block a second task. Explicit turn rejection can retry on its existing thread and keeps the Worker leased. A clean pre-dispatch HOLD releases the lease only after safe baseline restoration.

`get_worker_pool_status` reports configured slot state without clone contents or credentials. `release_codex_worker` requires `worker_id`, `work_identity`, `task_key`, and `confirm_completed=true`; the server verifies turn completion and repository/remote cleanliness before making the slot FREE.

## Verification

Run the bounded unit/integration suite:

```powershell
uv run --locked python -m unittest discover -s tests -v
```

The live Development E2E uses a temporary bare fixture repository, dispatches a read-only synthetic Task Request to the installed Codex app-server, waits for completion, confirms the Worker stayed clean, and calls the safe release tool. It does not use a GWI-0006/GWI-0009 task:

```powershell
$env:LOCAL_MCP_RUN_LIVE_APP_SERVER_TESTS = "1"
uv run --locked python -m unittest discover -s tests -p test_live_app_server.py -v
```

The probe uses a disposable clone below the OS temporary directory and removes it when the test exits.

## Troubleshooting

- `WORKER_POOL_NOT_CONFIGURED`: set the two local Worker Pool variables and use the documented JSON format.
- `WORKER_REPOSITORY_UNAVAILABLE`: run bounded bootstrap and check the configured clone URL/identity.
- `WORKER_REPOSITORY_DIRTY` / `WORKER_BRANCH_DIVERGED`: inspect and preserve local state; do not reset or clean.
- `NO_FREE_WORKER`: inspect `get_worker_pool_status`; release completed work or resolve quarantined slots deliberately.
- `DISPATCH_OUTCOME_UNKNOWN`: inspect the saved Codex thread; never retry the same key as a new task.
- `CODEX_UNAVAILABLE`: Codex CLI/app-server must be available to the runtime account.
- Tunnel profile mismatch: run `tunnel-client doctor --profile <profile> --explain`; confirm its MCP command uses its DevEnv/ProdEnv path and the Tunnel IDs differ.

Tunnel runtime data, local config, managed clones, Codex credentials, and task output are host-local state and are never committed.
