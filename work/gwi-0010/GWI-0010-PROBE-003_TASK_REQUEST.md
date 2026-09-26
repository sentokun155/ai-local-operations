# GWI-0010-PROBE-003 Task Request

Task Key: `GWI-0010-PROBE-003`
Task Name: `Codex Tool Availability Probe`
Stage: `verification`
Role: `diagnostic probe`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-codex-tool-probe-20260927`

## Goal

このCodex Task contextから利用可能なtool/capabilityを確認し、ChatGPT App Toolsに相当するchat一覧取得・chat message送信能力が存在するかだけを短時間で判定する。

## Required action

1. nested Codex/app-serverは起動しない。
2. 外部Chatへmessageを送信しない。
3. Repository source codeは変更しない。
4. このTask contextで利用可能なtool/capabilityを確認する。
5. ChatGPT関連について、以下をResultへ記録する。
   - chat一覧取得 capability: present / absent
   - chatへのmessage送信 capability: present / absent
   - presentの場合は見えているtool/capability名
6. Resultを次へ保存する。
   `work/gwi-0010/probes/GWI-0010-PROBE-003_RESULT.md`
7. Resultだけをcommitし、このbranchへnormal non-force pushする。

## Safety

- ChatGPTへの実送信禁止。
- Production/Development runtime設定変更禁止。
- Secret/credential/tokenの記録禁止。
- force push / reset --hard / clean / branch deletion禁止。

## Completion

Result push後に完了する。
