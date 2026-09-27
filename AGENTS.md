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

For ordinary Development work, do not require exact starting HEAD, Task Request blob pinning, or redundant local/remote revision equality checks unless the task explicitly needs reproducibility at that exact revision.

Use the requested repository and branch, update them normally, and block only when there is a concrete risk such as working in the wrong repository, overwriting unpersisted local work, or requiring destructive recovery.

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

Production:
- Plugin: `Local Operations`
- tunnel-client profile: `local-operations`
- runtime: `C:\Dev\ProdEnv`

Dev / Prod separation exists to avoid process, profile, and Plugin collision. Do not turn this into a customer-facing release-management system. Exact main-only, immutable-checkout, promotion, and revision-equality gates are not goals by themselves.

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

## Implementation principles

- Prefer bounded tools over generic shell exposure.
- Validate only the inputs needed to prevent concrete mistakes.
- Keep Repository-backed Task Requests as task instructions, but do not over-pin their revision during ordinary Development work.
- Chat must not need local absolute paths in the normal dispatch route.
- Local path / Worker Slot / concrete Codex cwd resolution is a Local Operations responsibility.
- One Worker Slot may be leased to only one active Task.
- Codex cwd must be the selected repository root, not the Worker root.
- Codex Desktop Project registration is optional UI organization, not Worker routing authority.
- Preserve local-only work when an operation fails.
- `DISPATCHED` means turn/start acknowledgement, not Task completion.
- Duplicate / uncertain dispatch must not create a second Task under the same identity.
- Worker FREE does not require returning to a default branch; the next PREPARE operation may switch to the requested branch.

## Personal-tool proportionality rule

This repository is a **personal local tool**, not a customer-facing production service. Design and review must use that risk profile.

Do not add or preserve operational complexity only because it would be conventional for a customer-facing production system. A guard, state, repository constraint, or verification step needs a concrete benefit for this repository.

Strong safeguards are justified when they directly prevent at least one of these concrete risks:

- secret / credential exposure
- destructive loss of local work or data
- dispatch to the wrong repository or branch
- duplicate or uncertain dispatch that can create duplicate work
- concurrent use of the same Worker Slot
- Dev / Prod Tunnel or process collision
- explicit authority escalation such as force push or merge without request

The following are **not sufficient reasons by themselves** for added machinery:

- conventional production deployment practice
- immutable-runtime or clean-checkout purity
- exact local/remote revision equality when no concrete safety property depends on it
- exact starting HEAD or Task Request blob pinning for ordinary Development work
- customer-facing availability / release-management assumptions
- extra evidence, gates, states, or recovery paths added only for theoretical completeness

Prefer observation and diagnostics over blocking when blocking does not prevent a concrete risk.

When an affected area next needs a real modification, simplify obsolete production-style constraints instead of adding another exception layer.

## Supported shell / environment verification

Repository-backed operational scripts are supported on **PowerShell 7+ (`pwsh.exe`)**.

Current Human-confirmed Worker settings:
- Worker root: `C:\Dev\WorkerRoot`
- Worker count: `5`
- Runtime config: `%LOCALAPPDATA%\LocalOperations\worker-pool.json`

Windows User environment changes require runtime restart before the existing MCP process can observe them.

See `work/gwi-0010/VALIDATION_KNOWLEDGE.md` for derived operational knowledge.

## Operational scripts

Repository-backed scripts include:

- `scripts/setup.ps1`
- `scripts/start-all.ps1`
- `scripts/restart-dev.ps1`
- `scripts/restart-prod.ps1`

Keep Dev / Prod process/profile isolation. Do not add release-management behavior to these scripts unless it prevents a concrete local failure.

## Verification

Implementation work should include focused unit/integration tests and one practical Development E2E for the changed behavior.

Do not multiply verification layers only to prove the same condition repeatedly.
