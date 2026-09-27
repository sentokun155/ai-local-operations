# GWI-0010-T012 Task Request

Task Key: `GWI-0010-T012`
Task Name: `Worker-Leased Unity Project Open via Host MCP V0`
Stage: `implementation / bounded host action preparation`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## 1. Decision already made

Do not reopen the direct-Worker Unity CLI route.

Current evidence establishes:

- Native / Host identity `DESKTOP-U5FJ9NG\sennn` can reach the running Unity Editor through Unity CLI / Pipeline.
- MCP-dispatched Codex Worker runs as `DESKTOP-U5FJ9NG\CodexSandboxOffline`.
- The Worker can reach the Pipeline localhost port, but cannot read `Library/Pipeline/.unity-pipeline-port`.
- The descriptor contains the bearer token and is recreated current-user-only by Unity Pipeline.
- Therefore granting descriptor access to the Worker is not the selected architecture.
- The selected architecture candidate is:

```text
Codex Worker
  -> Host-side Local Operations MCP
  -> Unity CLI
  -> Unity Pipeline
  -> Unity Editor
```

The Worker must not receive the descriptor or bearer token.

The Unity Plugin / Skills remain a knowledge source. Plugin runtime reproduction is not required for this Task.

## 2. Current problem

The Unity Editor currently open on the machine points to a normal local project, not to the Worker Pool checkout.

A useful Worker-driven Unity loop therefore first needs to prove that a Worker can request the Host to open **that Worker's own leased Unity project**, and that the Host can re-identify the resulting Editor as the same project.

Do not test Unity asset mutation, EditMode tests, PlayMode tests, or file-change visibility yet.

## 3. Goal

Implement one bounded Host-side MCP action that can open the Unity project associated with an **existing active Worker lease**, without accepting an arbitrary filesystem path.

Candidate tool name:

`open_leased_unity_project(worker_id, work_identity, task_key)`

Exact naming may be adjusted only if the repository already has a stronger naming convention.

The tool must:

1. resolve the exact active Worker lease;
2. resolve that lease's managed repository root;
3. verify that the repository is a Unity project;
4. determine the project-declared Unity Editor version from repository-owned metadata;
5. use the installed, supported Unity CLI open route to open that exact project under the Local Operations Host identity;
6. avoid closing or changing the already-open default project;
7. re-identify the opened project through the supported Unity CLI/Pipeline route;
8. return bounded identity/readiness data;
9. never expose the Pipeline descriptor or bearer token to the Worker.

## 4. Entry gate: Worker -> Host MCP feasibility

Before broad implementation, confirm from current app-server / Local Operations evidence whether a dispatched Worker can invoke Local Operations Dev MCP tools.

Use existing evidence and supported catalogs first.

Do not create a second transport if the existing MCP route already supports this.

If the current app-server Worker cannot call Host MCP tools at all, stop with:

`HOLD / WORKER_HOST_MCP_UNAVAILABLE`

and document the exact missing attachment/configuration point.

Do not continue to build an unusable open tool behind an unreachable surface.

## 5. Lease-bound path resolution

The open action must not accept:

- arbitrary absolute project paths;
- arbitrary shell commands;
- arbitrary Unity CLI arguments;
- a repository path supplied by the Worker.

Resolve the project root from:

- `worker_id`
- `work_identity`
- `task_key`
- the current Worker Pool lease

The lease must still be active and identities must match exactly.

For V0, the expected real target repository is `sentokun155/2Dhakusura`, but prefer verifying "managed repository + valid Unity project" rather than hard-coding a machine path.

## 6. Unity project identity

Before opening, verify the resolved repository contains the minimum Unity project identity required by the current project, including repository-owned Editor version metadata.

Use the repository's actual Unity version as authority.

Do not:

- upgrade the project;
- install another Editor;
- change `ProjectVersion.txt`;
- change packages;
- accept a fallback Editor version silently.

If the required Editor is unavailable, return a bounded HOLD result.

## 7. Unity CLI open route

Inspect the installed Unity CLI version/help/documentation and use its supported project-open operation.

Do not assume an undocumented command shape.

Requirements:

- Host-side process execution only.
- No shell string execution.
- No `--allow-install` or equivalent installation behavior.
- No login/license mutation.
- No project upgrade.
- No Editor termination.
- No forced closure of the currently open default project.
- Multiple Editor instances are acceptable if Unity supports them for different project paths.

If the project is already open and uniquely identifiable, return an idempotent `ALREADY_READY`-style success instead of opening a duplicate.

## 8. Re-identification / readiness

After open request, identify the target by the **resolved Worker project path**, not by whichever Editor happens to be first.

Use supported Unity CLI/Pipeline status/list operations with explicit project targeting where available.

Return only bounded fields such as:

- status / verdict;
- workerId;
- repository identity;
- resolved project path;
- project-declared Editor version;
- Host user;
- Editor state;
- observed Editor version;
- PID if available;
- Pipeline port if already safely returned by the CLI;
- whether the resolved Worker project is uniquely ready;
- whether it was already open or newly opened.

Do not return:

- bearer token;
- descriptor contents;
- raw environment;
- raw command line;
- full raw Unity JSON;
- unrelated Editor/project details beyond what is needed to disambiguate the target.

## 9. Side-effect boundary

Opening a Unity project naturally may create/update ignored runtime state such as `Library`, `Temp`, or `Logs`.

This Task must distinguish those expected Editor/runtime effects from tracked repository mutation.

The tool must not intentionally modify:

- `Assets`
- `Packages`
- `ProjectSettings`
- tracked source/docs
- Git configuration

Do not implement automatic cleanup of Unity-generated state.

Do not run Git reset/clean.

## 10. Existing Editor coexistence

The currently open default Unity project is not the Worker project.

The implementation must not assume it can reuse that Editor as the target.

Do not close it.

The result must make clear which project path the newly observed Editor belongs to.

If the supported Unity CLI cannot safely open another project while the current one remains open, return HOLD and document that limitation instead of changing the existing Editor session.

## 11. Tests

Add focused tests for at least:

- exact active lease resolves to its managed repository root;
- mismatched worker/work/task identity rejected;
- non-Unity repository rejected;
- arbitrary path cannot be supplied;
- project-declared Editor version is read correctly;
- required Editor unavailable -> HOLD;
- already-ready target -> idempotent success;
- supported open command generated only from Host-resolved data;
- different currently-open project is not mistaken for target;
- target project becomes uniquely ready after open;
- credential/descriptor-like fields never returned;
- timeout/no-ready outcome preserves current Editor processes and returns HOLD.

Run the supported repository test environment available on the execution surface.

If the Worker environment cannot run the project tests for a known infrastructure reason, record that accurately; do not misreport tests as executed.

## 12. Live-effect boundary for this implementation Task

This Codex implementation Task must **not** open the real Worker Unity project.

It implements source/tests/docs only.

Do not during this Task:

- invoke the new open action against the real machine;
- start/stop Unity Editor;
- change descriptor ACL;
- read descriptor contents;
- configure Unity MCP;
- run Unity tests;
- change Production;
- restart Dev/Prod runtime;
- alter Worker security/sandbox policy.

Live E2E is a Controller follow-up after finalize + Dev runtime/plugin refresh.

## 13. Controller follow-up after implementation

After this Task is finalized and Development runtime/tool catalog is refreshed:

1. Dispatch a small read-only Codex Task **against `sentokun155/2Dhakusura`** so a Worker has a real lease for that repository.
2. From that Worker, invoke the Host MCP open action for its own lease.
3. Verify the Host runs under the expected Host identity.
4. Verify the target path is exactly that Worker's `2Dhakusura` checkout.
5. Verify Unity Editor becomes ready for that exact path and required Editor version.
6. Verify the pre-existing default project remains untouched.
7. Verify no descriptor/token is returned to the Worker.
8. From the Worker, inspect its own repository state only; do not mutate project files yet.

Only after this E2E succeeds should a later Task test Worker visibility of Unity-generated/project changes or Unity test execution.

## 14. Result

Create:

`work/gwi-0010/GWI-0010-T012_RESULT.md`

Result vocabulary:

- `PASS / WORKER_PROJECT_OPEN_TOOL_READY`
- `HOLD / WORKER_HOST_MCP_UNAVAILABLE`
- `HOLD / UNITY_OPEN_ROUTE_UNAVAILABLE`
- `HOLD / PROJECT_VERSION_UNAVAILABLE`
- `HOLD / IMPLEMENTATION_VERIFICATION_INCOMPLETE`

PASS means the bounded Host action is implementation-ready for Controller E2E.
It does not mean the real Worker Unity project has been opened yet.

## 15. Persistence

This is an app-server Worker Task.

Use the existing Local Operations finalize flow for repository persistence.

Do not commit/push directly from the Codex Worker.

Final message:

`GWI-0010-T012 <PASS|HOLD> — <one-line result and next Controller action>`
