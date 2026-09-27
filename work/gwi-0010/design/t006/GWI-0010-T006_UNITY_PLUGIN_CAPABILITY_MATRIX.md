# GWI-0010-T006 Unity Plugin Capability Matrix

- Status: **PASS / UNITY_ROUTE_DECISION_READY**
- Task: GWI-0010-T006 — Codex-native Unity Plugin Capability Audit
- Date: 2026-09-27
- Repository: sentokun155/ai-local-operations
- Target branch: gwi-0010-ai-local-operations
- Worktree: isolated T006 checkout; repository reflection uses normal non-force Git operations
- Prepared commit: 1e945c01782e3019de4efa1cff041d87d6e8bc73
- Task Request blob: ef60aaaa427a535e6febcac4d8d746206dfc88c3

## Scope and evidence labels

This audit used the Codex Desktop task's callable-tool/resource catalog, the installed Unity plugin package files, the local Unity CLI, and the repository's pinned T005 outputs. It did not use Local Operations dispatch, app-server Worker execution, Computer Use, or UI automation.

- **Observed** means directly returned by this task's tool catalog, resource catalog, CLI, or local manifest.
- **Documented** means stated by the installed plugin's README or Unity CLI skill/reference files. It is not a live Editor observation.
- **Inferred** means a bounded design conclusion derived from observed or documented facts.
- **Unknown** means the current evidence does not answer the question.

## Plugin identity and package

| Field | Finding | Evidence |
|---|---|---|
| Codex plugin name | **unity**; display name **Unity** | **.codex-plugin/plugin.json** |
| Codex install identifier | **unity@unity-agent-plugin** | Package README install/list examples; the manifest itself has **name: unity** and no separate ID field |
| Version | **0.1.6-beta** | **.codex-plugin/plugin.json**; also the installed skill catalog |
| Publisher | Unity Technologies | **.codex-plugin/plugin.json** |
| Origin | https://github.com/Unity-Technologies/unity-agent-plugin.git | **.codex-marketplace-install.json** and package Git remote |
| Installed source revision | **566368b21c92c93f74a7dbee34958385d028a300** | **.codex-marketplace-install.json**; matches package checkout HEAD |
| Local package root | C:/Users/sennn/.codex/plugins/cache/unity-agent-plugin/unity/0.1.6-beta | Installed filesystem path |
| Declared package entrypoint | **./skills/**; **requires_local_executor: true** | **.codex-plugin/plugin.json** |
| Declared UI capabilities | **Interactive**, **Read**, **Write** | Manifest labels only; they do not enumerate callable tool schemas |

The installed package contains 32 skill directories. These are skill names, not callable tool names:

**2d-pixel-perfect**, **asset-transformer-toolkit**, **audio-setup-mixers**, **build-live-game**, **generate-editor-search-query**, **implement-in-app-purchases**, **initialize-ai-navigation**, **levelplay-unity-integration**, **localization**, **manage-sprite-atlas**, **migrate-birp-to-urp**, **new-unity-project**, **optimize-audio**, **optimize-text-mesh-pro**, **optimize-web**, **physics-3d-collision**, **setup-multiplayer-services**, **setup-vivox-voice-chat**, **shader-graph-create-custom-node**, **sprite-editor**, **sprite-segment-3x3grid**, **tilemap-palette-create**, **tilemap-ruletile-createempty**, **tilemap-ruletile-createfromsegment**, **ui**, **ui-imgui**, **ui-ugui**, **ui-uitk**, **unity-cli**, **unity-package-management**, **urp-postprocessing**, **validate-urp-render-graph-renderer-feature**.

The plugin manifest declares a skills directory and has no MCP tool/server declaration. No **mcp.json** exists at the package root.

The README documents **unity mcp configure codex** as a separate CLI setup that gives a client Unity tools. That configuration command was not run: it writes client configuration and is outside this task's allowed repository-document mutation.

## Initial no-Editor surface observation

At audit time, the active task exposed 244 callable tool definitions. No tool name or description contained “Unity”. The MCP resource catalog returned 36 resources, including 7 plugin resources; none identified Unity. This does not erase the locally installed Unity skill package. It means this task had no direct Unity MCP tool wrapper available in its callable surface.

The Unity CLI is installed as version **1.0.0-beta.9**. The read-only readiness probe was:

    unity status --format json --no-banner --non-interactive

It returned **STATUS_NO_INSTANCES**, **count: 0**, and an empty **instances** array, with exit code 6. Therefore no Editor project, Editor version, project path, or live Pipeline command catalog was observable through this CLI in this task.

The package skill documents **unity list --format json** as a read-only catalog query that returns the connected Editor's registered tool names, descriptions, groups, and parameter schemas. It was not run because **status** found no connected instance. No Editor was started, no Pipeline package was installed, no MCP configuration was written, and no Unity test was run.

## Surface separation

| Surface | Meaning in this audit | Finding |
|---|---|---|
| Local Operations app-server Worker | The route audited by T005 | T005 is **PASS / ROUTING_DECISION_READY** for its routing decision. It did not observe the Codex-native Unity plugin or establish Unity execution readiness. |
| Codex-native / Desktop | Installed Unity skill package plus whatever tools are exposed to this Codex task | The package and CLI are present. This task's callable catalog had no Unity tool wrapper, and the CLI reported no connected Editor. |
| Local Operations Host | A possible future bounded executor for Unity validation | No Unity adapter was implemented or exercised by T006. Candidate boundary is described in the replication design. |
| ChatGPT Controller | Selects the next action and starts authorized host work | Must keep repository/profile selection, execution grant, and persistence separate from the Unity tool surface. |

## Capability matrix

Rows in this matrix record the initial no-Editor snapshot. Time-sensitive findings are superseded by the live follow-up section below.

| Capability | Codex-native Unity Plugin | app-server Worker | Local Operations MCP reproducibility | Recommended route |
|---|---|---|---|---|
| Plugin identity and origin | **Observed:** Unity **unity** plugin, **0.1.6-beta**, Unity Technologies, installed from Unity-Technologies/unity-agent-plugin at revision **566368b...**. | Not the Unity plugin identity surface. | Can record the repository-approved adapter/version identity; do not infer it from Worker tool names. | Preserve plugin identity as an environment observation and pin CLI/Editor versions per run. |
| Fixed callable MCP tool catalog | **Observed:** zero Unity-named callable tools in this task; package manifest declares skills, not MCP tools. | **Observed:** T005 is a separate app-server Worker audit. It does not expose this plugin's tools. | A bounded host adapter can expose its own stable typed interface. | Keep plugin skills and host adapter as distinct surfaces. |
| Live Editor tool list and schemas | **Documented:** **unity list** retrieves registered Editor tools and schemas via **com.unity.pipeline**; **Unknown:** current Editor catalog and schemas. | **Unknown:** T005 did not observe the Codex-native Editor catalog. | Could return a constrained copy of **unity list** data when a profile is authorized and an Editor is reachable. | Do not mirror every dynamic command. Allowlist read-only catalog data; keep arbitrary command/eval out of Local Operations. |
| Editor connection, version, project | **Observed:** CLI **status** reported zero instances. **Unknown:** active project and Editor version. | T005 recorded Unity readiness as unverified; no Unity test ran. | Host preflight could return state, project identity, and version before a run. | Make readiness a blocking precondition for live Editor operations. |
| Project selection/version matching | **Documented:** project path can disambiguate multiple Editors; CLI supports explicit Editor version selection for batch runs. **Unknown:** current project selection. | Worker-side repo/project identity is governed by its own lease and is not evidence of an open Editor. | Resolve project root from the lease and profile; compare declared Editor version; reject ambiguity or mismatch. | Never accept an arbitrary absolute path or silently upgrade the project. |
| Live Editor inspection and commands | **Documented:** status/list/command/eval use the Pipeline package and a running Editor. **Unknown:** live commands available here. | Not tested by T005. | Technically reachable through the CLI, but arbitrary dynamic commands can mutate project state. | Leave interactive scene authoring with the official skill/CLI route; do not expose unrestricted command/eval through the host adapter. |
| EditMode tests | **Documented:** **unity test** can select EditMode and write NUnit/JUnit reports. **Not executed:** no Editor/project was connected. | T005 did not execute Unity tests. | Reproducible through a fixed test profile and bounded host process lifecycle. | Host adapter should accept profile ID and test selection, not shell text. |
| PlayMode tests | **Documented:** **unity test** can select PlayMode. **Not executed:** no Editor/project was connected. | T005 did not execute Unity tests. | Reproducible through a separate declared profile; runtime/graphics needs can differ from EditMode. | Keep EditMode and PlayMode separate and initially serialize Unity runs per project. |
| Test result and logs | **Documented:** JSON result envelope plus NUnit/JUnit reports; **unity logs** reads CLI logs, while Editor compilation errors require filtered Editor.log reading. **Unknown:** current console/log/result behavior. | T005 did not produce Unity artifacts. | Host can store run-scoped XML/logs and return a bounded summary plus artifact locators. | Keep raw artifacts separate from derived verdict; missing report is infrastructure failure. |
| Compile state and Safe Mode | **Documented:** Safe Mode prevents Pipeline connection; compile errors in **unity test** produce no test verdict. **Unknown:** live compile state. | T005 marked Unity readiness unverified. | Host can classify compile/launch failures separately from failing tests. | Never convert compile/setup failure into test FAIL or PASS. |
| Timeout and cancellation | **Documented:** test timeout, typed timeout result, CLI process termination behavior, and cancellable CLI shell operations for supported commands. **Unknown:** Editor-specific cancellation behavior here. | T005 distinguishes poll timeout from process cancellation. | Host can own PID/run ID, deadline, cancel, and output collection. | Use the common host process/result lifecycle from T005; preserve partial evidence. |
| Busy Editor, concurrency, package/license | **Documented:** starting/unreachable states, explicit project selection for multiple Editors, Pipeline package requirement for live tools, and separate batch-test path. **Unknown:** current busy/license/package state. | T005 recommends a separate Unity adapter and no assumed Unity readiness. | Preflight and project-level serialization are implementable; license acceptance remains Human/external. | Do not install packages, accept licenses, or clean up failing state implicitly. |
| Route decision | Static package evidence supports a candidate design, but live Editor schemas are missing. | T005 is a separate Worker-side routing decision. | A bounded adapter is plausible; equivalence is not yet verified. | **Conditional hybrid:** retain the Unity skill/CLI for interactive authoring; add only a profile-bound Local Operations validation adapter after live catalog and host lifecycle validation. |

## Live Editor follow-up (2026-09-27)

This section supersedes time-dependent connection, catalog, test, console, and compile-state findings above. Static plugin identity and T005 separation remain unchanged.

| Capability | Current live finding | Boundary |
|---|---|---|
| Direct Codex Unity tools | 244 active tools; zero Unity name/description matches. The installed package declares skills and a local executor, not a fixed MCP catalog. | Do not call the Pipeline commands direct Codex MCP tools. |
| Live Editor catalog | unity list returned 149 built-in commands with names, descriptions, and input schemas. | No per-command output schemas are declared; no custom project command was listed. |
| Editor target | One ready Editor at 127.0.0.1:7800; project C:/Users/sennn/2D_RPG_Project6_git; Unity 6000.3.9f1. | Multi-Editor ambiguity was not probed. |
| State and tests | editor_status: not compiling, no domain reload, Play Mode stopped. list_tests found one EditMode stub, no PlayMode tests; one filtered EditMode test passed 1/1. | Only a minimal EditMode route was exercised. |
| Console and logs | get_console_logs severity=error returned zero entries. | Editor.log was not read; no dedicated Editor.log tool was observed. |
| Timeout/cancel | run_tests declares async_tests and timeout (default 300 seconds); test_status and cancel_tests are present. | Async, timeout, and cancellation behavior were not exercised. |

Relevant observed schemas and result shapes:

| Tool | Input schema | Classification / output |
|---|---|---|
| editor_status | None. | Read-only; data.result has status, compiling, domainReloadInProgress, playMode, lastHeartbeat, projectPath, unityVersion. |
| list_tests | mode:string optional, all/editor/playmode, default all. | Read-only; data.result has Mode, Count, Tests, success, result, message. |
| run_tests | mode:string; filter:string; filter_type:string; include_explicit:bool; async_tests:bool; timeout:int seconds. Defaults: all, empty, testName, false, false, 300. | Test execution; observed data.result has Summary, Results, Duration, StatusPath, Mode, FilterApplied, success, result. |
| get_console_logs | severity:string all/log/warning/error; limit:int default 100, capped at 1000. | Read-only; total=0, returned=0, logs=[]. |
| test_status / cancel_tests | None. | Read-only poll / cancellation control; not exercised. |

The command envelope contains success, command, data, errors, and warnings. The endpoint observed was loopback; the wire protocol was not inspected. This supports PASS / UNITY_ROUTE_DECISION_READY for a bounded route choice, not full tool parity.

Still unknown: PlayMode execution, Editor.log retrieval, output schemas for unprobed commands, busy/multiple-Editor behavior, cancellation, timeout, compile failure, Safe Mode, and direct Unity MCP configuration. No MCP client configuration was written.

## Decision limit
The result is **PASS / UNITY_ROUTE_DECISION_READY** for the route choice, not a claim of full tool parity. Keep the Unity skill/CLI for interactive Editor work and limit any future Local Operations adapter to profile-bound test lifecycle and result collection.

Remaining unverified: PlayMode execution, Editor.log retrieval, unprobed command output schemas, busy/multiple-Editor handling, cancellation, timeout, compile failure, Safe Mode, and direct Unity MCP configuration. No Unity MCP client configuration was written.

## Sources

- Installed package: **.codex-plugin/plugin.json**, **.codex-marketplace-install.json**, **README.md**
- Installed skill: **skills/unity-cli/SKILL.md**
- Installed CLI references: **skills/unity-cli/references/integration-advanced.md**, **build-run-test.md**, **diagnostics-maintenance.md**
- Repository baseline: [T005 Result](../../GWI-0010-T005_RESULT.md), [T005 Validation Routing Decision](../t005/GWI-0010-T005_VALIDATION_ROUTING_DECISION.md)
