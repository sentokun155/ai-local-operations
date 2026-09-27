# GWI-0010-PROBE-004 Task Request

Task Key: `GWI-0010-PROBE-004`
Task Name: `Codex Subagent Availability Probe`
Stage: `verification`
Role: `diagnostic probe`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-subagent-probe-20260927`

## Goal

Local Operations Dev から app-server 経由で起動された Codex Task で、Codex の multi-agent / subagent 機能が実際に利用可能かを確認する。

## Required action

1. Repositoryのファイルを変更しない。
2. commit / push / branch変更を行わない。
3. このTask contextで利用可能なtool/capabilityを確認し、次のmulti-agent系toolが存在するか判定する。
   - `spawn_agent`
   - `wait_agent`
   - `send_message` または `send_input`
   - `close_agent`
   - その他subagent lifecycle tool
4. `spawn_agent` 相当が存在する場合、read-onlyの子Agentを1体だけ起動する。
5. 子Agentへの依頼は次だけに限定する。
   - Repositoryや外部サービスを変更しない。
   - 現在のTaskがsubagentとして動作していることを確認する。
   - 親へ次の固定文字列を返す:
     `GWI-0010-PROBE-004 SUBAGENT_OK`
6. 親Agentは子Agentの完了を待ち、固定文字列を受領できたか確認する。
7. 子Agentを安全にcloseできる場合はcloseする。
8. 最終応答は次の形式で簡潔に返す。RepositoryへResultファイルは作らない。

```text
VERDICT: PASS | HOLD
SPAWN_AGENT: present | absent
WAIT_AGENT: present | absent
MESSAGE_TOOL: <tool name> | absent
CLOSE_AGENT: present | absent
CHILD_STARTED: yes | no
CHILD_RESULT: <exact child result or none>
NOTES: <brief factual note>
```

## Safety boundary

- Repository変更禁止。
- Git write禁止。
- 外部Chatへの送信禁止。
- GitHub / Drive / Sites等へのwrite禁止。
- generic computer/UI automation禁止。
- nested app-server起動禁止。
- 子Agentは最大1体。
- 対象toolが存在しない場合、代替手段でsubagentを擬似実装せずHOLDする。

## Completion

上記の検証結果を最終agent messageとして返した時点で完了する。
