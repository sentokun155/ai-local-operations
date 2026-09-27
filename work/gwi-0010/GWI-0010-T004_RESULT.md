# GWI-0010-T004 Result

Status: **HOLD — implementation candidate prepared; required verification incomplete**

Task: Controller-Owned Runtime Effect Separation V0
Date: 2026-09-27
Repository: `github.com/sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`
Workspace: `C:\Dev\WorkerRoot\worker-01\ai-local-operations`

指定された現在の Task Request を読めること、repository / branch の一致、開始時の clean worktree を確認した。Task Request 自体は変更していない。変更は worktree に残している。

## App-server capability investigation

実行したローカル調査:

- `codex --version`: `codex-cli 0.158.0-alpha.2.1`。
- Executable: `C:\Users\sennn\AppData\Local\OpenAI\Codex\bin\faa963e871dd422c\codex.exe`。
- Executable SHA256: `8F0554EDE25BBC5450921897C468B2E84635AA513C5017457997AF0954581F49`。
- `codex app-server generate-json-schema --out <temporary-directory>`: exit 0。`--experimental` を付けずに生成した公開スキーマを確認した。CLI build 自体は alpha であり、stable release と呼んでいない。
- `v2/ThreadStartParams.json`: `config` は自由形式 object、`developerInstructions` と `sandbox` がある。直接の汎用 tool allowlist / denylist はない。
- `v2/TurnStartParams.json`: `disabledPluginIds` があり、指定された Plugin ID 一覧を置換する。`sandboxPolicy` は別 field。外部ツール全体を止める一括 allowlist を確認したわけではない。
- Schema SHA256: ThreadStartParams `E9C6D3CC18D049BFBC0249ADD3808FB8E5A27E1A0B5A423767AAFBC3859A9428`; TurnStartParams `2DFCF68705896FADC344CCFEB2E9FE5A6BCBBB8B9A90CF449CE232B636DAF05A`。
- 現行 `AppServerClient` から `initialize` / `config/read(cwd=repository)` を実行。表示は設定名のみに限定した。`mcp_servers` は空、`plugins` は `video-browser-inspector@personal` のみ、`apps` は値なし。この観測は Controller 側 Plugin や実際の Task tool catalog が空である証明にはならない。

公開設定には MCP server ごとの `enabled`, `enabled_tools`, `disabled_tools`、app の default/per-app enabled 設定がある。[OpenAI configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
Plugin 内 MCP にも個別 policy がある。[OpenAI Plugin packaging](https://developers.openai.com/plugins/build/plugins)
App-server の設定操作については [OpenAI App Server documentation](https://learn.chatgpt.com/docs/app-server) を確認した。

**判定:** 個別の公開 filtering mechanism は存在するため「Codex は tool filtering 非対応」とは結論しない。ただし、この Local app-server route の Local Operations / その他の外部 tools を網羅する設定と、実際の非公開化は未検証。`workspace-write` と external-tool exposure は別の制御であり、sandbox を filtering の証拠にしない。今回 Host-enforced filtering は導入していない。Task Request の B に沿う contract-only candidate を実装したが、A/B の最終適用判定にはこの route での追加確認が残る。この未解決点も HOLD の理由である。

## Implemented separation

通常の dispatch の各 `turn/start` prompt に repository-only execution boundary を付加した。新規 thread だけでなく、既存 thread での rejected-turn retry にも同じ指示が付く。

- Codex: resolved / leased repository 内の source / docs / tests / Task-owned Result の read/edit/test。worktree に変更を残す。
- Local Operations finalize: completed turn の Git commit / normal push。
- Controller Chat: Worker recovery、Production preparation、Tunnel/profile/process restart、runtime promotion の開始判断。
- Task Request に runtime effect が書かれていても normal dispatch から実行権限を生成しない。必要な action は Result と final message に Controller follow-up として返す。

保証は **contract-only; not Host-enforced tool filtering**。ツール名 blacklist による遮断は追加していない。実際の Git / host 操作を機械的に拒否する新しい security boundary ではない。

Controller surface は既存の finalize response の `finalAgentMessage` と `resultLocators` を再利用する。自由文から action graph を生成せず、自動実行も追加していない。重複する finalize / recovery / production 実装はない。

## Changed files

- `src/local_mcp/dispatch.py`: repository-only prompt boundary。
- `tests/test_dispatch.py`: runtime effect を要求する Task Request に対する instruction delivery、原文保持、manifest/cwd、workspace-write、duplicate dispatch の regression test。
- `tests/test_execution_boundary.py`: MCP transport 依存なしの boundary / verbatim follow-up tests。
- `README.md`: actor / persistence / Controller 分離、contract-only の保証範囲、既存 follow-up surface、GWI-0009 Management Plane と Chat callback の scope。
- `work/gwi-0010/GWI-0010-T004_RESULT.md`: 本 Result。

## Verification

Environment: Windows / PowerShell `7.6.5`, `PSEdition=Core`。

標準 Python は `C:\Dev\DevEnv\.venv\Scripts\python.exe` だが、基底の WindowsApps Python 3.13 が起動できなかった。通常の `uv run --offline --locked` も cache access / interpreter 起動で失敗。repository 内の一時 cache / install directory を指定した Python 3.13 取得は network access denied (`os error 10013`) で失敗した。DevEnv や Python 設定を変更していない。

利用可能な bundled Python `3.12.14` で `PYTHONPATH=<repository>/src` を指定し、`python -m unittest discover -s tests -v` による全 suite discovery/execution を1回実行した。

結果: **15 passed / 3 module import errors**, `Ran 18 tests in 34.986s`, exit 1。

- 新規 contract / follow-up tests: 2 passed。
- Production の isolated fixture tests: 5 passed。
- Runtime script tests: 8 passed。
- `test_dispatch`, `test_worker_pool`, `test_live_app_server`: `ModuleNotFoundError: No module named 'mcp'`。
- 生ログ: `tmp/t004-tests.txt`（ignored local diagnostic; commit 対象外）。

この fallback は project requirement の Python >=3.13 を満たさないため、supported environment の full suite PASS として扱わない。新規 dispatch integration test、既存 duplicate/finalize/recovery regression は未実行。`git diff --check` は成功した。

Development E2E は未実行。今回の Actor から Development/Production runtime を起動せず、実 Worker Pool state も操作していない。既存の live suite は finalize/push/release まで含むため、そのまま T004 の repository-only live verification として実行しない。

## Remaining work and Controller follow-up

1. 利用可能な Python >=3.13 と locked dependencies を持つ許可済み検証環境で full unit/integration suite を実行する。現在の15成功を代用しない。
2. Local app-server route の個別 MCP / Plugin / app filtering が Task ごとに自然に適用できるかを完了させる。可能なら実装・request test・観測を追加し、困難なら具体的な limitation を確定する。
3. Controller が Development 側で repository-only harmless fixture の実環境検証を行う。production preparation や Worker recovery を fixture Task に委ねない。
4. 検証後、Controller が `finalize_codex_task` による保存と PR #1 への通常反映を判断する。実装差分は review 用に準備済みだが、**PR #1 acceptance-ready とはまだ主張しない**。

Production 更新 / Tunnel restart / `prepare_production_runtime` / `recover_quarantined_worker` / Git commit・push / merge / publication は実行していない。これらをこの HOLD の解消手段として自動実行しない。
