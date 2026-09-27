# GWI-0010-PROBE-009 Result

## Verdict

`HOLD / NO_READY_INSTANCE`

指定されたread-only statusはUnity instanceを返さず、T008のUnity instanceとの一致を確認できなかった。

## Worker observation

- Windows user: `DESKTOP-U5FJ9NG\CodexSandboxOffline`
- `USERPROFILE`: `C:\Users\sennn`
- `LOCALAPPDATA`: `C:\Users\sennn\AppData\Local`
- `APPDATA`: `C:\Users\sennn\AppData\Roaming`
- PATHから解決されたUnity CLI: `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`
- Unity CLI version: `1.0.0-beta.9` (`--version` exit code `0`)
- Status command: `unity status --format json --no-banner --non-interactive`
- Status exit code: `6`
- Status JSON: `success=false`, `data.count=0`
- Instance count: `0`
- Project path / Editor version / PID / Pipeline port / state: instanceが返らず観測できず

Status出力から上記の必要項目だけを抽出した。raw statusは保存していない。

## T008 comparison

T008 baseline:

- Unity CLI: `1.0.0-beta.9`
- CLI path: `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`
- Project: `C:\Users\sennn\2D_RPG_Project6_git`
- Editor: `6000.3.9f1`
- PID: `5352`
- Pipeline port: `7800`
- State: `ready`

CLI path and version match T008. The Unity instance baseline does not match as an observed result: status returned zero instances, so project path, Editor version, PID, Pipeline port, and ready state could not be compared. The requested PASS condition is not met.

## Blocking difference

Worker status reports zero Unity instances (`success=false`, `count=0`; exit code `6`). No ready instance is available to this probe for comparison with T008.