# GWI-0010-PROBE-012 Controller assessment

Date: 2026-09-27. Scope: Development MCP-dispatched Codex Worker and the running local Unity Editor. Raw Worker observations are preserved separately in `GWI-0010-PROBE-012_RESULT.md`.

## Verdict

**HOLD / DIRECT_WORKER_DESCRIPTOR_ACCESS_DENIED.** The current MCP-dispatched Worker cannot use the installed Unity CLI to obtain a catalog from the running Editor. The observed immediate blocker is read access to the Editor's Pipeline instance descriptor.

## Evidence and interpretation

| Class | Claim |
| --- | --- |
| OBSERVED | The Worker ran as `DESKTOP-U5FJ9NG\CodexSandboxOffline` (SID ending `-1003`). Its exact descriptor read-open failed with `System.UnauthorizedAccessException`, HRESULT `0x80070005`, Win32 error 5. Its CLI `status` returned `STATUS_NO_INSTANCES`; fixed-project `list` returned `COMMAND_FAILED` with no catalog. TCP to `127.0.0.1:7800` succeeded. See the Worker Result for command-level evidence. |
| OBSERVED | Before and after Worker dispatch, the Development Host as `DESKTOP-U5FJ9NG\sennn` reached Editor `6000.3.9f1` for `C:\Users\sennn\2D_RPG_Project6_git`; fixed-project catalog validity and count were 149. The Host descriptor ACL after dispatch had one non-inherited FullControl allow ACE for `sennn` (SID ending `-1001`) and no allow ACE for the Worker SID. |
| DOCUMENTED | Installed `com.unity.pipeline@0.6.0-exp.1` documentation, `Documentation~/connectivity.md`, says the Editor descriptor is `Library/Pipeline/.unity-pipeline-port`, contains the bearer token, and is the only discovery channel. It says every request needs that token, including command execution endpoints. `Runtime/Models/InstanceDescriptor.cs` writes it and restricts permissions to the current user on file creation; heartbeat writes preserve existing permissions. `Runtime/Common/FilePermissions.cs` implements the Windows restriction through `icacls`. |
| INFERRED | The descriptor denial explains why this Worker cannot complete CLI discovery. The observed TCP success rules out a basic loopback connection refusal at that port. The CLI's internal `COMMAND_FAILED` path and any further blockers after changing descriptor access were not independently proven. |
| UNKNOWN | Whether a future, intentionally changed Worker security policy or Editor access design would yield a full CLI handshake. No such change was attempted. |

## Feasibility boundary

Direct Worker CLI access requires the Worker to obtain the descriptor's bearer token through a deliberately authorized access path, or to run with an identity that already has access. Granting descriptor read access also grants access to the token used for Editor command execution; it is not a read-only catalog permission. A one-time file ACL edit would not establish persistence across Editor restart because the file is recreated with current-user-only permissions. No ACL, sandbox, identity, Unity project, Unity MCP configuration, or Production change was made.

The already observed Host route remains available for bounded, authorized Unity operations. It executes Unity CLI in the Host process and is distinct from direct CLI execution inside the Worker sandbox.
