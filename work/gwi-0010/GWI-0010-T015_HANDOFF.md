# GWI-0010-T015 Human-facing Handoff

Work Identity: `GWI-0010 / Chat→Codex MCP Dispatch / Local Worker Pool`

Task Identity:
- Task Key: `GWI-0010-T015`
- Task Name: `Unity Open Lifecycle 検証失敗修正`
- Stage: `Implementation / Remediation`
- Logical Role: `Implementation Actor`

次担当：Codex app-server Worker

次Task：T014 Host verificationで確定した11件のfailure/errorを、remote committed baselineから修正する。

依頼文：
- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T015_TASK_REQUEST.md`
- Persistence / Delivery: `REMOTE_REFLECTION_REQUIRED`

主要修正：
- `openRequestOutcome` contract
- Pipeline duplicate / wrong-version / starting candidate判定
- starting targetへのduplicate open禁止
- `unity open` timeout後のbounded observation
- transient status retry
- unexpected status error後のopen禁止
- first effect前のlease再確認

重要境界：
- worker-03の失敗candidateは使わず、remote baselineからfreshに修正する。
- Workerはrepository-only。real Unity起動はController follow-up。
- testsがPASSするまでremote reflectionしない。
- force push / reset / rebase / mergeは禁止。

推奨モデル：`gpt-6-luna` / xhigh
理由：修正範囲は局所的だが、非同期state transitionとnegative-pathの整合を同時に直す必要がある。

Human Next Action: `NO_HUMAN_ACTION_REQUIRED`

Local Operations DevからこのTask Requestをdispatchできる。
