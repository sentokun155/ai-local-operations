# Unity Host connectivity investigation — 2026-09-27

Scope: Development Local Operations only. Target project: `C:\Users\sennn\2D_RPG_Project6_git`. No Unity project, package, scene, Editor state, or Production runtime was changed.

## Observed

- Native user `DESKTOP-U5FJ9NG\sennn` had Unity Editor PID 5352 open on the target project, version `6000.3.9f1`. Unity CLI at `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe` reported `1.0.0-beta.9`.
- Native `unity pipeline list --format json --no-banner --non-interactive` reported one running target candidate, Pipeline `0.6.0-exp.1`, and a reachable server on port 7800.
- Native `unity status --format json --no-banner --non-interactive` reported one `ready` instance for the target project and Editor version.
- Native `unity list --project-path C:\Users\sennn\2D_RPG_Project6_git --format json --no-banner --non-interactive` succeeded with a valid catalog of 149 tools. Only catalog validity and count were used as connectivity evidence; no catalog command was executed.
- The pre-refresh Development MCP probe returned `NO_INSTANCE` and `instanceCount=0`. The implementation read top-level `instances`, while the installed CLI returned `data.instances`. The T011 Pipeline parser also raised `UnboundLocalError` because it used `path` before binding it in a comprehension.
- After correcting those parsers, the Development checkout's 25 focused Unity probe tests passed. A direct invocation of the corrected probe returned `DIRECT_MATCH` and `pipelineHandshake.state=CONNECTED`.
- The Development MCP runtime was restarted to load the corrected source. `probe_unity_host_connectivity()` called through Chat → Local Operations Dev then returned `status=OK`, `verdict=DIRECT_MATCH`, `diagnosis=HOST_PIPELINE_CONNECTED`, target project and Editor version matched, and `pipelineHandshake` had `state=CONNECTED`, `catalogValid=true`, `toolCount=149`.

## Route decision

| Route | Evidence | Disposition |
| --- | --- | --- |
| Chat → Local Operations Dev Host → Unity CLI → Pipeline → Editor | Observed live through the existing MCP probe | Standard connectivity route |
| Chat → Codex app-server Worker → Unity CLI | Earlier Worker reported zero instances under `CodexSandboxOffline`; not retested here | Unneeded for connectivity; cause remains unverified |
| Unity CLI stdio MCP server | Documented by the installed Unity CLI skill; not run or configured here | Optional future integration, no demonstrated advantage for this probe |
| Native user shell → Unity CLI | Observed live | Useful local diagnostic baseline |

## Claim boundaries

- **OBSERVED:** Chat-initiated Development Host read-only access reaches the target Editor's Pipeline and obtains a valid `unity list` catalog response.
- **DOCUMENTED:** The installed Unity CLI skill describes `unity list` as read-only introspection and `unity mcp` as a stdio server. Its Windows sandbox guidance describes a separate-account discovery-file ACL failure mode.
- **INFERRED:** Host CLI calls are the simplest practical local route for this environment. The existing probe suffices for connectivity, so no new Local Operations Tool or Unity MCP configuration is needed for this phase.
- **UNKNOWN:** The exact reason for the earlier Worker zero-instance result; repeatability after Editor or Dev service restarts; execution of Unity tests from an Agent. The Host connectivity result does not establish test execution capability.

Next phase may design a separately bounded Unity test route. No Unity tests or commands that modify Editor/project state were run in this investigation.
