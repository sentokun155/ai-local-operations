# GWI-0010 Runtime / Validation Knowledge

Status: **Active derived operational knowledge**
Work Identity: `GWI-0010`

この文書はT001完了後の実環境確認で得た知見を保存する。
T001 Task Requestそのものを遡及変更するものではなく、以後のruntime remediation / verificationで参照する。

## K01 — Windows OSだけでは実行環境を特定できない

「Windowsで検証した」ことと、「Humanが実際に使うshell/runtimeで検証した」ことは同義ではない。

今回のT001 runtime-script testsは `pwsh` を明示的に起動しており、実質的にPowerShell 7系を検証していた。

Humanの手動実行はWindows PowerShell 5.1 (`powershell.exe`) であり、ここに互換性差があった。

以後、実行環境依存のAcceptance / Completion Reportでは少なくとも次を区別して記録する。

- OS
- shell executable
- shell version
- PSEdition
- relevant text encoding assumptions

「Windows PASS」だけでHuman runtime compatibilityを主張しない。

## K02 — Local Operations operational shell is PowerShell 7

Local OperationsのRepository-backed operational scriptsの正式shellは:

`pwsh.exe` / PowerShell 7+

とする。

Windows PowerShell 5.1 (`powershell.exe`) はLocal Operations operational scriptsの正式サポート対象としない。

理由:

- Repository sourceはUTF-8 BOMなしを通常形式として扱う。
- PowerShell 7はこの形式とnon-ASCII文字を自然に扱える。
- Windows PowerShell 5.1ではUTF-8 BOMなしの非ASCII文字を含むscriptが誤decodeされ、ParserErrorへ連鎖することが確認された。
- 日本語診断文をASCII-onlyへ制限するより、Codex/Work側の既存test runtimeでもあるPowerShell 7へHuman runtimeを揃える方が単純。

## K03 — Observed Windows PowerShell 5.1 failure

`scripts/restart-dev.ps1` をWindows PowerShell 5.1から実行すると、dot-source対象の `scripts/_runtime-common.ps1` が文字化けし、構文解析に失敗した。

観測例:

- 日本語診断文字列がmojibake化
- その後のquote / regex / string tokenまでParserErrorとして連鎖
- `_runtime-common.ps1` がloadされないため `Assert-RequiredCommand`, `Import-RuntimeApiKey` 等が未定義になる
- 後続Git commandの引数も壊れる

これは `CONTROL_PLANE_API_KEY` の値やWorker Pool configの内容が原因ではない。

## K04 — Existing test coverage gap

`tests/test_runtime_scripts.py` のPowerShell testsは `pwsh` が存在する場合にのみ実行される。

したがって現状の:

`test_all_repository_backed_scripts_parse`

が証明するのは「PowerShell 7でparseできる」であり、「Windows PowerShell 5.1でもparseできる」ではない。

今後はtest name / completion reportからverified runtimeを明確に読めるようにする。

## K05 — Human-confirmed local runtime topology

Canonical source:

`sentokun155/ai-local-operations`

Development runtime:

`C:\Dev\DevEnv`

Production runtime:

`C:\Dev\ProdEnv`

Worker Pool root:

`C:\Dev\WorkerRoot`

Worker count:

`5`

Runtime Worker config:

`%LOCALAPPDATA%\LocalOperations\worker-pool.json`

Environment variables:

```text
LOCAL_OPERATIONS_WORKER_ROOT=C:\Dev\WorkerRoot
LOCAL_OPERATIONS_WORKER_POOL_CONFIG=%LOCALAPPDATA%\LocalOperations\worker-pool.json
CONTROL_PLANE_API_KEY=<Windows User environment secret>
```

Worker config本体はmachine-local runtime configurationとし、Repositoryにはexample/schemaだけを置く。

## K06 — User environment variable changes require process restart

Windows User environment variableを追加・変更しても、既に起動済みのTunnel / Local MCP child processへ自動反映されない。

正常な確認順序:

1. local config / User environment variablesを設定
2. 新しい `pwsh` sessionで値を確認
3. Development Tunnel / MCPをrestart
4. ChatGPT側から `get_worker_pool_status` 等で確認

`get_worker_pool_status` の後にrestartするのではなく、restart後のruntime stateを `get_worker_pool_status` で確認する。

## K07 — Separate failure classes

次を混同しない。

### Runtime-script parse failure

例:
- PowerShell 5.1 encoding / parser incompatibility
- common scriptがload不能

この場合、API key / Worker config validationへ到達していない。

### Worker Pool not configured

例:
- `WORKER_POOL_NOT_CONFIGURED`
- runtime processから `LOCAL_OPERATIONS_WORKER_POOL_CONFIG` が見えない

これはMCPが起動・tool invocationまで到達した後のconfiguration HOLD。

### Tunnel / MCP process failure

例:
- stdio child exit
- readiness失敗

これも上記2つとは別classとして扱う。

## K08 — Verification reporting rule

実環境確認を報告するときは、最低限:

```text
OS:
Shell executable:
Shell version:
PSEdition:
Runtime checkout:
Tunnel profile:
Health port:
Worker root:
Worker config path:
```

を必要に応じて記録する。

「実機で検証」「Windowsで検証」だけではHuman operational environmentと一致した証拠にしない。

## K09 — Immediate follow-up implication

GWI-0010の次のremediation / verificationでは:

- PowerShell 7をformal prerequisiteとしてREADME / setup pathへ明示する
- Humanが `pwsh` からoperational scriptsを実行する
- Worker root `C:\Dev\WorkerRoot`, workerCount 5でbootstrapする
- restart後にDev Pluginから `get_worker_pool_status` を確認する
- その後Chat → Dev Plugin → Worker Pool → Codex → Chatの実E2Eへ進む

T001のhistorical Task Requestは変更せず、以後のTask Requestが本知見を参照する。
