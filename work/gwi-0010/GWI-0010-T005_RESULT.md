# GWI-0010-T005 Result

Status: **PASS / ROUTING_DECISION_READY**  
Task: Worker Execution Capability Audit and Validation Routing  
Date: 2026-09-27  
Repository: `github.com/sentokun155/ai-local-operations`  
Branch: `gwi-0010-ai-local-operations`  
Workspace: `C:\Dev\WorkerRoot\worker-01\ai-local-operations`

指定された現在の`work/gwi-0010/GWI-0010-T005_TASK_REQUEST.md`を読み、repo/branchの一致と開始時clean worktreeを確認した。次に実装すべきbounded validation経路を選ぶためのEvidenceが揃った。全capabilityの利用可能性や、将来runnerの実動作をPASSとしたものではない。

## 成果物

- [Capability Matrix / probe ledger](design/t005/GWI-0010-T005_CAPABILITY_MATRIX.md)
- [Validation Routing Decision](design/t005/GWI-0010-T005_VALIDATION_ROUTING_DECISION.md)

Actorはrepository read/edit、read-only Git、準備済み環境での短い検査を担当する。環境準備、network restore、長期test、process/artifact管理はControllerが開始するbounded host toolへ分ける。認証・license acceptance・Human判断はHUMAN_OR_EXTERNALとする。

## 主な新しい観測と制約

- PATHのPythonはDevEnv venvを指し、`python --version`はexit 101。DevEnvのcfgを読めることと、そのinterpreterをWorkerから実行できることは別だった。
- fallback Python 3.12.14は動くがproject要求>=3.13を満たさず、mcpもない。uv cacheの上位一覧は読めるが、offline locked environment readyの証明にはならない。
- dotnet SDK 9.0.201、Node v24.19.0、npm 11.17.0等はversion discovery可能。build/restore能力を確認したものではない。
- このTaskのtool catalogにはLocal Operations Dev/Prodを含む外部familyが見える。repository-only contractとhost-enforced filteringを区別する必要がある。該当toolsは実行していない。
- app-serverのpoll timeoutはprocess cancellationではない。短命Python直接子のtimeoutは確認したが、子孫全体cleanupは未検証。
- Unity標準配置とHub情報は未発見。PATHのunity.exeを6000.1 Editorとは確認できず、Unity readinessは**UNVERIFIED**。license、package、実project testsは未確認。

## 推奨する次の実装

repository-owned validation profileを選び、既存leaseからrepo/cwdを解決するhost validation V0とPython/uv adapterを先行する。PREPAREはvalidation readinessを診断するが、環境不足だけで安全な編集を一律blockしない。venvはWorkerごと、cacheはhost管理とする。Unityは後続の明示的adapterにし、共通のprocess/result管理を利用する。generic shell runnerや製品固有hard-codeは導入しない。

この将来経路はT004の正式suite環境不足を解消し得る。ただし実際のfull suite PASS、tool filteringの判断、repository-only Development E2Eが別途必要である。**T004 HOLDを変更していない。**

## Verification / scope

probe別のcommand、exit、変更有無、出力要約、limitationsはMatrixに記録した。Pythonのcwd/env継承、OS temp roundtrip、短命process timeoutを実測した。

- `python -B -m unittest discover -s tests -p test_execution_boundary.py -v`（bundled Python 3.12.14、process-local PYTHONPATH、bytecode無効）: **2 tests passed**, exit 0。正式環境のfull suite PASSではない。
- native version probes: pwsh/cmd/uv/dotnet/git/node/npm/codexは各exit 0。PATH Pythonのみexit 101。
- Git mutation、network download、app-server filtering調査の再実行はせず、T004記録・現source・現在のpermission/tool catalogを利用した。
- full suite、Development E2E、Unity testsは実行していない。本Taskはaudit/designであり、Task Request §7に従ってcompletion条件にしていない。

最終文書検査: `git diff --check`はexit 0。ただし新規untracked文書は対象にならないため、3成果物を別途UTF-8読取し、local Markdownリンクの実在と末尾空白を確認した。初回の補助checkerはMarkdown hard breakの2空白を誤検出してexit 1となり、checkerを修正して再確認した。製品test failureではない。Git statusで変更が指定3成果物のみであることを確認し、既存source/Task Requestには変更がない。

## Controller follow-up

次Task候補の採否と実行許可を判断する。本TaskからTaskを自動作成していない。成果物はworktreeに残し、Git add/commit/push、finalize、merge、publication、deployment、DevEnv/ProdEnv変更、Worker Pool操作は実行していない。
