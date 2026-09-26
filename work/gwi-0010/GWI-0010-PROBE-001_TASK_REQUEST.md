# GWI-0010-PROBE-001 Task Request

Task Key: `GWI-0010-PROBE-001`  
Task Name: `Codex to Chat Connectivity Probe`  
Stage: `verification`  
Role: `connectivity probe`

Repository: `sentokun155/ai-local-operations`  
Branch: `gwi-0010-codex-chat-probe-20260927`

## 1. Goal

Local Operations Dev から起動されたこのCodex Taskが、ChatGPT App Toolsを利用して、このTaskを依頼した元のChatGPTチャットへ疎通確認メッセージを1回だけ返せることを確認する。

## 2. Required action

1. Repositoryのファイルを変更しない。
2. commit / push / branch操作を行わない。
3. ChatGPT App Toolsが利用可能か確認する。
4. 必要ならChat一覧を確認し、このTaskを依頼した直近のGWI-0010 / Local Operations関連チャットを特定する。
5. 特定したチャットへ、次の文字列を**そのまま1回だけ**送信する。

`GWI-0010-PROBE-001 CODEX_TO_CHAT_OK`

6. 送信に成功したらTaskを完了する。

## 3. Safety boundary

- Repository変更禁止。
- shellによる任意の外部送信は禁止。
- ChatGPT App Tools以外でチャットへ送信しない。
- 対象チャットを一意に特定できない場合、別チャットへ推測送信せずHOLDする。
- 複数回送信しない。

## 4. Completion condition

以下のいずれかで終了する。

- PASS: 対象チャットへ指定文字列を1回だけ送信できた。
- HOLD: ChatGPT App Toolsが利用不能、または対象チャットを一意に特定できない。

Repositoryへの成果物保存は不要。
