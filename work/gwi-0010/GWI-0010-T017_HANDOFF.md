# GWI-0010-T017 Human-facing Handoff

Work Identity: `GWI-0010 / Chat→Codex MCP Dispatch / Local Worker Pool`

Task Identity:
- Task Key: `GWI-0010-T017`
- Task Name: `Worker Python Runtime 診断とHost環境整理`
- Stage: `Investigation / Host Maintenance`
- Logical Role: `Host Maintenance / Investigation Actor`

次担当：**Desktop Codex**

次Task：
Hostでは動くPython 3.13.14がCodex Workerでは起動できず、`uv`もcache access deniedになる原因をHost側から診断する。同時にlocal Python/uv/Codex/legacy runtime artifactをinventoryし、安全性が証明できたものだけ整理する。

依頼文：
- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T017_TASK_REQUEST.md`
- Persistence / Delivery: `REMOTE_REFLECTION_REQUIRED`
- Execution Surface: Desktop Codex。Local Operations Worker Poolへdispatchしない。

重要条件：
- 最初はread-only diagnosis / inventory。
- cleanupは`OBSOLETE_SAFE_TO_REMOVE`に分類できたものだけ。
- `C:\Dev\WorkerRoot\worker-01..05` のT013–T016状態は削除・reset・cleanしない。
- `C:\Dev\ProdEnv`はread-only。
- secret値を表示・保存しない。
- Host共有venv / per-Worker env / dedicated Worker runtimeを実測比較し、最小で安定した構成を選ぶ。
- 最終的にHumanのPowerShell操作なしでWorker contextからPython 3.13+ verificationが起動できることを実証する。

推奨モデル：Desktop Codexで利用可能な高推論設定
理由：Windows ACL / process identity / Python / uv / filesystem / runtime topologyを横断して実環境を調べるHost調査であり、Worker sandbox自身からは観測しづらい。

Human Next Action: `MANUAL_TRANSFER_REQUIRED`

Desktop Codexで上記Repository / branchを開き、Task Requestを実行してください。
このHandoffの提示はdispatch / execution済みを意味しない。
