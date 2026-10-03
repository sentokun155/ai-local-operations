# GWI-0010-T009 Result

- Status: `PASS` — Host connectivity probe implementation ready
- Prepared commit: `84707b7336e7097922fb2ac577f75b02ce337d94`
- Task Request blob: `b7c64e268257a79566ce51cc59914851084558d4`
- Branch: `gwi-0010-ai-local-operations`

## 実装

`probe_unity_host_connectivity()` を Local Operations MCP に追加しました。引数はありません。Host プロセスの `USERNAME` / `USERDOMAIN`、`USERPROFILE`、`LOCALAPPDATA`、`APPDATA` のみを読み取り、固定 Unity CLI パスが存在するときはそれを優先し、なければ PATH から `unity` を解決します。ディスク全体は検索しません。

実行する subprocess は `unity --version` と `unity status --format json --no-banner --non-interactive` に限定しました。各呼び出しに 8 秒の timeout を設け、shell を介さずに起動します。status JSON は必要なフィールドだけを許可リストで取り出し、未知のフィールド、raw JSON、標準エラー、コマンドライン、資格情報を返しません。返却する instance は最大 32 件です。T008 の project path・Editor version・`ready` 状態への一致判定は、返却上限より前の全 instance に対して行います。

`verdict` は `DIRECT_MATCH`、`NO_INSTANCE`、`CLI_UNAVAILABLE`、`STATUS_FAILED`、`IDENTITY_MISMATCH` のいずれかです。status コマンドが正常終了しても T008 の instance が見つからない場合は `HOLD` を返します。PID と Pipeline port は観測値として返します。

## Unity MCP route observation

インストール済み CLI (`C:\Users\sennn\AppData\Local\Unity\bin\unity.exe`, `1.0.0-beta.9`) の version と `mcp --help` / `mcp configure --help` を確認しました。CLI help では `unity mcp` が stdio MCP server の起動、`unity mcp configure [options] [client]` が AI client 用設定の登録として示されています。Unity の [Integration & advanced reference](https://github.com/Unity-Technologies/skills/blob/main/skills/unity-cli/references/integration-advanced.md) にも stdio server と configure route が記載されています。

この確認では `unity status`、`unity mcp` server、`unity mcp configure` は実行していません。設定変更もありません。

## Verification

- Focused probe tests: `uv run --locked python -m unittest discover -s tests -p test_unity_probe.py -v` — 11 passed.
- Existing non-live unit suites: `test_execution_boundary.py` (2), `test_dispatch.py` (28), `test_production.py` (5), `test_runtime_scripts.py` (8), `test_worker_pool.py` (17) — 60 passed.
- `git diff --check` — passed.
- The live app-server integration test was not run; it dispatches a real app-server turn and lies outside this source/test-only task boundary.

## Connectivity disposition

この Task では Host tool を実機に対して呼び出していません。したがって、Local Operations Host から T008 と同じ Unity Editor に到達できるかはまだ `UNVERIFIED` です。Task Request に記載されたとおり、Controller が変更を finalize し、Human が Dev Plugin catalog を更新した後に tool を呼び出して、T008 direct baseline および PROBE-009 Worker observation と比較してください。Host の結果が一致するまでは `HOST_BRIDGE` を選択しません。
