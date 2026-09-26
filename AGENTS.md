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
