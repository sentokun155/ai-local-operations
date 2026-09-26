# ai-local-operations

Personal Local Operations / Local MCP implementation repository.

このRepositoryは、ChatGPTからSecure MCP Tunnel経由で利用する個人用Local Operations Pluginの**local host implementation**を所有します。

## Canonical scope

- Local MCP server implementation
- bounded MCP tools
- Codex app-server integration
- Codex task dispatch
- DispatchReceipt / duplicate ledger semantics
- Local Worker Pool
- managed repository clone routing
- repository / branch / dirty-state preflight
- worker lease / release / quarantine
- local operational diagnostics and tests

Global GWI lifecycle、Human Decision、auto-dispatch policy、repository ownership routingそのものは `sentokun155/ai-dev-control` が所有します。

Host-independentな共有AI開発workflow / skillは `sentokun155/ai-operations-skills` が所有します。

## Current work

GWI-0010 — Chat→Codex MCP Dispatch / Local Worker Pool

Tracking Issue:
https://github.com/sentokun155/ai-dev-control/issues/16

Current implementation branch:

`gwi-0010-ai-local-operations`

Current entry:

`work/gwi-0010/ENTRY.md`

Current implementation Task Request:

`work/gwi-0010/GWI-0010-T001_TASK_REQUEST.md`

## Current local implementation

GWI-0010開始前のprototypeはローカルの `C:\Dev\local-mcp` に存在します。

このlocal implementationはmigration inputであり、このRepositoryへ反映されたrevisionより上位のCanonical Authorityではありません。

T001で、secret / credential / runtime stateを除く必要な実装を本Repositoryへ移行します。

## Runtime data is not source

次はGit管理しません。

- OpenAI / Tunnel / GitHub等のcredential
- environment secret
- `.env`
- runtime SQLite ledger
- Worker Slot runtime state
- managed repository clones
- Codex credentials / home
- logs / temporary Evidence
- virtual environment / cache

具体的なignore policyは `.gitignore` を参照してください。

## Worker Pool direction

V0では固定数のWorker Slotを利用します。

各Slotにはmanaged Repository群の独立cloneを配置します。

Task dispatch時にはFREE Slotをleaseし、対象Repository cloneだけをCodex cwdとして利用します。

Task完了時はRepository-backed成果とlocal cleanlinessを確認し、安全な場合だけdefault branch等のclean baselineへ戻してSlotをFREE化します。

未保存差分や不整合があれば自動破棄せず `DIRTY` / `QUARANTINED` とします。

Git worktreeはV0の必須実装ではありません。Worker Slot abstractionを維持し、必要性が確認された場合に内部実装を変更します。

## Security boundary

このPluginはgeneric local shellを公開するためのものではありません。

- Toolは用途限定
- server-side validationを必須
- Repository-backed Task RequestをCanonicalとして扱う
- MCP Toolの存在から追加Authorityを推論しない
- force-push / merge / publication / deployment / destructive cleanupを暗黙許可しない
- secretをTool responseへ返さない

## Local runtime

通常起動はSecure MCP Tunnel profile側から行います。

```powershell
tunnel-client run --profile local-operations
```

Tool Catalogを変更した場合はTunnelを再起動し、ChatGPT WebのPlugin管理から「ツールの更新」を実行します。

詳細運用手順はT001で現在のlocal READMEを監査・移行して更新します。
