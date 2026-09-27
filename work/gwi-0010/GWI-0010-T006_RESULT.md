# GWI-0010-T006 Result

- Status: **HOLD / UNITY_CONNECTION_UNAVAILABLE**
- Task: Codex-native Unity Plugin Capability Audit
- Date: 2026-09-27
- Repository: **github.com/sentokun155/ai-local-operations**
- Target branch: **origin/gwi-0010-ai-local-operations**, which resolved to the prepared commit
- Worktree: detached at the prepared commit for isolated Task-owned document changes
- Prepared commit: **1e945c01782e3019de4efa1cff041d87d6e8bc73**
- Task Request blob: **ef60aaaa427a535e6febcac4d8d746206dfc88c3**

## Result

The installed Unity plugin package and its documented CLI architecture were identified. The current Codex Desktop task did not expose a Unity callable tool wrapper, and the Unity CLI reported no connected Editor instances. Because the Editor-specific tool catalog is dynamic and requires a connected Editor, this audit could not capture its exact tool names, descriptions, input/output schemas, or behavior.

The status is **HOLD / UNITY_CONNECTION_UNAVAILABLE**. This records the current observation boundary; it does not claim that the Unity plugin is absent from Codex or that Unity is unavailable on the machine.

## Identity and surface findings

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

## Required follow-up evidence

From Codex Desktop, make the intended Unity 6 project available through the supported Pipeline setup, then capture **unity status --format json** and **unity list --format json**. Record the Editor/project identity and exact live tool schemas before deciding whether one existing read-mostly test is safe. If the intended route is Unity's MCP server, inspect its tools through the supported Codex client catalog after separately authorized configuration.

## Scope and persistence

Only the three Task-owned Result/design documents were created in the repository worktree. No source, Unity project, assets, packages, Worker Pool state, or Local Operations production runtime was changed. The Task Request initially prohibited Codex commit/push; the user later explicitly authorized repository reflection. The final commit/push state and remote readback are reported in the Controller completion message. No dispatch, finalize, merge, or publication was performed.
