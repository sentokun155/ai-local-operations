# GWI-0010-PROBE-012 Result

**Verdict: HOLD / DESCRIPTOR_READ_ACCESS_DENIED.** この Worker から固定プロジェクトの Unity CLI catalog は取得できなかった。descriptor の read-open はアクセス拒否となった一方、Host が dispatch 直前に報告した port への TCP 接続は成功した。

## Preflight

| Item | Verified value |
| --- | --- |
| Repository root | `C:\Dev\WorkerRoot\worker-01\ai-local-operations` |
| Branch | `gwi-0010-ai-local-operations` |
| Commit | `d01cd4933834cf533414c5ef298702524b9b8a42` |
| Task Request blob (`HEAD:work/gwi-0010/probes/GWI-0010-PROBE-012_TASK_REQUEST.md`) | `554fc5431e64522c27e906b5ea6080da1464ae78` |

The worktree Task Request matched the committed blob before probing.

## Evidence

| Kind | Evidence |
| --- | --- |
| OBSERVED | Effective user: `DESKTOP-U5FJ9NG\CodexSandboxOffline`; SID: `S-1-5-21-1083097524-253295874-3483930368-1003`. `USERPROFILE=C:\Users\sennn`; `LOCALAPPDATA=C:\Users\sennn\AppData\Local`; `APPDATA=C:\Users\sennn\AppData\Roaming`. |
| OBSERVED | Installed CLI exists at `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`; `--version` exited 0 and reported `1.0.0-beta.9`. Each CLI probe used a bounded timeout and captured output in memory without returning raw stdout or stderr. |
| OBSERVED | `unity pipeline list --format json --no-banner --non-interactive`: exit 0, JSON `success=true`, `instances=[]` (0 instances). |
| OBSERVED | `unity status --format json --no-banner --non-interactive`: exit 6, JSON `success=false`, error code `STATUS_NO_INSTANCES`, 0 instances. This status alone is not the verdict. |
| OBSERVED | Fixed-project `unity list --project-path C:\Users\sennn\2D_RPG_Project6_git --format json --no-banner --non-interactive`: exit 6, JSON `success=false`, error code `COMMAND_FAILED`; no valid catalog or tool count returned. |
| OBSERVED | Descriptor `C:\Users\sennn\2D_RPG_Project6_git\Library\Pipeline\.unity-pipeline-port` exists; file metadata was visible (length 571 bytes; last write `2026-09-27T10:45:32.6039165Z`). Opening it for read without reading bytes failed with `System.UnauthorizedAccessException`, HRESULT `0x80070005`, Win32 error 5. ACL metadata inspection also failed with `System.UnauthorizedAccessException`, HRESULT `0x80070005`; owner and ACEs were unavailable from this Worker. |
| OBSERVED | Short TCP connection to `127.0.0.1:7800` succeeded and was closed without sending data. This establishes loopback transport only. |
| DOCUMENTED | The Task Request records the Controller's immediately pre-dispatch Host observation: user `DESKTOP-U5FJ9NG\sennn` reached Editor `6000.3.9f1` and a 149-tool fixed-project catalog through CLI `1.0.0-beta.9`; the descriptor had one non-inherited allow ACE for that Host user with FullControl. PID 5352 and port 7800 were observations, not immutable identity. |
| INFERRED | The Worker identity's denied descriptor read is a concrete discovery/access blocker consistent with the CLI reporting no instances. The successful TCP probe does not establish authenticated Pipeline access. |
| UNKNOWN | Whether the CLI's `COMMAND_FAILED` is caused solely by descriptor access; the Worker's direct ACL owner/ACE view; whether the Host PID and port remained unchanged after dispatch. |

## Smallest supported next step

Controller follow-up, **not executed**: inspect the descriptor ACL under the Host identity against the observed Worker SID, then choose an authorized way for this Worker to read the descriptor and repeat the single fixed-project `unity list` probe. No ACL, sandbox, runtime, or Unity project change was made in this task.
