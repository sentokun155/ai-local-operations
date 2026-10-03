# GWI-0010-T017 Result — Phase A 読み取り診断

実施日: 2026-10-02 (UTC)

Verdict: `HOLD / WORKER_RUNTIME_VERIFICATION_INCOMPLETE` — Phase Aの観測を記録。T017全体の完了やPhase B実施を示さない。

## Scope / Current Contract

- 対象: `sentokun155/ai-local-operations@gwi-0010-ai-local-operations`。固定commitは `64d77dc0af0e10a738c870d6dfb81a6a2a6b96f0`。実施開始時のremote branch HEADも同一。
- Task Request: `work/gwi-0010/GWI-0010-T017_TASK_REQUEST.md` (blob `b151869aa8d3458f7906e40a00ec4ddbabedf4a`)。対応Handoffは同commitに存在。
- `sentokun155/ai-dev-control#16` はOpen / In Progress。最新取得コメントはT017のprepareのみで、dispatch / 実行済みとはしていない。Handoffの `MANUAL_TRANSFER_REQUIRED` も単独の実行許可とは扱わない。今回のユーザー明示依頼が許可したPhase Aだけを行った。
- remoteおよび既知のDevEnv / ProdEnv / Worker cloneでT017 Resultは見つからなかった。T017の重複Resultはなし。
- 選択cwd `C:\Users\sennn\Documents\Codex\2026-10-02\task-14` は空。別checkout `C:\Dev\LocalOperationsT002E2E` はT002 probe branch (`gwi-0010-t002-dev-e2e-probe-20260927`, `e477c206163ccd88c24ffa2a0eaed3f2df7daadc`) のため変更・branch切替をしていない。

## Read-only Observations

- 今回のPowerShellプロセス: `DESKTOP-U5FJ9NG\CodexSandboxOffline` / SID末尾 `-1003`。`USERPROFILE` / `LOCALAPPDATA` は `C:\Users\sennn`。Host account `DESKTOP-U5FJ9NG\sennn` はSID末尾 `-1001`。shellはPowerShell `7.6.5`, Core。
- Task Request / T004のHost baselineでは `C:\Dev\DevEnv\.venv` のPython `3.13.14` が利用可能。今回のプロセスはHost accountではないため、HostユーザーとしてPythonを再起動してはいない。
- `C:\Dev\DevEnv\.venv\pyvenv.cfg` は `version_info=3.13.14`, `uv=0.12.16`。`home` はHostユーザー配下の `WindowsApps\PythonSoftwareFoundation.Python.3.13_qbz5n2kfra8p0`。この `python.exe` は0-byte ReparsePointで、Host accountにはFullControl、`CodexSandboxUsers`にはReadAndExecute。`CodexSandboxOffline`から直接起動するとAccess Denied。venvの `Scripts\python.exe` もexit 101でbase interpreter起動に失敗した。
- `C:\Dev\DevEnv\.venv` の親/実行ファイルACLには `BUILTIN\Users: ReadAndExecute` がある。よってvenv本体の単純なNTFS execute不足は観測されていない。最初の失敗境界はHostユーザーに紐づくWindowsApps実行alias。AppX activation / user registration / sandbox process policyのどれかまでは読み取り診断だけでは確定できない。
- `python` discoveryは同じWindowsApps aliasを指し、起動はAccess Denied。`py` は未検出。`uv.exe` は `C:\Users\sennn\.local\bin\uv.exe`、version `0.12.16` で起動する。
- `UV_CACHE_DIR` 等のuv path overrideは未設定。`uv cache dir` は `C:\Users\sennn\AppData\Local\uv\cache` を返した。`uv python find 3.13` はexit 2でcache初期化時に `...\cache\sdists-v9\.git` をopenできず、OS error 5 Access Deniedとなり、Python discoveryまで到達しない。cache / `.git` ACLは `CodexSandboxUsers: ReadAndExecute`、Host account: FullControl。uv cache pathにWorker用Modify/Create権限がないことが直接のuv失敗理由。
- `.python-version=3.13`, `pyproject.toml requires-python>=3.13`, `uv.lock requires-python>=3.13` は一致。version不一致を示す証拠はない。

## Runtime Topology

| 案 | Phase Aで分かったこと | 評価 |
|---|---|---|
| Host DevEnv共有 | venvがHostユーザーのWindowsApps aliasとHostのuv cacheを参照 | Workerの実行経路としては不適 |
| Workerごとのvenv | 既知の5つのrepo cloneに標準 `.venv` はない。各venvだけを分けても、実行可能なPython baseとuv cache問題が残る | 可能だがPython配備・保守とdiskを5重化 |
| Dedicated Worker Runtime | WindowsAppsに依存しないHost管理CPython 3.13+を共有read-only実行し、Workerごとのproject venv/cacheを分離できる | 推奨候補。正確な配置先・必要権限はPhase B前に別途決定・検証 |

この推奨は診断上の候補であり、install / environment update / ACL変更を実施したものではない。

## Inventory / Classification

| 対象 | 分類 | 根拠・処置 |
|---|---|---|
| `C:\Dev\DevEnv\.venv` とWindowsApps Python base | `ACTIVE_REQUIRED` | Development Host runtime。Host baselineは3.13.14稼働。Worker identityではalias起動不可。保持。 |
| `C:\Users\sennn\.local\bin\uv.exe` / `C:\Users\sennn\AppData\Local\uv\cache` | `ACTIVE_REQUIRED` | uv 0.12.16は稼働。Host cacheはWorkerから更新不可。削除せず。 |
| `C:\Dev\ProdEnv\.venv` | `ACTIVE_REQUIRED` | Production runtimeのvenvと確認。pyvenv.cfgも同じbase aliasを示す。中身の実行・変更なし。 |
| `C:\Dev\WorkerRoot\worker-01..05` | `ACTIVE_REQUIRED` | T013–T016の作業・証拠保持先。標準repo内 `.venv` は5 cloneとも不在。read-only。 |
| Local Operations config / ledger / logs | `ACTIVE_REQUIRED` / `UNRESOLVED_PRESERVE` | config・dispatch ledger・4 log filesの存在とmetadataのみ確認。config/DB内容とlog内容は読んでいない。ledger最終更新は2026-09-27。 |
| `C:\Dev\local-mcp\.venv` | `UNRESOLVED_PRESERVE` | legacy migration inputにvenvあり。唯一の証拠・参照ではないことを証明していない。 |
| `C:\Users\sennn\Documents\Codex\2026-10-02\task-*` | `UNRESOLVED_PRESERVE` | 複数task directoryあり。現task-14は空、task-15..17等の兄弟directoryも存在。内容と参照関係を調べていない。削除候補にしない。 |

`OBSOLETE_SAFE_TO_REMOVE` と立証できる候補は今回なし。削除・整理は行っていない。

## Parallel Work / Live Status

- Control Issue #16の最新読める記録: T013はworker-01、T014はworker-02のquarantine記録とworker-03 candidate、T015はworker-04、T016はworker-05への割当。並行するT013–T016の作業物には触れていない。
- Local Operations Dev `get_worker_pool_status` は `Tunnel-client has not been seen for 300 seconds` で失敗。worker leaseの現在値は照合できず、Dev Tunnelは再起動していない。
- local Git HEAD (全てbranch名は `gwi-0010-ai-local-operations`; HEADのみ参照しstatus/内容は変更せず): DevEnv `02d6b66939e29813f26a6bf862723af60a85cc1a`; ProdEnv `f732450a440f8c87f5c06a8f35c6d90535bec501`; worker-01 `768722142a8be6a47da67bceb35e8ce514f5f0b2`; worker-02 `6ee00b2f751249971213eabfbebafed7f4a850b1`; worker-03 `3e0e00d41dfc752c7e6c3391f8e01208e686e631`; worker-04 `2b73324ba49a06c3723c49491c52ecfd86dddc22`; worker-05 `7d36aa5fa05ab64d2f5126929922ee224fc7acef`.

## Cleanup / Verification / Remaining Decision

- Phase A観測のみ。Worker Pool dispatch、tests、cleanup、install/update、environment設定変更、ACL/security変更、Production restart、credential値の取得は実施していない。
- Worker Python 3.13+ import/test proofは未実施。Dev Tunnelが停止状態で、Hostユーザーとしての再確認もこの実行環境ではできないため、T017全体のVerdictはHOLD。
- Phase B最小候補: WindowsApps aliasではないCPython 3.13+をWorker専用のHost管理場所に置き、Workerに必要なRead/Executeだけを付与し、SennnのLocalAppData外にWorker-scoped uv cacheを設定する。配置先・権限・process設定の適用は今回の許可範囲外。
- 次に必要なHuman decision / additional permission: Phase BでのPython配備、Worker cache/config設定、必要となる最小ACL方針。広範なACL変更は提案しない。Worker lease確認後に別途bounded verificationを行う。
- ResultはPhase Aの記録のみで、T017完了、T013–T016 disposition、Worker release、Global Acceptanceを示さない。