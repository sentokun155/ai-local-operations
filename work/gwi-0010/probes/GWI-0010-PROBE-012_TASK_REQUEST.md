# GWI-0010-PROBE-012 — Dispatched Worker Unity CLI connectivity diagnosis

Task Key: `GWI-0010-PROBE-012`
Work Identity: `GWI-0010`
Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`
Stage: read-only local connectivity investigation

## Goal

From this MCP-dispatched Codex app-server Worker, determine whether the installed Unity CLI can reach the already running Editor for `C:\Users\sennn\2D_RPG_Project6_git`. If not, identify the concrete blocking step with direct evidence. Do not treat `unity status` alone as the verdict.

The Controller observed immediately before dispatch: the Host user `DESKTOP-U5FJ9NG\sennn` reached Editor `6000.3.9f1`, PID 5352, Pipeline port 7800 using CLI `1.0.0-beta.9`; fixed-project `unity list` returned a valid catalog of 149 tools. PID/port are observations, not immutable identity. The Editor's discovery descriptor is `C:\Users\sennn\2D_RPG_Project6_git\Library\Pipeline\.unity-pipeline-port`. The Controller observed it exists and has one non-inherited allow ACE: `DESKTOP-U5FJ9NG\sennn` FullControl. It contains an authentication token; never read or print its contents.

## Worker preflight

Verify the repository root, `gwi-0010-ai-local-operations` branch, and this Task Request from the dispatch manifest before probing. Record only the verified root/branch/commit and Task Request blob in the Result. If these cannot be verified, HOLD without executing Unity probes or editing anything.

## Read-only probe

Use the installed CLI at `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`, if present. Observe, with bounded timeouts and structured JSON where available:

1. Effective Windows user and SID, plus `USERPROFILE`, `LOCALAPPDATA`, and `APPDATA`. Do not enumerate the whole environment.
2. CLI version; `unity pipeline list --format json --no-banner --non-interactive`; `unity status --format json --no-banner --non-interactive`.
3. `unity list --project-path C:\Users\sennn\2D_RPG_Project6_git --format json --no-banner --non-interactive`. Record exit code, envelope success/error code, and whether a valid catalog and tool count were returned. Do not return catalog content, names, schemas, descriptions, or raw stdout/stderr.
4. For the exact discovery descriptor above, record existence/metadata visibility and whether opening it for read succeeds. Close immediately without reading any bytes. Record exception type and HRESULT/Win32 error on failure. Inspect owner/ACL metadata only if available. Do not print descriptor contents, hashes, token, or full ACL beyond relevant identity/rights.
5. Test a short TCP connection to `127.0.0.1:7800` if the Host baseline still reports that port. Close without sending HTTP or authentication data. Record success or concrete socket error. This distinguishes loopback transport from descriptor access; it does not prove authenticated Pipeline access.

If CLI `list` succeeds with a valid catalog for the fixed project, report `PASS / WORKER_DIRECT`. Otherwise report `HOLD / <specific observed blocker>`. Separate observed facts from an inferred cause. In particular, do not claim ACL or loopback causality without the corresponding read/open or TCP evidence. If both descriptor access and TCP succeed but CLI fails, leave the CLI discovery/auth failure unresolved and report its code.

## Bounds

- No sandbox or ACL changes, elevation, impersonation, credential sharing, copied descriptor, policy relaxation, network configuration, Unity MCP configuration, or alternate privileged process.
- No Unity command execution, eval, tests, build, Editor restart, package/asset/project modification, or Production operation.
- No Git commit/push. Do not add a generic runner or new MCP Tool.
- Do not print process command lines, raw CLI output, auth tokens, descriptor bytes, or unrelated files.

Write only `work/gwi-0010/probes/GWI-0010-PROBE-012_RESULT.md` in the leased repository checkout. Include a compact evidence table (`OBSERVED`, `DOCUMENTED`, `INFERRED`, `UNKNOWN`), the verdict, and the smallest supported next step. Final message: `GWI-0010-PROBE-012 <PASS / WORKER_DIRECT | HOLD / reason> — <one-line conclusion>`.
