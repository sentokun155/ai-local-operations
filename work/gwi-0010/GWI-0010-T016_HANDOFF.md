# GWI-0010-T016 Human-facing Handoff

Work Identity: `GWI-0010 / Chat→Codex MCP Dispatch / Local Worker Pool`

Task Identity:
- Task Key: `GWI-0010-T016`
- Task Name: `Unity Open Lifecycle 状態遷移再構成`
- Stage: `Implementation / Remediation`
- Logical Role: `Implementation Actor`

次担当：Codex app-server Worker

次Task：T015で残った9 FAIL / 5 ERRORを、個別patchではなく`open_leased_unity_project`の状態遷移順序を明示して修正する。

依頼文：
- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T016_TASK_REQUEST.md`
- Persistence / Delivery: `REMOTE_REFLECTION_REQUIRED`

中心となる順序：

`lease解決 -> pipeline discovery -> status観測 -> state分類 -> editor availability -> lease再確認 -> open最大1回 -> bounded readiness`

重要条件：
- `openRequestOutcome = NOT_SENT | ACCEPTED | UNCERTAIN` を全返却pathで持つ。
- starting targetへduplicate openしない。
- fatal discovery/status error後にopenへfall throughしない。
- T014/T015のfailing local candidateは使わずremote baselineから修正する。
- Workerはrepository-only。real Unity effectはController follow-up。
- focused testsがPASSするまでpushしない。

推奨モデル：`gpt-6-luna` / xhigh
理由：修正範囲は限定されているが、複数の非同期状態とnegative pathの順序整合が中心となるため。

Human Next Action: `NO_HUMAN_ACTION_REQUIRED`

Local Operations Devからdispatchできる。
