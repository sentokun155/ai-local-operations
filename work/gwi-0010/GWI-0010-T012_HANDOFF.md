# GWI-0010-T012 Handoff

Work Identity: `GWI-0010`
Task Key: `GWI-0010-T012`
作業名: **Worker専用Unity ProjectをHost MCP経由でOpenする経路の実装**

## Authority

`work/gwi-0010/GWI-0010-T012_TASK_REQUEST.md`

このHandoffは要約です。Task RequestをAuthorityとして実装してください。

## 今回の決定事項

- Worker自身からUnity CLIへ直接接続する方式は採用しない。
- `CodexSandboxOffline` にPipeline descriptor / bearer tokenを読ませない。
- Unity実行経路は **Worker -> Local Operations Host MCP -> Unity CLI -> Pipeline -> Unity Editor** を候補とする。
- Unity Plugin / SkillsはKnowledge sourceとして扱い、Plugin runtimeの再現はしない。
- 現在開いている既定Unity projectはWorker checkoutではないため、対象として扱わない。

## 今回やること

Workerのactive leaseに対応するUnity projectをHost側で解決し、そのprojectを安全にOpenして再識別できるbounded MCP actionを実装する。

候補:

`open_leased_unity_project(worker_id, work_identity, task_key)`

重要条件:

- filesystem pathをWorker入力にしない。
- Worker Pool leaseからproject rootをHost側で解決する。
- Unity project / Editor versionをrepository metadataから確認する。
- installed Unity CLIのsupported open routeだけを使う。
- arbitrary shell runnerを作らない。
- Unity Editor install/upgradeをしない。
- 現在開いている別projectを閉じない。
- target projectをresolved pathで再識別する。
- descriptor/token/raw command lineをWorkerへ返さない。

## 最初のGate

実装を広げる前に、現在のapp-server WorkerからLocal Operations Dev MCP Toolを呼べる経路が存在するか、既存Evidence / catalogから確認する。

利用不能なら実装を続けず、

`HOLD / WORKER_HOST_MCP_UNAVAILABLE`

で止め、どのattachment/configurationが不足しているかをResultへ残す。

## 今回やらないこと

- real Worker Unity projectを実際にOpenするE2E
- Unity asset/source mutation
- EditMode / PlayMode test
- file visibility test
- descriptor ACL変更
- Unity MCP configure
- Worker sandbox/security変更
- Production変更
- Dev/Prod runtime restart

今回はsource/tests/docsまで。

実機E2Eはfinalize + Dev runtime/plugin refresh後にControllerが実施する。

## 最低限読むEvidence

- `work/gwi-0010/probes/GWI-0010-PROBE-012_CONTROLLER_ASSESSMENT.md`
- `work/gwi-0010/probes/GWI-0010-PROBE-012_RESULT.md`
- `work/gwi-0010/GWI-0010-T009_RESULT.md`
- `work/gwi-0010/GWI-0010-T010_RESULT.md`
- `work/gwi-0010/GWI-0010-T011_RESULT.md`
- `src/local_mcp/worker_pool.py`
- `src/local_mcp/unity_probe.py`
- `server.py`

既に確定したACL原因調査を繰り返さない。

## 完了条件

- Task-owned Resultを作成。
- 実行できたtests / 実行できなかったtestsを正確に区別。
- Worker自身ではcommit/pushしない。
- Local Operations finalizeへ引き渡す。
- Final messageはTask Request指定形式に従う。
