# GWI-0010-T006 Unity Plugin Replication Design

- Status: **CONDITIONAL DESIGN INPUT — no implementation authorized**
- Task: GWI-0010-T006
Basis: [Capability Matrix](GWI-0010-T006_UNITY_PLUGIN_CAPABILITY_MATRIX.md)

## Summary

The installed Unity plugin is a Codex skill package backed by the local Unity CLI. Its static skill documents describe both live Editor control through Unity's Pipeline package and batch EditMode/PlayMode testing. The plugin package does not declare a fixed MCP server or tool schema. The Codex task catalog still has no Unity callable tool wrapper. The initial status probe found no Editor; the later follow-up connected to a ready Editor through the CLI/Pipeline route.

The candidate route is hybrid:

1. Keep the official Unity skill/CLI surface for interactive Codex work in an open Editor.
2. If Local Operations later needs repository validation, implement a small profile-bound host adapter that invokes documented Unity CLI operations and owns project identity, process lifecycle, timeout/cancel, and artifacts.
3. Do not reproduce the plugin's whole dynamic command surface or pass arbitrary shell/Editor commands through Local Operations.

This is a design input, not an implementation authorization. The live catalog and behavior from the follow-up are recorded below, and the route decision is now ready.

## Initial evidence classification

| Class | Finding |
|---|---|
| Observed | Installed plugin manifest name **unity**, version **0.1.6-beta**, Unity Technologies publisher, Git install source and revision **566368b21c92c93f74a7dbee34958385d028a300**; 32 skill directories; Unity CLI **1.0.0-beta.9**; status reported zero connected Editors. |
| Documented | Plugin README describes Unity CLI as its main route to an open Editor. The unity-cli skill documents status/list/command operations using **com.unity.pipeline**, CLI-driven test/build operations, and a separate **unity mcp configure codex** setup path. |
| Inferred | A Local Operations adapter can reuse the CLI as a controlled backend for declared test profiles, while common host-runner code owns process and artifact lifecycle. |
| Unknown | The actual connected Editor tool names, descriptions, input/output schemas, custom project commands, live console/compile state, selected project, Editor version, package/license state, and safe existing tests. |

## Surface architecture

### Unity skill and CLI

The package manifest points to **./skills/** and requires a local executor. Its README says the Unity CLI can drive an already-open Editor and can also install/open projects, build, and test. The installed unity-cli skill documents:

- **unity status** for connected Editor state, project, version, and PID.
- **unity list** for the current Editor's registered tool names, descriptions, groups, and parameter schemas.
- **unity command** for invoking registered Editor commands. The Editor and project can add dynamic commands; the skill documents **eval/eval_file** when available.
- **unity test** for EditMode/PlayMode batch tests and NUnit/JUnit reports.
- **unity mcp configure codex** as a separate setup action that writes client configuration.

The command catalog is partly Editor-defined and project-specific. The current package does not supply a fixed plugin MCP schema that can be copied into Local Operations. The Unity MCP configure path was not invoked.

### Local Editor communication

The package documentation describes live status/list/command operations as CLI-to-Pipeline communication with an already-running Unity Editor. **com.unity.pipeline** must be available in the project for that live route. The CLI discovers Editors, reports readiness, and accepts a project path when multiple Editors could match.

The package also documents batch testing as a separate route: **unity test** launches the Editor command line with test-run arguments, waits for completion, and returns a report. That path does not use the Pipeline server. The exact live Editor endpoint and wire-level protocol were not captured in this task; no private binary inspection or configuration probing was performed.

### Relation to other GWI-0010 surfaces (initial view)

- **Local Operations app-server Worker:** T005 is **PASS / ROUTING_DECISION_READY** for its own validation-routing decision. It did not observe this plugin's Desktop tool list and did not establish Unity readiness.
- **Codex-native / Desktop:** the installed Unity skill package and local CLI are present; no Unity callable tool was exposed in this task, and no Editor was reported by the CLI.
- **Local Operations Host:** a future adapter could execute bounded Unity validation under a Worker lease.
- **ChatGPT Controller:** selects the authorized profile, starts the host run, and decides persistence. The adapter must not take over Controller authority.

## Candidate Local Operations tools

All entries below are design candidates, not existing tools.

| Candidate tool | Bounded request | Returned evidence | Boundary |
|---|---|---|---|
| **unity_readiness** | Lease identity and repository-owned profile ID | CLI availability/version, resolved project identity, Editor readiness/version, package/license preflight state | Resolve paths from the lease/profile; do not accept arbitrary absolute paths. No install, login, or package mutation. |
| **unity_catalog_read** | Lease identity and an allowlisted project profile | Read-only status and, when connected, a bounded **unity list** catalog snapshot | Return catalog data only. Do not expose dynamic commands for execution or infer missing schemas. |
| **unity_test_start** | Lease identity, fixed profile ID, EditMode or PlayMode, optional approved test filter | Run ID, start time, resolved versions, artifact directory, process identity | Generate argv from the profile. Do not accept arbitrary CLI text, Editor flags, command/eval names, or **--allow-install**. |
| **unity_test_status** | Run ID | Lifecycle state, elapsed time, bounded progress and captured output | Polling timeout is not process cancellation. Do not restart an uncertain run. |
| **unity_test_cancel** | Run ID owned by the same lease | Cancellation request and final process state | Stop only the process tree owned by that run; never kill by process name. Preserve partial logs/reports. |
| **unity_result_read** | Run ID and approved artifact kinds | Test summary, report status, bounded stdout/stderr, report/log locators | Keep raw artifacts separate from derived judgment. A missing report is not PASS. |

The adapter should not expose generic **unity command**, arbitrary **[CliCommand]**, **eval**, **eval_file**, arbitrary build methods, project creation, install, license, or auth operations. Those have broader mutation or authority than repository validation requires.

## Route comparison

| Route | Benefits | Limits | Decision |
|---|---|---|---|
| Use the Unity plugin only | Official skills and CLI knowledge support interactive Editor authoring and Unity-specific guidance. | Does not by itself bind tests to a Worker lease, own a host run ID, enforce repository profiles, or persist bounded result artifacts. The initial pass had no connected Editor; the live follow-up now documents its available route. | Retain for Codex-native interactive work. Do not treat it as the Worker validation route. |
| Reimplement Unity tools in Local Operations | Could expose a uniform host API. | Would duplicate a broad and project-extensible command surface, increase mutation authority, and require maintaining Editor protocol behavior that the CLI already supplies. | Not recommended. |
| Hybrid | Keeps Unity-authored skills/CLI for direct work and gives Local Operations a small host-owned test lifecycle with repository binding. | The live connection check is complete; profile and host validation remain required before implementation. | **Recommended candidate**, supported by T006 live-catalog evidence but still pending host lifecycle validation and a separately authorized implementation task. |

## Test routing

The installed CLI reference documents **unity test <project> --mode EditMode** and **--mode PlayMode**, optional test filters, NUnit/JUnit output, and a bounded timeout. It launches the Editor in batch mode. A successful test run, a test assertion failure, and a run that never produced a verdict have distinct documented result codes.

For a future Local Operations profile:

1. Resolve the Unity project from the repository lease and declared profile.
2. Verify the required Editor version against repository-owned project metadata. Reject mismatch; do not install or upgrade an Editor.
3. Keep EditMode and PlayMode as separate profiles, each with an explicit filter, timeout ceiling, and artifact contract.
4. Start one owned process per run. Initially serialize runs for a project and avoid running batch tests beside an Editor using the same project.
5. Capture exit code, structured CLI result, stdout/stderr, NUnit/JUnit files, and relevant Editor log locator.
6. Classify compile/setup/license/Editor failures as infrastructure or no-verdict outcomes, separately from reported failing tests.

The T005 recommendation already calls for Unity as a separate adapter using the common process/result lifecycle. This design refines that recommendation around the observed Unity CLI; it does not authorize an implementation.

## Results, logs, and compilation

The CLI documentation describes a JSON result envelope with success, command, data, errors, and warnings. Test results can be written as NUnit or JUnit XML. The docs distinguish reported test failure from a test run that could not produce a verdict, including compile error, unavailable license, Editor crash, invalid platform, or timeout.

The CLI's **logs** command reads the CLI's own logs. The skill directs compile-error diagnosis to filtered Editor.log content. The Pipeline skill documentation says Safe Mode prevents the Pipeline package from loading, so live status/list/command connection may be unavailable. A host adapter should preserve raw log/report paths and classify missing reports or compilation failures without converting them into test results.

The initial pass did not observe a Unity console, compile state, Editor.log, test report, or test result schema from a connected Editor. The live follow-up below records the later observations.

## Editor lifecycle, timeout, and concurrency

The skill documents live Editors as already-running processes for status/list/command. It reports **starting** separately from **ready**, and warns that multiple Editors require explicit project targeting. **unity test** instead launches a batch Editor and accepts a timeout. The CLI shell documents Ctrl-C cancellation for supported operations, not as a universal cancellation guarantee for all Editor actions.

The Local Operations host should own start, poll, deadline, cancel, and final collection. A caller wait timeout must not imply that the Unity process stopped. On timeout or lost response, inspect the existing run ID and preserve partial evidence; do not start a replacement run until the original state is known. Enforce one active run per project until safe parallel behavior is validated.

## Packages, login, and licensing

Live Editor tools require the project's **com.unity.pipeline** package. Installing that package or configuring Unity MCP changes the project/client and was not part of this audit. Batch tests use the Editor command-line test runner and are documented separately from Pipeline live commands.

The CLI supports Editor installation and authentication/licensing flows, but the Local Operations adapter should not invoke them implicitly. Package restore, Editor installation, sign-in, license acceptance, Unity Cloud account selection, and project upgrade remain separate Human or explicitly authorized host preparation. Secrets must not appear in process arguments or logs.

## Live Editor follow-up evidence

The follow-up observed Unity CLI 1.0.0-beta.9, one ready Editor at 127.0.0.1:7800, project C:/Users/sennn/2D_RPG_Project6_git, and Unity 6000.3.9f1. unity list returned 149 built-in commands with input schemas but no declared per-command output schemas. The Codex task's 244 callable tools still had no Unity name/description match.

editor_status reported not compiling, no domain reload, and Play Mode stopped. list_tests found one EditMode documentation stub and no PlayMode tests. Its source was an empty NUnit method. One exact filtered run_tests execution passed 1/1 in 3.25 seconds. An error-only get_console_logs read returned zero records. The project tracked diff remained clean; two unrelated untracked Markdown files had timestamps before this probe and were not changed.

The observed command envelope has success, command, data, errors, and warnings. The test result is nested under data.result and includes Summary, Results, Duration, StatusPath, Mode, FilterApplied, success, and result. This proves a narrow live Editor route and a single EditMode execution, not full output-schema parity, PlayMode support, cancellation, timeout, or compile-failure behavior.

## Route decision readiness

The live-entry criteria needed for the route decision are met. Result status: **PASS / UNITY_ROUTE_DECISION_READY**.

Keep the official Unity skill/CLI for interactive Editor commands. If Local Operations needs repository validation, use a profile-bound adapter for the dedicated CLI test lifecycle, run identity, timeout/cancel handling, and result/log collection. Do not expose the Editor's 149-command dynamic surface, arbitrary command names, eval, or project mutation through a generic host tool.

If a future task requires direct Unity MCP calls inside Codex, authorize and inspect the supported client configuration and tool catalog separately. This T006 audit did not write MCP configuration or implement an adapter.
