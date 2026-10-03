# GWI-0010-T012 Result

Date: 2026-09-27

Task Request commit: `bbbd39f39a61c277280d57cf87cc5d8bc5185c3a`

Handoff commit: `8a927885a46d133cfaa1fd6766fd4263512798bb`

Branch: `gwi-0010-ai-local-operations`

## Verdict

`PASS / WORKER_PROJECT_OPEN_TOOL_READY`

The bounded Host MCP action is ready for Controller E2E. This Result does not claim that the real Worker Unity project was opened.

## Entry gate

- The repository branch was fast-forwarded to `8a927885a46d133cfaa1fd6766fd4263512798bb`; the Task Request commit is an ancestor of the Handoff commit.
- The current tool catalog exposed Local Operations Dev MCP tools. Calling its existing `ping` returned `LOCAL_MCP_OK`, so the Worker-to-Host MCP entry gate passed.

## Implementation

- Added `open_leased_unity_project(worker_id, work_identity, task_key)`. Its MCP schema accepts only those three lease identity fields; it has no project path, shell command, or arbitrary Unity argument input.
- The Host requires an exact active `LEASED` row, derives the repository path from Worker Pool configuration, and checks that the resolved repository stays inside that Worker Slot.
- The action requires a Git checkout with `Assets`, `ProjectSettings`, and a valid `ProjectSettings/ProjectVersion.txt`. It checks the exact project-declared Editor version against `unity editors --installed` and returns HOLD when that version is unavailable.
- The Host invokes the installed Unity CLI through argument arrays with `shell=False`, passes the resolved path and declared Editor version to `unity open`, and filters `unity status` by that path. It then requires exactly one ready instance at the same normalized path and version. A uniquely ready target returns `ALREADY_READY` without another open request.
- Returned data is allowlisted and bounded. Raw CLI output, environment contents, Pipeline descriptor data, and bearer tokens are not returned. The action does not invoke Editor close, Editor install/upgrade, Unity tests, or project cleanup.

## Verification

- Installed CLI: `1.0.0-beta.9`. Its help exposes `unity open`, `unity status --project-path`, and `unity editors --installed`. The installed Editor catalog query exited successfully; no Worker project metadata was read. The [Unity CLI guide](https://github.com/Unity-Technologies/skills/blob/main/skills/unity-cli/SKILL.md) documents checking the project Editor version and installed Editors before `unity open`.
- `uv --directory C:\Dev\DevEnv run --locked python -m unittest discover -s tests -p 'test_unity_project_open.py' -v` — 12 passed.
- `uv --directory C:\Dev\DevEnv run --locked python -m unittest discover -s tests -p 'test_worker_pool.py' -k get_lease -v` — 1 passed.
- `uv --directory C:\Dev\DevEnv run --locked python -m unittest discover -s tests -p 'test_unity_probe.py' -v` — 25 passed.
- `uv --directory C:\Dev\DevEnv run --locked python -m unittest discover -s tests -p 'test_execution_boundary.py' -v` — 2 passed.
- Python compilation and `git diff --check` passed.
- The full `test_worker_pool.py` run did not complete: it remained at the existing `test_recovery_commits_and_pushes_completed_task_before_freeing_worker` case for over 20 minutes. The test runner was stopped; that suite is not reported as passed.

## Live-effect boundary

The new action was not invoked against a real Worker project. No Unity Editor was started or stopped, no descriptor was read, and no Unity test, runtime refresh/restart, Production change, or Worker security change was performed. The Development and Production runtimes remain untouched.

## Persistence and Controller follow-up

The existing Local Operations Dev status tool reported all five Worker Slots `FREE`; there was no active `GWI-0010-T012` lease to pass to `finalize_codex_task`. Following the user's explicit direction to proceed through push, the implementation and this Result were persisted with a normal Git commit and push to `origin/gwi-0010-ai-local-operations`.

After the Development tool catalog is refreshed, the Controller should run the read-only E2E against a Worker leased for `sentokun155/2Dhakusura`, verify the Host identity and exact project path/version, confirm the pre-existing default project remains open, and confirm no descriptor/token is returned.
