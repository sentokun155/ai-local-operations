# GWI-0010-T006 Result

- Status: **PASS / UNITY_ROUTE_DECISION_READY**
- Task: Codex-native Unity Plugin Capability Audit
- Date: 2026-09-27
- Repository: **github.com/sentokun155/ai-local-operations**
- Target branch: **gwi-0010-ai-local-operations**
- Worktree: isolated T006 checkout; repository reflection uses normal non-force Git operations
- Prepared commit: **1e945c01782e3019de4efa1cff041d87d6e8bc73**
- Task Request blob: **ef60aaaa427a535e6febcac4d8d746206dfc88c3**

## Result

The first pass identified the installed Unity plugin package but found no connected Editor, so its live Editor catalog and behavior were then unverified. After the user started Unity, the follow-up connected to the running Editor, captured its live Pipeline catalog, read Editor state and console errors, discovered the available tests, and ran one safe existing EditMode test.

The current status is **PASS / UNITY_ROUTE_DECISION_READY**. The route decision is supported by live Editor and test evidence; it does not claim Unity MCP parity or that all 149 dynamic commands are safe to mirror.

## Identity and surface findings from the initial no-Editor probe

- Installed plugin: **unity**, Codex install identifier documented as **unity@unity-agent-plugin**, version **0.1.6-beta**, publisher Unity Technologies.
- Source: https://github.com/Unity-Technologies/unity-agent-plugin.git, installed revision **566368b21c92c93f74a7dbee34958385d028a300**.
- The package declares **./skills/** and requires a local executor. It contains 32 Unity skills. The package manifest does not declare a fixed MCP tool catalog; no package-root **mcp.json** was present.
- The package README describes the Unity CLI as the route for live Editor interaction and batch testing. The unity-cli skill documents a separate Unity MCP configuration command; that client configuration was not changed.
- The task's callable catalog contained 244 tools, with zero Unity name/description matches. The MCP resource catalog returned 36 resources and 7 plugin resources, with zero Unity resources.
- Unity CLI **1.0.0-beta.9** was available. The read-only status probe returned **STATUS_NO_INSTANCES**, **count: 0**, and **instances: []** with exit code 6.

Status evidence:

    {
      "success": false,
      "command": "status",
      "data": {
        "count": 0,
        "instances": []
      },
      "errors": [
        {
          "code": "STATUS_NO_INSTANCES",
          "message": "Pipeline パッケージがインストールされた Unity Editor インスタンスが見つかりません。"
        }
      ],
      "warnings": []
    }

The package documents **unity list --format json** as the read-only way to retrieve connected Editor tool names, descriptions, groups, and parameter schemas. It was not invoked because no Editor instance was reported. No Unity project was selected, no Editor or Pipeline package was started/installed, no MCP configuration was written, and no tests were run.

## Capability decision

Package documentation supports a candidate hybrid route: retain the official Unity skill/CLI for interactive Codex work, and consider a separate profile-bound Local Operations adapter for test execution and result collection. The adapter should invoke fixed Unity CLI profiles and reuse the host process/result lifecycle recommended by T005. It should not expose arbitrary shell text, dynamic Editor commands, **eval**, installation, package changes, license acceptance, or authentication.

This route is a design input only. T005 remains **PASS / ROUTING_DECISION_READY** for the app-server Worker route; it did not observe the Codex-native Unity tool catalog and does not establish Unity readiness.

## Deliverables

- [Unity Plugin Capability Matrix](design/t006/GWI-0010-T006_UNITY_PLUGIN_CAPABILITY_MATRIX.md)
- [Unity Plugin Replication Design](design/t006/GWI-0010-T006_UNITY_PLUGIN_REPLICATION_DESIGN.md)

## Follow-up evidence requested on the initial pass

From Codex Desktop, make the intended Unity 6 project available through the supported Pipeline setup, then capture **unity status --format json** and **unity list --format json**. Record the Editor/project identity and exact live tool schemas before deciding whether one existing read-mostly test is safe. If the intended route is Unity's MCP server, inspect its tools through the supported Codex client catalog after separately authorized configuration.

## Scope and persistence

Only the three Task-owned Result/design documents were created in the repository worktree. No source, Unity project, assets, packages, Worker Pool state, or Local Operations production runtime was changed. The Task Request initially prohibited Codex commit/push; the user later explicitly authorized repository reflection. The final commit/push state and remote readback are reported in the Controller completion message. No dispatch, finalize, merge, or publication was performed.

## Live Editor follow-up (2026-09-27)

This follow-up supersedes the initial connection HOLD.

- Unity CLI 1.0.0-beta.9; one ready Unity 6000.3.9f1 Editor at 127.0.0.1:7800, project C:/Users/sennn/2D_RPG_Project6_git.
- editor_status: ready, compiling=false, domainReloadInProgress=false, playMode=stopped.
- unity list returned 149 built-in Editor commands with input schemas; it declares no per-command output schemas. The Codex catalog still has 244 tools and zero Unity matches.
- list_tests found one EditMode documentation stub and no PlayMode tests. A single filtered run_tests probe passed 1/1 in 3.25 seconds.
- get_console_logs with severity=error returned total=0, returned=0, logs=[].

| Tool | Input schema | Observed output / classification |
|---|---|---|
| editor_status | No parameters. | Read-only; status, compile/domain-reload state, Play Mode, project path, Unity version. |
| list_tests | Optional mode:string; all/editor/playmode; default all. | Read-only discovery; Mode, Count, Tests, success, result, message. |
| run_tests | mode:string=all; filter:string=empty; filter_type:string=testName/assembly/category=testName; include_explicit:bool=false; async_tests:bool=false; timeout:int seconds=300. | Executes tests; Summary, Results, Duration, StatusPath, Mode, FilterApplied and success observed. |
| get_console_logs | severity:string=all/log/warning/error=all; limit:int=100, max 1000. | Read-only; zero error entries observed. |
| test_status / cancel_tests | No parameters. | Poll and cancellation controls listed; cancellation not tested. |

The common command envelope contains success, command, data, errors, warnings. The only test was AddressableAssets.DocExampleCode.TestStub.RequiredTest; its package-cache source is an empty NUnit test method. No Editor.log was read. PlayMode, cancellation, timeout, busy Editor, compile failure, and Safe Mode were not tested.

The Unity project's tracked diff was clean. Two unrelated untracked Markdown files had last-write times of 2026-09-14 and 2026-09-17 and were left untouched. No Unity source, assets, packages, settings, or scenes were edited.

Route decision: keep the official Unity skill/CLI for interactive Editor work. Any future Local Operations validation adapter should be profile-bound and limited to test lifecycle and result/log collection; do not mirror the 149-command dynamic surface or expose arbitrary Editor commands or eval.
