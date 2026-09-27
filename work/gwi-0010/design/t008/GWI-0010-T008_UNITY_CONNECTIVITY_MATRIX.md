# GWI-0010-T008 Unity Connectivity Matrix

## Scope and identity

- Task: GWI-0010-T008 — Unity Connectivity Path Investigation
- Repository: sentokun155/ai-local-operations
- Branch: gwi-0010-ai-local-operations
- Prepared commit: 4e258b094c31d47272a100fe7121ef9304a51fac
- Task Request blob: 18f9a7eb78e2d9bb45c9d3e5cdbe5d33bd7ee4d9
- Probe date: 2026-09-27
- Scope: read-only connectivity observations; no Unity command catalog, tests, project mutation, package/config change, or authentication operation.

## Connectivity gate

The gate passed for the sole running Editor instance visible to the current Windows user:

- Unity CLI: 1.0.0-beta.9, executable at C:\Users\sennn\AppData\Local\Unity\bin\unity.exe; SHA-256 325C5F4D0A241121034E0C066B3D6169EF776CD33B73B1489D5C151440C77876.
- Probe: unity status --format json --no-banner --non-interactive.
- Result: success=true; count=1; state=ready.
- Project: C:\Users\sennn\2D_RPG_Project6_git.
- Editor: 6000.3.9f1; PID 5352; reported Pipeline port 7800.
- Independent process observation matched PID 5352 and executable F:\unity\6\6000.3.9f1\Editor\Unity.exe.
- Only one ready instance was reported, so the currently open project is uniquely identified. The Task Request does not pin a project path; the current single instance is used as its intended target.

The status command is a read-only connectivity probe. No Unity command/list/eval, test, or project operation was run.

## Surface matrix

| Surface | Client process | Discovery source | Transport | Connected? | Blocking difference |
|---|---|---|---|---|---|
| Codex-native / Desktop baseline | Human-confirmed Native Codex baseline; current local Codex task shell also invoked the Unity CLI directly | CLI status found one ready Editor for the project above. Existing T006 result records plugin identity unity@unity-agent-plugin, version 0.1.6-beta, and the prior no-instance observation. | Documented model: Unity CLI discovers a per-Editor Pipeline descriptor and connects to the Editor's local Pipeline API. Unity documents the Pipeline API as local HTTP. Exact wire request was not captured. | Current CLI status: yes. The prior Human-confirmed Plugin baseline is accepted as task input, not re-proven here. | The current callable tool catalog contains zero Unity-named tools. The successful probe was CLI-to-Editor, not a call through a Unity Plugin tool wrapper. |
| Local Operations → Codex app-server Worker | A Dev dispatch thread was created, but no Worker ID was assigned and no Worker Pool lease appeared for T008. Dispatch thread 01a0e1bd-6b4c-7c50-86aa-185ee5e37b44, turn 01a0e1bd-6c15-7702-ae61-af6d468db2f5. | No Unity executable lookup or status probe ran in a Worker. The thread status became interrupted / notLoaded before the Unity probe. Worker Pool still showed worker-01 leased to T007 and worker-02 through worker-05 free. | Unknown for the Worker. | Unverified. | The attempt stopped at dispatch/app-server task lifecycle, before executable discovery or Unity transport. This is not evidence that Unity connectivity itself failed. |
| Local Operations Host | Local Operations Dev MCP responded to ping with LOCAL_MCP_OK and returned Worker Pool status. A host-side Unity CLI subprocess was not invoked. | No Host-side Unity discovery evidence was exposed by the current bounded tools. The available callable catalog had no Unity-named tool. | Unity documents unity mcp as an AI-client stdio server that discovers an Editor and uses Pipeline. No such server was launched or registered for Local Operations in this task. | Unverified. | The Host surface exposed no bounded Unity status operation. Configuring the CLI MCP client would write client configuration and was outside this task's boundary. |

## Environment and equivalence

| Property | Current direct CLI surface | Worker | Local Operations Host |
|---|---|---|---|
| Windows user | DESKTOP-U5FJ9NG\sennn | Not observed | Not observed |
| USERPROFILE | C:\Users\sennn | Not observed | Not observed |
| LOCALAPPDATA | C:\Users\sennn\AppData\Local | Not observed | Not observed |
| APPDATA | C:\Users\sennn\AppData\Roaming | Not observed | Not observed |
| HOME | Empty in the current PowerShell process | Not observed | Not observed |
| Unity CLI executable/version/hash | C:\Users\sennn\AppData\Local\Unity\bin\unity.exe; 1.0.0-beta.9; SHA-256 325C5F4D0A241121034E0C066B3D6169EF776CD33B73B1489D5C151440C77876 | Not observed | Not observed |
| Project / Editor PID / version | C:\Users\sennn\2D_RPG_Project6_git / 5352 / 6000.3.9f1 | Not observed | Not observed |
| Pipeline visibility | One ready instance; status reports port 7800 | Not observed | Not observed |

No Worker or Host equivalence is claimed. In particular, identical Windows user, environment directories, executable, project, Editor process, and local transport visibility were not established on those surfaces.

## Evidence and source notes

- The direct status output and matching process identity are observations from this task's current Windows environment.
- The Human-confirmed Native Codex baseline is supplied by the Task Request. The prior repository locator is [GWI-0010-T006_RESULT.md](../../GWI-0010-T006_RESULT.md); it identified unity@unity-agent-plugin version 0.1.6-beta and recorded the earlier no-instance state.
- Unity's official CLI documentation describes the Pipeline package as a local HTTP API: [Unity Pipeline package](https://docs.unity.com/en-us/unity-cli/unity-pipeline/unity-pipeline-package).
- Unity Technologies' official CLI skill documents the stdio MCP server, Editor discovery, and status/descriptor behavior: [Integration and advanced reference](https://github.com/Unity-Technologies/skills/blob/main/skills/unity-cli/references/integration-advanced.md).
- Unity's official plugin README documents the Codex plugin identifier and installation: [unity-agent-plugin](https://github.com/Unity-Technologies/unity-agent-plugin).

Documented transport is distinguished from wire-level observation. The current CLI status response reports a Pipeline port, but this task did not inspect local sockets, named pipes, HTTP requests, or credentials.
