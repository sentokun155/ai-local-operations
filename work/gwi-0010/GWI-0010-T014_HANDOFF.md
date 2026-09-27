# GWI-0010-T014 Human-facing Handoff

Work Identity: `GWI-0010 / Chat→Codex MCP Dispatch / Local Worker Pool`

Task Identity:
- Task Key: `GWI-0010-T014`
- Task Name: `Unity Worker Project Open 起動ライフサイクル修正`
- Stage: `Implementation / Remediation`
- Logical Role: `Implementation Actor`

次担当：Codex app-server Worker

次Task：`open_leased_unity_project`の起動ライフサイクルを修正し、`unity open` timeout後も起動中Editorを観測し、同じWorker projectへのduplicate openを送らないようにする。

依頼文：
- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T014_TASK_REQUEST.md`
- Persistence / Delivery: `REMOTE_REFLECTION_REQUIRED`

重要境界：
- T004どおりWorkerはrepository-only。Unity Editor起動のlive effectはControllerが後続E2Eで行う。
- T013でdefault projectが消えた件はHumanが手動で閉じたため、Toolのclose動作として扱わない。
- real Unity Editorはこの実装Taskで起動しない。
- force push / reset / rebase / merge / Production変更は禁止。

推奨モデル：`gpt-6-luna` / high-to-xhigh reasoning
理由：実装範囲は局所的だが、subprocess timeout・起動中state・idempotenceの非同期境界を正確に扱う必要がある。

Human Next Action: `NO_HUMAN_ACTION_REQUIRED`

このTask RequestをLocal Operations Devからdispatchできる。Handoff自体はAuthorityを追加しない。
