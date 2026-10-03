# GWI-0010-T011 結果

判定: HOLD

## 実装

- 既存の `probe_unity_host_connectivity()` を拡張し、`unity pipeline list --format json` の `data.summary.instancesInSafeMode` と `data.instances[]` を解析します。候補数、project identity、PID、Safe Mode、Pipeline / package の状態だけを許可リストから返します。
- 固定 project に対して read-only の `unity list --project-path ... --format json --no-banner --non-interactive` handshake を追加しました。返す情報は exit code、envelope success、catalog の形と件数、project identity、制限・検証した error code に限ります。catalog、schema、tool description、生の stdout / stderr は返しません。
- `pipelineHandshake` に `CONNECTED` / `NOT_CONNECTED` / `SAFE_MODE` / `UNRESOLVED` を記録し、status が空でも handshake 成功時は `HOST_PIPELINE_CONNECTED` と診断します。status 観測と T008 の ready identity 判定は維持しました。
- モックテストに公式 JSON の Safe Mode 形、handshake 成功・失敗・timeout、秘密情報と catalog の非返却、Editor と対象 Pipeline が見える場合の診断を追加しました。既存の `DIRECT_MATCH` ケースも残しています。

## 検証

- `git diff --check`: PASS
- `python -m unittest discover -s tests -p 'test_unity_probe.py'`: NOT RUN。設定済み interpreter `C:\Dev\DevEnv\.venv\Scripts\python.exe` を起動できませんでした。利用可能な Python launcher はなく、`uv python find 3.13` も uv cache へのアクセス拒否で停止しました。Python 環境の修復は行っていません。
- Unity CLI、対象 Unity project、Host probe、Dev / Production runtime は実行・変更していません。

テストを実行できず、Host 上の実 handshake も未確認のため HOLD です。

## Controller follow-up

通常の finalize と Dev runtime refresh の後、Controller Chat が既存の `probe_unity_host_connectivity()` を1回呼び出してください。`pipelineHandshake.state` が `CONNECTED` なら `HOST_BRIDGE` を判断し、失敗または未解決なら HOLD を維持してください。この Worker は commit / push / finalize、runtime refresh、Host probe を実行していません。
