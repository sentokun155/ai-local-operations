# GWI-0010 Entry

Work Identity: `GWI-0010`  
Work Name: `Chat→Codex MCP Dispatch / Local Worker Pool`

## Tracking

Control Issue:
https://github.com/sentokun155/ai-dev-control/issues/16

Implementation Repository:
`sentokun155/ai-local-operations`

Dedicated branch:
`gwi-0010-ai-local-operations`

## Current task

`GWI-0010-T001 — Repository Migration and Fixed Local Worker Pool V0`

Task Request:
`work/gwi-0010/GWI-0010-T001_TASK_REQUEST.md`

## Current state

Status: **READY FOR IMPLEMENTATION**

The current local-only prototype under `C:\Dev\local-mcp` is an implementation input.

T001 must first audit that prototype and preserve already-working bounded behavior where compatible, while superseding the previous local-path / existing-workspace discovery assumption with the Human-confirmed fixed Worker Pool direction.

## Key boundaries

- This repository owns Local Operations host implementation.
- `ai-dev-control` owns GWI / routing / authority.
- `ai-operations-skills` remains owner of host-independent reusable workflow semantics.
- Worker Pool implementation does not authorize auto-dispatch policy.
- Worker cleanup must never silently discard local-only work.
