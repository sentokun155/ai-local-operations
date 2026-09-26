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

## Source of truth and runtime layout

Canonical source:

`sentokun155/ai-local-operations`

Development runtime checkout:

`C:\Dev\DevEnv`

Production runtime checkout:

`C:\Dev\ProdEnv`

Worker Slot内の `ai-local-operations` cloneは**実装作業用**であり、Local MCP runtimeとして直接起動しません。

役割:

- Worker checkout: implementation / commit / push
- `C:\Dev\DevEnv`: candidate revisionのDevelopment MCP実行・検証
- `C:\Dev\ProdEnv`: accepted / main revisionのProduction MCP実行

通常のpromotion:

```text
Worker implementation
→ commit / non-force push
→ DevEnvをcandidate revisionへ安全に同期
→ Development MCP再起動
→ Local Operations Devで検証
→ acceptance / merge
→ ProdEnvをaccepted mainへ安全に同期
→ Production MCP再起動
```

## Development / Production tunnel boundary

Development:

- Plugin: `Local Operations Dev`
- tunnel-client profile: `local-operations-dev`
- runtime checkout: `C:\Dev\DevEnv`
- Tunnel ID: Productionとは別ID

Production:

- Plugin: `Local Operations`
- tunnel-client profile: `local-operations`
- runtime checkout: `C:\Dev\ProdEnv`
- Tunnel ID: Developmentとは別ID

同一Tunnel IDをDevelopment / Productionで共有しません。

## API key

Runtime keyはRepositoryへ保存しません。

標準運用ではWindows User環境変数:

`CONTROL_PLANE_API_KEY`

を利用します。

Development / Productionは同じRestricted Runtime keyを共有してよいものとし、各Tunnelに必要なRead + Use権限を持たせます。将来必要になればDev / Prod別keyへ分離可能です。

起動・再起動scriptはAPI keyを引数として受け取りません。環境変数が存在しない場合はsecret valueを表示せず安全に停止します。

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

## Operational scripts

T001で次をRepository-backedにします。

- `scripts/setup.ps1`
- `scripts/start-all.ps1`
- `scripts/restart-dev.ps1`
- `scripts/restart-prod.ps1`

責務:

### setup.ps1

- Dev / Prod runtime checkoutと必要dependency / profile前提を検証
- `CONTROL_PLANE_API_KEY` の存在を検証
- keyの値を表示・保存しない
- 初期設定不足を明確な診断で停止

### start-all.ps1

- PC起動時等にDevelopment / Productionの両Tunnelを起動
- 二重起動を避ける
- 起動後に各環境のhealth / admin UI確認先を表示

### restart-dev.ps1

- `C:\Dev\DevEnv` をDevelopment runtimeとして使用
- `local-operations-dev` profileを再起動
- candidate branch / revisionを検証可能
- Production process / checkoutを変更しない

### restart-prod.ps1

- `C:\Dev\ProdEnv` をProduction runtimeとして使用
- `local-operations` profileを再起動
- accepted / main revision以外を暗黙利用しない
- Development process / checkoutを変更しない

Source code / Tool Catalog変更後は対象Tunnelを再起動し、ChatGPT WebのPlugin管理から「ツールの更新」を実行します。

## Worker Pool direction

V0では固定数のWorker Slotを利用します。

各Slotにはmanaged Repository群の独立cloneを配置します。

Task dispatch時にはFREE Slotをleaseし、対象Repository cloneだけをCodex cwdとして利用します。

Task完了時はRepository-backed成果とlocal cleanlinessを確認し、安全な場合だけdefault branch等のclean baselineへ戻してSlotをFREE化します。

未保存差分や不整合があれば自動破棄せず `DIRTY` / `QUARANTINED` とします。

Git worktreeはV0の必須実装ではありません。Worker Slot abstractionを維持し、必要性が確認された場合に内部実装を変更します。

Codex Desktop Project登録はWorker routingのAuthorityにしません。Local Operationsが選択した対象Repository rootをCodex app-serverのcwdとして明示します。

## Security boundary

このPluginはgeneric local shellを公開するためのものではありません。

- Toolは用途限定
- server-side validationを必須
- Repository-backed Task RequestをCanonicalとして扱う
- MCP Toolの存在から追加Authorityを推論しない
- force-push / merge / publication / deployment / destructive cleanupを暗黙許可しない
- secretをTool responseへ返さない

## Historical prototype

GWI-0010開始前のprototypeは `C:\Dev\local-mcp` に存在します。

これはmigration inputであり、このRepositoryへ反映されたrevisionより上位のCanonical Authorityではありません。

T001でsecret / credential / runtime stateを除く必要な実装を本Repositoryへ移行し、その後のruntimeはDevEnv / ProdEnvへ分離します。
