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

Status: **T002 IMPLEMENTED AND DEVELOPMENT VERIFIED**

T001 established the Repository-backed Local Operations implementation, fixed Worker Pool, logical repository routing, Codex app-server dispatch, Dev/Prod runtime separation, and Worker reuse/quarantine behavior.

Human runtime probes after T001 established:

- app-server-created work appears as Codex Tasks rather than ChatGPT chats;
- direct ChatGPT chat-list / chat-send capability is absent from the observed Codex Task tool catalog;
- Codex subagent capability is available (`spawn_agent`, `wait_agent`, `send_message`; PROBE-004 PASS);
- Codex can edit the leased worktree under `workspace-write`, but the observed Windows sandbox did not allow the required `.git` metadata update for `git add`;
- Codex-created source/Result changes therefore need Local Operations to persist them before Worker reuse.

T002 changed the normal responsibility split to:

```text
Local Operations: Worker確保・指定branch最新化
→ Codex: worktree編集 / test / Result
→ Local Operations: commit / non-force push / Result Intake
→ Worker FREE
```

`finalize_codex_task(worker_id, work_identity, task_key)` reads the exact completed turn and returns its final agent message and changed paths. It commits and normally pushes when there are changes, or returns a read-only Result without a commit, then frees a clean Worker on its current branch. `LOCAL_OPERATIONS_CODEX_EXECUTABLE` selects the executable, with PATH lookup as the fallback.

Verification: `uv run --locked python -m unittest discover -s tests -v` — 48 passed, 1 opt-in live app-server test skipped. Development probe branch `gwi-0010-t002-dev-e2e-probe-20260927` was dispatched through `Local Operations Dev`; worker-03 produced `GWI-0010-T002-DEV-E2E-RESULT.md`, final message and commit `9dd09ccc12ccfb6a2d4ebc4f05b904e3d9a2507a` were returned, and worker-03 became FREE. The current Codex task's cached Local Operations Dev tool catalog did not yet expose the new finalize schema, so the same Development runtime finalization implementation was invoked directly for this probe after confirming the target turn completed.

PROBE-002 and PROBE-003 remain QUARANTINED with their diagnostic Result files preserved. Automatic callback into an existing ChatGPT conversation is not implemented.

The personal-tool proportionality rule applies: exact starting HEAD / Task Request blob pinning, default-branch restore, strict production promotion gates, redundant remote readbacks, and other production-style machinery are not normal requirements unless they prevent a concrete local risk.

Automatic future-event callback into an existing ChatGPT chat is not owned by T002.

## Key boundaries

- This repository owns Local Operations host implementation.
- `ai-dev-control` owns GWI / routing / authority.
- `ai-operations-skills` remains owner of host-independent reusable workflow semantics.
- Worker Pool implementation does not authorize auto-dispatch policy.
- Codex edits the leased task worktree; Local Operations performs normal Git persistence.
- Preserve unpersisted local work on failure.
- Keep only concrete safeguards such as avoiding force push, wrong-repository work, duplicate Worker use, destructive cleanup, and secret exposure.
