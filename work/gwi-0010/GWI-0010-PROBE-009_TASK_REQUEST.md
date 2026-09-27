# GWI-0010 Unity Worker Connectivity Probe

Task Key: `GWI-0010-PROBE-009`
Task Name: `App-server Worker Unity Connectivity Probe`
Stage: `read-only connectivity probe`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

Local Operations Dev から起動された Codex app-server Worker が、現在起動中のUnity Editor / Pipeline instanceへread-onlyで到達できるか確認する。

Capability discovery、Unity test、project変更は行わない。

## T008 baseline to compare

T008でdirect CLI surfaceから次を確認済み。

- Unity CLI: `1.0.0-beta.9`
- CLI path: `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`
- Project: `C:\Users\sennn\2D_RPG_Project6_git`
- Editor: `6000.3.9f1`
- Editor PID: `5352`
- Pipeline port: `7800`
- state: `ready`

PID / portはEditor再起動等で変化し得るため、project path + Editor version + ready状態を主identityとし、PID/portは観測値として比較する。

## Probe

Worker内で次だけ確認する。

1. Unity CLI executable discovery
2. Unity CLI version
3. read-only status:
   `unity status --format json --no-banner --non-interactive`
4. status結果の:
   - success
   - instance count
   - state
   - project path
   - Editor version
   - PID
   - Pipeline port
5. 必要最小限の環境比較:
   - Windows user
   - USERPROFILE
   - LOCALAPPDATA
   - APPDATA
   - PATH上で解決されたUnity CLI path

## Secret handling

- Unity Editor process command line全体を出力しない。
- `accessToken`, token, secret, credential等の値を取得・表示・保存しない。
- environment全体を列挙しない。
- status outputにcredential-like valueが含まれる場合はResultへ保存前にredactする。

## Boundaries

Do not:
- Unity command/list/eval/test
- project/source/assets/packages変更
- Editor起動/停止
- package install/update
- MCP configuration write
- login/license/auth変更
- process command lineのdump
- network設定変更
- Git commit/push
- Production操作
- Worker recovery

## Result

Create exactly:
`work/gwi-0010/probes/GWI-0010-PROBE-009_RESULT.md`

Include:
- `PASS / APP_SERVER_DIRECT` if Worker status reaches a ready Unity instance matching the T008 project + Editor version.
- otherwise `HOLD / <reason>`.
- observed CLI path/version
- observed project/Editor/PID/port/state
- whether T008 baseline matches
- any blocking difference

Final agent message:
`GWI-0010-PROBE-009 <PASS / APP_SERVER_DIRECT | HOLD / ...> — <one-line conclusion>`

Do not commit or push. Local Operations finalize owns Git persistence.
