# GWI-0010-T005 Capability Matrix

Date: 2026-09-27 (JST)  
Scope: `github.com/sentokun155/ai-local-operations`, branch `gwi-0010-ai-local-operations`  
Observed checkout: `C:\Dev\WorkerRoot\worker-01\ai-local-operations`  
Observed HEAD: `96d33c332f6fffabb05d36ac1a52ae173ab02d6f`（観測識別子。開始条件のpinではない）

## 読み方

ACTOR_LOCAL = このWorkerの通常Task内で扱う範囲、HOST_EXECUTED = Controllerが明示的に開始するbounded host処理、HUMAN_OR_EXTERNAL = 認証・判断・未対応操作。推奨routeは実装済みを意味しない。未実測は不可と同義ではない。

Current observations、repository source、T004 historical Evidence、公式仕様、設計判断を区別する。本TaskではGit mutation、外部runtime変更、Unity project起動、dependency install、GUI操作を行っていない。

## Evidence / probe ledger

以下は必要な出力を抜粋した観測記録であり、生ログではない。shellはWindows 10.0.26200.9550、PowerShell 7.6.5 Core。native version probeはbundled Pythonの`subprocess.run(..., capture_output=True, text=True, timeout=10)`でも終了コードを個別確認した。

| ID | Command / probe | Exit / outcome | Persistent mutation | Relevant output / limitation |
|---|---|---|---|---|
| P01 | `Get-Location`; `git remote -v`; `git branch --show-current`; `git status --short`; 指定Task Requestの`Get-Content -Raw` | batch exit 0、全出力確認 | 意図した変更なし | root / origin / branch一致、開始時status空、指定ファイル読取成功 |
| P02 | `git rev-parse --show-toplevel HEAD`; `git log -1 --format='%h %s'`; `git diff --stat`; `git show HEAD:pyproject.toml` | batch exit 0、全出力確認 | 意図した変更なし | HEAD上記、差分空、Python >=3.13。Git内部の任意refreshまで監査したものではない |
| P03 | `Get-Command` for pwsh/cmd/python/uv/dotnet/MSBuild/Unity/git/node/npm/codex | 読取成功 | なし | 下記path表。MSBuildはPATHなし |
| P04 | `pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'`; `cmd /d /c ver` | 各0 | 意図した変更なし | 7.6.5 / Windows 10.0.26200.9550 |
| P05 | `python --version`; DevEnv `.venv/pyvenv.cfg`読取 | python 101、cfg読取成功 | なし | PATHのDevEnv venvからprocessを生成できない。cfgは3.13.14、WindowsApps base |
| P06 | bundled `python -B -c`でsys.version、`find_spec('mcp')` | 0 | なし | Python 3.12.14、mcp_available=False |
| P07 | `uv --version`; `uv cache dir`; cache直下の`Get-ChildItem -Name` | native各0、列挙成功 | 意図した変更なし | uv 0.12.16、cacheにarchive-v0/builds-v0/interpreter-v4/sdists-v9/simple-v25/wheels-v6。対象lockの全依存がある証明ではない |
| P08 | `dotnet --list-sdks`; `Test-Path` SDK内MSBuild.dll | 0 / True | 意図した変更なし | SDK 9.0.201。build/restore/MSBuild実行は未確認 |
| P09 | `git --version`; `node --version`; `cmd /d /c 'npm --version'`; `codex --version` | 各0 | 意図した変更なし | 2.49.0.windows.1 / v24.19.0 / 11.17.0 / 0.158.0-alpha.2.1 |
| P10 | `Test-Path` standard Unity Editor/Hub locations、Hub editors-v2.json; PATH unity.exeのVersionInfo | 読取成功 | なし | 標準3箇所はFalse。PATH binaryはProduct=unity、Version=1.0.0。Editor 6000.1の存在証明ではない。非標準全ドライブ探索なし |
| P11 | `git check-ignore .venv/probe tmp/t005-probe logs/t005-probe Library/probe` | 0 | なし | 最初の3つのみignored。Libraryは出力なし。ignoreはwrite permissionではない |
| P12 | bundled Pythonでharmless markerを子processに渡しcwd/stdout/returncode確認 | 0、child 0 | process-local envのみ | cwdは対象repo、T005_MARKER=harmless。秘密environmentを列挙していない |
| P13 | `tempfile.gettempdir()`内の一意`t005-<pid>.txt`にwrite/read/unlink | 0 | 一時ファイル作成後削除 | roundtrip=True、removed=True。任意repository外writeの許可を意味しない |
| P14 | bundled Python `subprocess.run([python,'-B','-c','import time; time.sleep(0.4)'], capture_output=True, timeout=0.05)` | TimeoutExpiredを捕捉、probe 0 | なし | 直接子のtimeout/kill/wait経路のみ。孫process、tool cancellation、Unity hangは未実測 |
| P15 | `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=<repo>/src`, bundled `python -B -m unittest discover -s tests -p test_execution_boundary.py -v` | 0 | process-local envのみ | 2 tests OK、0.001s。Python >=3.13 full suiteの代用ではない |
| P16 | `Get-Item .,.git -Force`のAttributes/LinkType | 成功 | なし | root=Directory、.git=Hidden/Directory、LinkType=null。symlink/junction作成や境界越えは試していない |
| P17 | このturnの宣言済みtoolsと`ALL_TOOLS`の名前のみ列挙 | 成功（shell exit対象外） | なし | exec/apply_patch、web、CUA、collaboration、image、GitHub/Drive/plugin管理、Local Operations Dev/Prod familiesが見える。呼出成功は未検証 |
| P18 | T005成果物作成と最終`git diff --check`、status、必要項目確認 | Result参照 | 指定成果物3ファイルのみ | repository writeを直接確認。runner/source変更なし |

Version/path discovery対象:

| Command | Resolved path / observation |
|---|---|
| pwsh | `C:\Users\sennn\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe` |
| cmd | `C:\WINDOWS\system32\cmd.exe` |
| python (PATH) | `C:\Dev\DevEnv\.venv\Scripts\python.exe` |
| python (bounded fallback) | `C:\Users\sennn\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe` |
| uv | `C:\Users\sennn\.local\bin\uv.exe` |
| dotnet | `C:\Program Files\dotnet\dotnet.exe` |
| MSBuild | PATHなし、`C:\Program Files\dotnet\sdk\9.0.201\MSBuild.dll`は存在 |
| Unity | `C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`。Editorと未同定 |
| Unity Hub | PATHなし、`C:\Program Files\Unity Hub\Unity Hub.exe`なし |
| Git | `C:\Program Files\Git\cmd\git.exe` |
| Node / npm | `C:\Program Files\nodejs\node.exe` / `npm.ps1` |
| Codex | `C:\Users\sennn\AppData\Local\OpenAI\Codex\bin\faa963e871dd422c\codex.exe` |

Discoveryには、標準Editor root `C:\Program Files\Unity\Hub\Editor` と `%APPDATA%\UnityHub\editors-v2.json` も使用し、どちらも未発見。ライセンス・credentialファイルは読んでいない。

補助探索で存在しない`work/gwi-0010/design/t004`をrgに渡した際はpath missingとなった（他の読取と同じshell全体ではexit 1、rg単体のexit未記録）。T004の指定Taskを代替したものではなく、実在するT004 Resultを読んで調査を継続した。初回PowerShell表出力は型の混在によりpath欄が省略されたため、pathをJSON出力して確認した。これらをcapability failureに数えない。

### Reused evidence / source

- H01: [T004 Result](../../GWI-0010-T004_RESULT.md)。`uv run --offline --locked`失敗、cache/interpreter問題、Python取得時`os error 10013`、fallback suite 15 passed / 3 import errors。今回network/restore試行を繰り返していない。歴史的probeごとのexit値は同Resultに全て残っておらず、未記載の値を推定しない。
- H02: 同Resultのapp-server公開schema/config調査。`ThreadStartParams.config`、`TurnStartParams.disabledPluginIds`、個別filterと実Task catalogの区別。CLI versionはP09と一致するがschema hashの再照合はしていない。
- S01: [dispatch.py](../../../../src/local_mcp/dispatch.py): thread/startはcwd、runtimeWorkspaceRoots、workspace-write、approvalPolicy=never。turn/startにdisabledPluginIdsを設定していない。wait_for_turn_completedのtimeoutはNoneを返すだけ。closeは直接processのterminate/killと2秒waitで、子孫全体の終了証明なし。
- S02: [finalize.py](../../../../src/local_mcp/finalize.py)、[worker_pool.py](../../../../src/local_mcp/worker_pool.py)、[VALIDATION_KNOWLEDGE.md K11](../../VALIDATION_KNOWLEDGE.md)。Git persistence / PREPAREはhost側の責務。今回呼び出していない。
- C01: このturnのpermission profileはrepo worktreeとtempへのwrite、.git/.agents/.codexはread、approval never、network restricted。任意repository外writeやGit mutationで再確認しない。

## Capability matrix

| Capability | Observed Actor-local status | Evidence | Limitation | Recommended route |
|---|---|---|---|---|
| repository read | 可 | P01/P02 | このrepoのみ | ACTOR_LOCAL |
| repository worktree write | 可 | P18 | .git等保護対象を含まない | ACTOR_LOCAL |
| repository外read | 一部可 | P05/P07/P10 | cfg/metadataのみ。全領域読取を保証しない | ACTOR_LOCALの必要最小限discovery |
| repository外write | temp以外は許可しない | C01 | 実write denial probe未実施 | HOST_EXECUTEDの所有領域、例外はHuman |
| OS temp | write/read/delete可 | P13 | 自作1ファイル、容量上限未測定 | ACTOR_LOCAL bounded temporary use |
| symlink / junction | 現rootと.gitは非link | P16 | 作成・追跡・sandbox境界はUNVERIFIED | hostでresolved containment確認。link経由の権限拡張なし |
| ignored files | ignore判定可 | P11 | ignoreだけで秘密や大容量を安全にしない | ACTOR_LOCAL限定生成物、host artifacts |
| large/generated artifacts | 小ファイルのみ実測 | P13/P18 | disk budget/performance未測定、Library未ignore | HOST_EXECUTEDで容量と保存先管理 |
| Git status/diff/log/show/rev-parse | 可 | P01/P02 | local read-only | ACTOR_LOCAL |
| Git add / commit | 今回未実行、.git read-only | C01/H01 context | mutating probe禁止。機能不良と断定しない | HOST_EXECUTED finalize |
| branch checkout/switch | 未実行 | S02/C01 | active Actorから切替しない | HOST_EXECUTED PREPARE |
| fetch | 未実行 | S02/C01 | Git metadata/network双方が必要 | HOST_EXECUTED PREPARE |
| push | 未実行 | S02/Task禁止 | credential/networkの実経路未検証 | HOST_EXECUTED finalize、別の明示的authority |
| PowerShell / cmd | 起動可 | P04 | operational scriptsはpwsh 7+ | ACTOR_LOCAL bounded command |
| Python PATH | 起動不可 | P05 | DevEnvへのpath依存、baseの起動不能 | HOST_EXECUTED準備、per-worker venv |
| Python fallback | 起動/限定tests可 | P06/P15 | 3.12はproject非対応、mcpなし | ACTOR_LOCAL診断のみ |
| uv executable | 起動可 | P07 | uv実行可とlocked env可は別 | ACTOR_LOCAL version、HOST_EXECUTED setup |
| dotnet / MSBuild | SDK列挙可 / DLL存在 | P08 | compile/restore未確認 | 準備済みならACTOR_LOCAL bounded test、restoreはhost |
| Node/npm | version可 | P09 | install/test未確認 | 準備済みbounded testはActor、installはhost |
| Codex CLI | version可 | P09 | 新規app-server/actorは起動せず | ACTOR_LOCAL discovery、dispatchはController |
| Unity Editor / Hub | 標準配置で未発見 | P10 | PATH unityは6000.1 Editorの証拠でない | HOST_EXECUTED discovery/adapter |
| uv cache access | top-level read可 | P07/H01 | lock/write/必要wheel全量は不明 | host-managed uv cache |
| offline locked dependencies | 成立未確認、T004で失敗 | H01/P05/P06 | cache名一覧だけでoffline readyにしない | HOST_EXECUTED preflight + provision |
| DevEnv venv共有 | 不適切、PATH起動失敗 | P05 | 別repo/editable install/同時変更リスク | 共有しない、per-worker環境 |
| outbound / registry download | restricted、T004 download拒否 | C01/H01 | 全endpointの到達不能証明ではない | HOST_EXECUTED authorized restore |
| Git remote network | origin設定は確認、通信未試行 | P01/S02 | remote設定≠接続成功 | host Git route、connectorは別経路 |
| MCP/app/plugin exposure | 複数familyが見える | P17/H02 | visible≠authorized≠call succeeded | Actorはrepository-only、runtime toolsはController |
| per-task filtering | schema/configの機構あり、現route未適用 | H02/S01 | 全family非公開化はUNVERIFIED | Controllerの別bounded検証 |
| cwd/environment inheritance | repo cwd、harmless marker継承 | P12 | 全environmentを読んでいない | ACTOR_LOCAL。hostは必要envだけ渡す |
| short process timeout/output | direct child timeout捕捉、stdout/exit回収 | P12/P14 | tool session yieldはdeadlineではない | ACTOR_LOCAL短期、host長期 |
| cancellation / descendants | 実測不足 | P14/S01 | parent kill、poll timeoutはtree cleanupでない | HOST_EXECUTED tracked process tree |
| long-running validation | 未実行 | S01/Task禁止 | Editor/restore/test runnerの残存・hang未検証 | host start/poll/cancel、lease維持 |
| GUI/login/license/judgment | 未実行 | Task禁止 | tool exposureは利用権限でない | HUMAN_OR_EXTERNAL |

## Network / tool boundary

公式資料取得はweb tool経由で成功したが、Worker shellのoutbound許可を証明しない。GitHub connectorもshell Gitとはcredential・transportが異なる。Local Operations Devにはdispatch/finalize/status/recovery/production preparation、Production名にもdispatch/pingがこのTaskのcatalogに現れた。どれも本Taskでは呼び出していない。

OpenAIの公式設定にもMCP/app/plugin単位の制御がある。ただし設定機構の存在と、このdispatchで非公開化できたことは別である。[Configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)

## 結論

Pythonだけを直すと、Unityの長期process・license・生成物・network restoreと同じ問題が再発する。source編集と軽い検査をActorに残し、必要環境の準備と長期検証をhostに分離する根拠は揃った。Host route自体の実行能力とUnity readinessは未検証であり、次Taskの受入条件にする。
