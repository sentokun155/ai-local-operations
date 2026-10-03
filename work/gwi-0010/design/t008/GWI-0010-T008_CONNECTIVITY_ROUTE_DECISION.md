# GWI-0010-T008 Connectivity Route Decision

## Decision

**E. HOLD — HOLD / CONNECTIVITY_PATH_UNRESOLVED**

The current Unity Editor and Pipeline are ready and uniquely identified from the current direct CLI surface. The evidence does not establish which Local Operations route can reach that same instance:

- The Local Operations Worker probe did not reach Unity. Its dispatched app-server thread was interrupted before the read-only status command, and no Worker lease was recorded for T008.
- The Local Operations Host MCP is healthy, but its available bounded tools do not expose Unity CLI or a Unity MCP endpoint. Host-side process launch and Editor discovery were not observed.
- Unity's official CLI offers a supported stdio MCP server route, but it was not launched or configured for this Host or Worker. This task prohibits client-configuration writes.

Selecting APP_SERVER_DIRECT, HOST_BRIDGE, or SUPPORTED_MCP_ROUTE would therefore claim connectivity that has not been observed. NATIVE_ONLY is also not established because the Worker and Host paths remain unverified.

## Decision inputs

| Candidate | Required evidence | Observed | Decision |
|---|---|---|---|
| APP_SERVER_DIRECT | A Worker can find the same CLI and obtain ready status for the same project, Editor PID, and version. | No Unity probe ran; the dispatched thread stopped before executable discovery. | Not established. |
| HOST_BRIDGE | A bounded Host-side CLI or supported MCP probe reaches that same instance. | Local Operations Dev ping and pool status succeeded; no Host Unity probe is exposed or recorded. | Not established. |
| SUPPORTED_MCP_ROUTE | A supported Unity MCP route is identified and can be selected for Local Operations or app-server use. | Official Unity documentation describes a stdio MCP server backed by the CLI and Pipeline, but no connection from the current Local Operations surfaces was verified. | Candidate for a follow-up, not selected as a connected route. |
| NATIVE_ONLY | Evidence shows only Native Codex can connect after the other routes are actually assessed. | Worker and Host connectivity are unknown. | Not established. |
| HOLD | The route cannot be identified from the available evidence. | The only successful live status probe was from the current direct CLI surface. | Selected. |

## Next bounded task

Resolve the Local Operations execution boundary before any Unity capability or test work:

1. Use one real Dev Worker lease and record whether the Worker starts, resolves the same Unity CLI executable/version, and receives a ready status for the pinned project.
2. If the Worker cannot be probed through an existing bounded route, decide separately whether a narrowly scoped Host-side Unity status operation or the official Unity CLI stdio MCP route should be implemented.
3. Repeat only the read-only status observation on the selected route. Compare project path, Editor PID/version, CLI executable/version, Windows user/profile directories, and Pipeline visibility against this matrix.
4. Keep Unity capability discovery and test execution in a later task after connectivity is established.

No Unity project/package, Local Operations source/runtime, client configuration, authentication, or Worker state should be changed as part of this decision record.
