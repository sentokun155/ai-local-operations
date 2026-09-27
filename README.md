# ai-local-operations

Personal Local Operations / Local MCP implementation repository. This repository owns the local host implementation for the personal Local Operations Plugin. GWI lifecycle, Human Decision policy, auto-dispatch policy, and host-independent workflow authority remain with their respective repositories.

## Canonical source and runtime checkouts

`sentokun155/ai-local-operations` is the canonical source. `C:\Dev\DevEnv` is the Development runtime checkout. `C:\Dev\ProdEnv` is a separate Production runtime checkout. Dev / Prod separation prevents local profile and process collisions; it is not a release-management system. A Worker Slot's clone is an implementation workspace; the MCP runtime never starts from a Worker Slot.

Development verification uses the `Local Operations Dev` profile and the requested repository branch. Production changes are outside T002.

## Local prototype audit and migration

The pre-repository prototype at `C:\Dev\local-mcp` contained `server.py`, `src/local_mcp/dispatch.py`, `tests/test_dispatch.py`, `tests/test_live_app_server.py`, `pyproject.toml`, `.python-version`, `uv.lock`, and its operational README. The MCP `ping` / `ping2` tools, app-server adapter, model and reasoning validation, `workspace-write` dispatch, DispatchReceipt, retry ledger, and uncertainty guard were retained and extended here. Dispatch reads the current Task Request at its repository-relative path without pinning its Git blob or starting revision.

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

`start-all.ps1` starts each environment independently, skips an already-running profile, and checks `/readyz`. A failure in one does not stop the other. `restart-dev.ps1` operates only on DevEnv and the Development profile; it allows a dirty development checkout and uses an ordinary fast-forward update if possible. A conflict stops the restart and preserves local edits. `prepare_production_runtime(branch)` prepares the fixed ProdEnv checkout on the requested branch, holds when that checkout has local changes, points the Production profile at ProdEnv, and restarts it after readiness checks. Production branch selection is not fixed to `main`; Worker leases do not block a Production restart. The scripts never use `reset --hard`, `clean`, force push, or branch deletion.

Restarting the Development Tunnel can stop its child MCP/app-server process. Production runtime restarts are independent of Worker leases.

After changing MCP tool schemas, restart the corresponding Tunnel and refresh the connected Local Operations tool catalog in the client. A task can retain an older cached tool list; confirm the new schema in a fresh task if the current list stays stale.

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

States include `FREE`, `LEASED`, `DIRTY`, and `QUARANTINED`. Only `FREE` slots can be leased. PREPARE checks the selected clone's remote identity and local changes, fetches `origin`, then checks out or fast-forwards the requested branch. It does not inspect sibling clones or restore a default branch on release. A wrong remote, unknown branch, uncommitted local changes, or a branch that cannot be updated with a fast-forward stays visible for recovery; no local work is discarded. The app-server `cwd` is the selected target repository root.

`finalize_codex_task` requires `worker_id`, `work_identity`, and `task_key`. It reads the exact dispatched turn and requires `completed`, stages non-ignored changes, blocks common credential files/values, commits with the Task identity, and pushes normally to `origin` on the requested branch. Push failure leaves the local commit and lease intact. With no changes, it returns the Result without making a commit. A clean target clone becomes `FREE` on its current branch; an unclean target remains leased. `recover_quarantined_worker(worker_id)` applies the same Git persistence checks to one quarantined Worker and leaves it quarantined when its turn is incomplete or persistence fails.

## MCP tools and dispatch contract

### Repository implementation and Controller follow-up

Codex is the repository implementation actor: normal dispatch limits its work to
source/docs/tests and Task-owned Results inside the resolved (normally leased)
repository root. Changes remain in the worktree. Local Operations
`finalize_codex_task` owns Git commit and normal push after completion.
Controller Chat initiates host/runtime actions; `recover_quarantined_worker` and
`prepare_production_runtime` are Controller-facing runtime tools. Tunnel/profile/
process restarts and local runtime promotion also belong to Controller follow-up.
A Task Request mentioning these actions does not grant the implementation actor
authority to execute them.

This boundary is **contract-only, not Host-enforced tool filtering**. The dispatch
prompt states it on every turn, including retries on an existing thread.
`workspace-write` constrains workspace operations; it does not establish that MCP
or other external tools are hidden. Codex has individual MCP/config and Plugin
controls, but this route has not verified complete external-tool exposure control
(see [T004 Result](work/gwi-0010/GWI-0010-T004_RESULT.md)). No tool-name blacklist
is treated as a security boundary.

When runtime work is needed, Codex records explicit Controller follow-up and a
Result locator in its Result and final message. The existing finalize response
returns `finalAgentMessage` and `resultLocators`; Controller reads these and decides
the next action. No action graph or automatic execution is inferred from prose.
Automatic normal Chat callbacks and new Chat creation are outside GWI-0010.
Scheduler, next-Task selection, and Controller lifecycle are Management Plane
candidates owned by GWI-0009.

Bounded tools:

- `ping` → `LOCAL_MCP_OK`
- `ping2` → `LOCAL_MCP_OK2`
- `dispatch_codex_task`
- `get_worker_pool_status`
- `finalize_codex_task`
- `recover_quarantined_worker`
- `prepare_production_runtime`

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

Dispatch validates the configured repository identity, requested branch, current Task Request file path, model, and reasoning effort. Commit and blob values in the receipt are diagnostic only. Codex receives `workspace-write`; dispatch grants no commit, push, merge, force-push, publication, deployment, or destructive-cleanup authority. Thread names remain `Task Key + Task Name`.

`DISPATCHED` means the app-server acknowledged `turn/start`, not that the task completed. The receipt includes Worker ID, selected repository root for diagnosis, thread/turn IDs, and informational commit/blob values. Repeating `work_identity + task_key` returns the accepted receipt without another turn. Uncertain outcomes block a second task. Explicit turn rejection can retry on its existing thread and keeps the Worker leased.

`get_worker_pool_status` reports configured slot state without clone contents or credentials. After Codex completes, `finalize_codex_task` returns the final agent message, changed paths, commit SHA when present, and push status, then frees a clean Worker. `recover_quarantined_worker` returns a quarantined Worker to `FREE` after confirming a clean clone or successfully saving and pushing its completed task. `prepare_production_runtime` returns `READY` only after Production `/readyz` responds successfully. These tools do not send an automatic callback to an existing ChatGPT chat.

Set `LOCAL_OPERATIONS_CODEX_EXECUTABLE` to the Codex executable path when it is not on `PATH`. If unset, Local Operations uses `shutil.which("codex")`.

## Verification

Run the bounded unit/integration suite:

```powershell
uv run --locked python -m unittest discover -s tests -v
```

The Development Plugin probe uses a harmless committed probe branch and Result file, never a GWI-0006/GWI-0009 task. T002's concrete probe and outcome are recorded in `work/gwi-0010/ENTRY.md`.

The opt-in automated app-server integration test creates a disposable local fixture repository, dispatches a harmless Result request, then checks finalization, push, and Worker release. It uses the installed Codex app-server and does not call the Dev Plugin connector:

```powershell
$env:LOCAL_MCP_RUN_LIVE_APP_SERVER_TESTS = "1"
uv run --locked python -m unittest discover -s tests -p test_live_app_server.py -v
```

The automated fixture clone is below the OS temporary directory. The Development Plugin probe uses a configured Worker and leaves its remote probe branch available for inspection.

## Troubleshooting

- `WORKER_POOL_NOT_CONFIGURED`: set the two local Worker Pool variables and use the documented JSON format.
- `WORKER_REPOSITORY_UNAVAILABLE`: run bounded bootstrap and check the configured clone URL/identity.
- `WORKER_REPOSITORY_DIRTY` / `WORKER_BRANCH_DIVERGED`: inspect and preserve local state; do not reset or clean.
- `NO_FREE_WORKER`: inspect `get_worker_pool_status`; finalize completed work or resolve quarantined slots deliberately.
- `DISPATCH_OUTCOME_UNKNOWN`: inspect the saved Codex thread; never retry the same key as a new task.
- `CODEX_UNAVAILABLE`: Codex CLI/app-server must be available to the runtime account.
- Tunnel profile mismatch: run `tunnel-client doctor --profile <profile> --explain`; confirm its MCP command uses its DevEnv/ProdEnv path and the Tunnel IDs differ.

Tunnel runtime data, local config, managed clones, Codex credentials, and task output are host-local state and are never committed.
