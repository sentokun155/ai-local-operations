# GWI-0010-T010 結果

判定: HOLD

## 実装

- 既存の `probe_unity_host_connectivity()` に、Windows Tool Help API を使う読み取り専用の `Unity.exe` プロセス確認を追加しました。返す PID は最大8件、確認するプロセス数は最大4096件です。コマンドラインや環境変数は取得しません。
- `unity pipeline list --format json --no-banner --non-interactive` を追加し、候補数、Safe Mode、コンパイル中、Pipeline 利用不可の状態だけを返します。標準出力・標準エラーと未許可フィールドは返しません。
- 既存の `unity status --format json --no-banner --non-interactive` と T008 の Editor / project / version / ready 判定は維持しました。
- 不在、Pipeline 未検出、Pipeline 候補があるのに status が空、Safe Mode 等、直接一致、未解決を `diagnosis` で区別します。サンドボックス起因とは判定しません。
- モックテストを追加し、PID 上限、コマンドライン非返却、秘密情報の除外、Pipeline timeout / failure の扱いを確認するケースを用意しました。

## 検証

- `git diff --check`: PASS
- `python -m unittest discover -s tests -p 'test_unity_probe.py'`: 未実行。`python` が参照する `C:\Dev\DevEnv\.venv\Scripts\python.exe` は起動できませんでした。`uv python install 3.13 --offline` も必要な実行環境がキャッシュされておらず失敗し、ネットワークが無効なため代替環境を取得できませんでした。
- 実 Unity CLI、Host probe、Dev / Production runtime は実行・変更していません。

focused suite の実行結果を確認できていないため、この Result は HOLD です。

## Controller follow-up

Local Operations が通常の finalize を行った後、Dev runtime refresh を実施してください。その後、Controller Chat が既存の Host probe を1回呼び出します。この Worker は finalize、runtime refresh、Host probe を実行していません。
