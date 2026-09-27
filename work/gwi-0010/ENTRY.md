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

Draft PR:
https://github.com/sentokun155/ai-local-operations/pull/1

## Current task

`GWI-0010-T002 — Codex Result Persistence and Intake V0`

Task Request:
`work/gwi-0010/GWI-0010-T002_TASK_REQUEST.md`

## Current state

Status: **T002 READY FOR IMPLEMENTATION**

T001 established the Repository-backed Local Operations implementation, fixed Worker Pool, logical repository routing, Codex app-server dispatch, safe release/quarantine behavior, Dev/Prod runtime separation, and bounded operational scripts.

Human runtime probes after T001 established additional facts that T002 must absorb:

- app-server-created work appears as Codex Tasks rather than ChatGPT chats;
- direct ChatGPT chat-list / chat-send capability is absent from the observed Codex Task tool catalog;
- Codex subagent capability is available (`spawn_agent`, `wait_agent`, `send_message` observed; PROBE-004 PASS);
- Codex can edit the leased worktree under `workspace-write`, but the observed Windows sandbox did not allow the required `.git` metadata update for `git add`;
- Codex-created Result/source changes therefore need a Local Operations persistence phase before safe Worker release;
- dirty local-only work must remain protected by HOLD/QUARANTINE rather than destructive cleanup.

T002 changes the normal responsibility split to:

```text
Local Operations PREPARE
→ Codex EXECUTE
→ Local Operations PERSIST
→ Local Operations / Chat INTAKE
→ Local Operations RELEASE
```

Automatic future-event callback into an existing ChatGPT chat is not owned by T002.

## Key boundaries

- This repository owns Local Operations host implementation.
- `ai-dev-control` owns GWI / routing / authority.
- `ai-operations-skills` remains owner of host-independent reusable workflow semantics.
- Worker Pool implementation does not authorize auto-dispatch policy.
- Worker cleanup must never silently discard local-only work.
- Codex is responsible for task worktree edits, not normal Git persistence.
- Local Operations may perform only bounded, exact-Task Git persistence defined by T002.
- No force push, merge, publication, deployment, or destructive cleanup authority is added.
