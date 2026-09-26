# AGENTS.md

## Repository purpose

This repository owns the host-specific implementation of Personal Local Operations.

Do not move Global Work lifecycle, Human Decision policy, auto-dispatch policy, or generic reusable AI-development workflow authority into this repository.

## Authority

For GWI-0010:

1. Human explicit direction
2. `sentokun155/ai-dev-control#16`
3. Current committed Task Request under `work/gwi-0010/`
4. Current repository source/tests
5. Historical local implementation under `C:\Dev\local-mcp`
6. Chat summaries / execution self-report

Historical local files are implementation input, not authority over the Repository-backed Task Request.

## Repository operation

Current GWI branch:

`gwi-0010-ai-local-operations`

Use normal non-force Git operations.

Do not:
- force push / force-with-lease
- delete branches/tags
- change remote/upstream
- modify default branch settings
- merge PRs without explicit authority
- discard unexpected local modifications
- use destructive cleanup as a recovery shortcut

If expected remote / branch / Task Request identity does not match, stop and report HOLD.

## Runtime topology

Canonical source is this GitHub repository.

Development runtime checkout:

`C:\Dev\DevEnv`

Production runtime checkout:

`C:\Dev\ProdEnv`

Worker Slot clones of `ai-local-operations` are implementation workspaces only. Do not run the Production or Development MCP directly from a leased Worker Slot.

Development:
- Plugin: `Local Operations Dev`
- tunnel-client profile: `local-operations-dev`
- runtime: `C:\Dev\DevEnv`
- separate Tunnel ID from Production

Production:
- Plugin: `Local Operations`
- tunnel-client profile: `local-operations`
- runtime: `C:\Dev\ProdEnv`
- separate Tunnel ID from Development

Do not share one Tunnel ID between Dev and Prod.

## Secret / runtime boundary

Never commit:

- API keys / tunnel keys / GitHub tokens
- Codex credentials
- `.env`
- local dispatch ledger
- Worker Slot runtime database/state
- managed repository clones
- local logs / caches / temp files
- virtual environments

Standard tunnel runtime credential is read from the Windows User environment variable:

`CONTROL_PLANE_API_KEY`

Scripts must not accept the key as a command-line argument, print it, or persist it into the repository.

If current `C:\Dev\local-mcp` contains secrets/runtime state, exclude them during migration.

## Implementation principles

- Prefer bounded tools over generic shell exposure.
- Validate tool inputs server-side.
- Keep Repository-backed Task Request canonical.
- Chat must not need local absolute paths in the normal dispatch route.
- Local path / Worker Slot / concrete Codex cwd resolution is a Local Operations responsibility.
- One Worker Slot may be leased to only one active Task.
- Codex cwd must be the selected repository root, not the Worker root.
- Codex Desktop Project registration is optional UI organization, not Worker routing authority.
- Unexpected local state is quarantined, not silently reset or deleted.
- `DISPATCHED` means turn/start acknowledgement, not Task completion.
- Duplicate / uncertain dispatch must not create a second Task under the same identity.
- Candidate revisions are validated through the Development runtime before Production promotion.


## Personal-tool proportionality rule

This repository is a **personal local tool**, not a customer-facing production service. Design and review must use that risk profile.

Do not add or preserve operational complexity only because it would be conventional for a customer-facing production system. A guard, state, promotion gate, repository constraint, or verification step needs a concrete benefit for this repository.

Strong safeguards are justified when they directly prevent at least one of these concrete risks:

- secret / credential exposure
- destructive loss of local work or data
- dispatch to the wrong repository / branch / Task identity
- duplicate or uncertain dispatch that can create duplicate work
- concurrent use of the same Worker Slot
- Dev / Prod Tunnel or process collision that causes the wrong local service to be used
- explicit authority escalation beyond the requested local operation

The following are **not sufficient reasons by themselves** for added machinery:

- conventional production-deployment practice
- immutable-runtime or clean-checkout purity
- exact local/remote revision equality when no concrete safety property depends on it
- customer-facing availability / release-management assumptions that do not apply to this personal tool
- extra evidence, gates, states, or recovery paths added only for theoretical completeness

Prefer observation and diagnostics over blocking when blocking does not prevent a concrete risk. In particular, Development runtime dirtiness or branch choice must not be treated as an error merely to emulate production deployment discipline.

### Avoid churn; fix comprehensively on the next relevant change

Do **not** immediately rewrite already-working code solely because an existing mechanism is now judged over-engineered. Rework plus repeated verification has a cost.

When the affected area next requires a real modification, the same bounded change must:

1. reassess the existing mechanism against this proportionality rule;
2. remove or relax unnecessary production-style constraints in that area rather than layering another exception on top;
3. keep only safeguards with an explicit concrete risk they mitigate;
4. update source, documentation, and tests together so obsolete behavior is not left as an accidental contract;
5. verify the resulting behavior once at the actual supported runtime boundary.

Do not perpetuate an unnecessary mechanism merely because it already exists. Do not create a separate cleanup task unless the mechanism itself is causing current harm or the Human explicitly requests one.

## Supported shell / environment verification

Repository-backed operational scripts are supported on **PowerShell 7+ (`pwsh.exe`)**.

Do not claim Windows operational compatibility from a `pwsh` test as if it also verified Windows PowerShell 5.1 (`powershell.exe`). Windows PowerShell 5.1 is not a supported Local Operations operational shell.

When runtime compatibility matters, record the concrete environment:
- OS
- shell executable
- shell version
- PSEdition
- runtime checkout
- Tunnel profile
- relevant encoding assumption

A Human-observed Windows PowerShell 5.1 failure showed that UTF-8 BOM-less scripts containing non-ASCII diagnostics can be mis-decoded before any API-key or Worker-Pool validation executes. Treat parser failure, Worker configuration HOLD, and Tunnel/MCP runtime failure as distinct failure classes.

Current Human-confirmed Worker settings:
- Worker root: `C:\Dev\WorkerRoot`
- Worker count: `5`
- Runtime config: `%LOCALAPPDATA%\LocalOperations\worker-pool.json`

Windows User environment changes require runtime restart before the existing MCP process can observe them.

See `work/gwi-0010/VALIDATION_KNOWLEDGE.md` for derived operational knowledge.

## Operational scripts

Repository-backed scripts must include:

- `scripts/setup.ps1`
- `scripts/start-all.ps1`
- `scripts/restart-dev.ps1`
- `scripts/restart-prod.ps1`

Scripts must preserve Dev / Prod isolation and must not use destructive Git cleanup to recover unexpected runtime checkout state.

## Verification

Implementation work must include bounded unit/integration tests and an E2E probe that does not execute a real GWI task.

Do not use GWI-0006 / GWI-0009 production tasks as implementation probes. They may be used only after the local implementation is accepted and Chat explicitly dispatches them.
