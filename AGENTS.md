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

If current `C:\Dev\local-mcp` contains any of these, exclude them during migration.

## Implementation principles

- Prefer bounded tools over generic shell exposure.
- Validate tool inputs server-side.
- Keep Repository-backed Task Request canonical.
- Chat must not need local absolute paths in the normal dispatch route.
- Local path / Worker Slot / concrete Codex cwd resolution is a Local Operations responsibility.
- One Worker Slot may be leased to only one active Task.
- Codex cwd must be the selected repository root, not the Worker root.
- Unexpected local state is quarantined, not silently reset or deleted.
- `DISPATCHED` means turn/start acknowledgement, not Task completion.
- Duplicate / uncertain dispatch must not create a second Task under the same identity.

## Verification

Implementation work must include bounded unit/integration tests and an E2E probe that does not execute a real GWI task.

Do not use GWI-0006 / GWI-0009 production tasks as implementation probes. They may be used only after the local implementation is accepted and Chat explicitly dispatches them.
