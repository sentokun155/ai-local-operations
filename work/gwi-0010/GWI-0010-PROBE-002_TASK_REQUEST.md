# GWI-0010-PROBE-002 Task Request

Task Key: `GWI-0010-PROBE-002`  
Task Name: `Inspect Prior Codex Thread and Tool Availability`  
Stage: `verification`  
Role: `diagnostic probe`

Repository: `sentokun155/ai-local-operations`  
Branch: `gwi-0010-codex-chat-probe-20260927`

## 1. Goal

前回のLocal Operations Dev疎通確認で作成されたCodex threadがcompletedになったにもかかわらず、
Codex Desktop UI上にTaskが見えず、ChatGPT側にも指定メッセージが届かなかった原因を、local evidenceで切り分ける。

Previous thread:
`01a0ded3-ee2b-7da3-a664-d735c10f285f`

Previous turn:
`01a0ded3-ef52-7ca0-8360-ba5f1744ff21`

## 2. Required diagnostics

1. このCodex contextで利用可能なTool / capabilityを確認する。
2. ChatGPT App Toolsに相当する、chat一覧取得・chatへのmessage送信 capabilityが存在するかを確認する。
   - 存在する場合はtool/capability名を記録する。
   - 存在しない場合は明確に absent と記録する。
   - 実際のChat送信は行わない。
3. Installed Codex CLI / app-serverを利用して、可能ならPrevious threadを `thread/read` + `includeTurns=true` でreadする。
4. Previous turnについて、最低限以下を抽出する。
   - turn status
   - user/task inputが到達していたか
   - 最終agent message
   - ChatGPT App Toolsのcall attemptがあったか
   - HOLD / failure reasonが文章として残っているか
5. Codex Desktop UIに表示されない理由について、証拠から判断できる事実と推測を分離する。
6. Previous threadのreadが不可能なら、その理由と試したbounded routeを記録する。

## 3. Safety boundary

- ChatGPT chatへのmessage送信は禁止。
- Repository source codeは変更しない。
- Production / Dev runtime設定を変更しない。
- Worker Pool設定を変更しない。
- branch deletion / reset --hard / clean / force pushは禁止。
- Secret / credential / token / raw auth dataをResultへ記録しない。
- 診断に必要なlocal Codex stateはread-onlyで扱う。

## 4. Result artifact

次へ結果を保存する:

`work/gwi-0010/probes/GWI-0010-PROBE-002_RESULT.md`

Resultには以下を含める:

- Verdict
- Previous thread/turn status
- Previous final agent message（秘密情報を含まない範囲）
- Available ChatGPT-related tool capability
- Tool-call evidence
- Desktop visibilityについて確認できた事実
- Root-cause candidates
- Recommended next diagnostic/fix

## 5. Repository reflection

Result artifactだけをcommitし、同じprobe branchへnormal non-force pushする。

Commit後にremote readbackを確認する。

## 6. Completion

Resultをpushできたら完了する。
