# GWI-0010-T002 Task Request

Task Key: `GWI-0010-T002`  
Task Name: `Codex Result Persistence and Intake V0`  
Stage: `implementation / integration`

Repository: `sentokun155/ai-local-operations`  
Branch: `gwi-0010-ai-local-operations`  
Tracking Issue: https://github.com/sentokun155/ai-dev-control/issues/16  
Draft PR: https://github.com/sentokun155/ai-local-operations/pull/1

## 1. Goal

T001で成立した Fixed Local Worker Pool / logical repository routing / Codex app-server dispatch に、Codex完了後の **Git persistence / Result Intake** を追加する。

正常系は次の単純な流れとする。

```text
Chat
→ Local Operations: Worker確保・指定branchを最新化
→ Codex: worktree編集・test・Result
→ Local Operations: commit・non-force push
→ Local Operations: Codex最終応答とcommit情報をChatへ返す
→ Worker FREE
```

Codexには `.git` 更新、commit、push、ChatGPT通常chatへの直接送信を要求しない。

Local Operationsはpersonal local toolである。customer-facing production serviceのようなrelease gate、revision pin、promotion discipline、過剰なEvidence、細粒度state machineを追加しない。

## 2. Current facts to preserve

実装前に root `AGENTS.md`, current source/tests, `work/gwi-0010/VALIDATION_KNOWLEDGE.md` と本Task Requestを読む。

確認済み:

- Local Operationsから起動したworkはCodex Taskとして表示される。
- observed Codex TaskにはChatGPT chat一覧取得 / chat送信専用Toolがない。
- Codex subagentは利用可能。
  - `spawn_agent`: present
  - `wait_agent`: present
  - `send_message`: present
  - PROBE-004 child result: `GWI-0010-PROBE-004 SUBAGENT_OK`
- Codexは `workspace-write` でworktree fileを編集できる。
- observed Windows environmentではCodex自身の `git add` が `.git/index.lock` 作成拒否で失敗した。
- dirty worktreeを現行releaseへ渡すとlocal成果を削除せずQUARANTINEDになる。

T001 historical Task Requestは変更しない。

## 3. Runtime

Current personal runtime:

- Development: `C:\Dev\DevEnv`
- Production: `C:\Dev\ProdEnv`
- Worker root: `C:\Dev\WorkerRoot`
- Worker count: `5`
- Worker config: `%LOCALAPPDATA%\LocalOperations\worker-pool.json`
- Supported operational shell: PowerShell 7+ / `pwsh.exe`

Dev / Prodを分ける目的はPlugin/process collisionを避けること。Production向けの厳格なpromotion gateやimmutable checkout disciplineは本Taskの要件にしない。

T002の動作確認はDevelopment Pluginで行えばよい。Production更新はT002の完了条件ではない。

## 4. Remove over-strict identity gating

通常のDevelopment taskで次を要求しない。

- expected starting HEADの固定
- expected Task Request blob IDの事前指定
- branch HEAD完全一致を開始条件にすること
- local/remote revision equalityを独立したacceptance gateにすること
- Task開始前の冗長なreadback

Task Requestはcurrent requested branch上のcurrent fileを読む。

Local Operationsが防ぐべきなのは、実害のある誤配送だけ:

- configured logical repositoryと対象cloneが明らかに異なる
- requested branchを取得/checkoutできない
- Workerが別Taskに利用中
- 前Taskの未保存local changesが残っている

それ以外のrevision差は、通常のfetch/updateで解消する。

## 5. PREPARE — Local Operations

FREE Workerを1つ確保し、対象Repositoryを次のTaskで使える状態にする。

正常系:

1. logical repositoryからWorker内の対象cloneを解決。
2. `git fetch origin`。
3. requested branchへcheckout。
4. remote branchが存在し、clean local branchをfast-forwardできるなら最新化。
5. 対象Repository rootをCodex cwdとしてdispatch。

Task Requestはrequested branch上のcurrent Repository-backed fileを読む。

開始を止めるのは、主に次の場合だけ:

- WorkerがFREEではない
- target cloneが対象Repositoryではない
- requested branchを取得できない
- 前Taskの未保存変更が残っている
- non-destructiveに通常同期できない

WorkerはTask完了後にdefault branchへ戻す必要はない。FREE Workerがどのbranchにいるかは状態ではなく、次回PREPAREがrequested branchへ切り替える。

既存T001実装に過剰なidentity / clean-baseline gateがあり、この領域をT002で触る場合は例外追加ではなく簡素化する。

## 6. EXECUTE — Codex

Codexの責務:

- Task Requestを読む
- 必要なsource / docs / tests / Resultを変更
- test / verification
- 必要ならsubagentを使用
- final agent messageを返す
- turnをcompletedにする

Codexの責務に含めない:

- `git add`
- `git commit`
- `git push`
- ChatGPT通常chatへの直接送信

force push / merge / deployment等は本Taskとは無関係であり、追加権限を与えない。

## 7. PERSIST — Local Operations

Codex完了後、Local OperationsがworktreeをGitへ反映する。

用途限定Toolを追加する。Candidate name:

`finalize_codex_task`

不要にToolを分割しない。

### 7.1 Input

最低限:

- `worker_id`
- `work_identity`
- `task_key`

local absolute pathやexpected commit/blobをChatへ要求しない。

### 7.2 Finalize flow

1. 指定Workerが指定Taskを実行していたことを確認。
2. app-serverでtarget turnがcompletedか確認。
3. target Repositoryのworktree変更を取得。
4. 変更が無ければcommitせずResult Intakeへ進む。
5. 変更があれば、ignored filesを除き通常の `git add -A`。
6. Task identityが分かるcommit messageでcommit。
7. current requested branchへ通常のnon-force push。
8. push成功後、commit SHAとCodex final messageをResultとして返す。
9. worktreeがcleanならWorkerをFREEにする。

pushがrejectされた場合は成果を残してエラーを返す。force/rebase/resetで自動解決しない。

### 7.3 Minimal safeguards

追加するguardは実害のあるものだけにする。

維持:

- force pushしない
- remote/upstreamを変更しない
- credential / runtime secretを明示的にcommitしない
- 他TaskのWorkerをfinalizeしない
- push失敗時にlocal成果を削除しない

不要:

- sibling Repository全件の完全不変チェック
- remote advancementの事前/事後二重検証
- commit後の全critical file readback
-細粒度path allowlist policy engine
- default branchへの復帰gate
- Production promotion gate
- 理論上の完全性だけの追加state

## 8. RESULT INTAKE

Local Operationsが `thread/read` を利用してCodexのtarget turnを読む。

`finalize_codex_task` responseに最低限:

- status
- task key
- worker id
- Codex turn status
- final agent message
- changed paths summary
- commit SHA（変更があった場合）
- push status
- error/recovery hint（失敗時）

を返す。

Repository-backed Result fileがある場合、changed pathsからlocatorを返せるなら返す。

Codexから既存ChatGPT chatを自動再開するcallbackはT002で作らない。Chatが `finalize_codex_task` を呼べば同じturnで結果を取得できればよい。

## 9. RELEASE

Finalize成功後、target worktreeがcleanならWorkerをFREEにする。

default branchへのcheckout、fetch、remote HEAD一致確認はrelease条件にしない。

read-only TaskはCodex turn completed + clean worktreeでそのままFREEにできる。

local changesが残っている場合だけFREEにしない。

既存 `release_codex_worker` と finalize が重複するなら、personal toolとして分かりやすい方へ簡素化する。互換性のためだけに複雑な二重lifecycleを残さない。

## 10. Existing quarantined probes

現在のprobe由来local state:

- worker-01 / PROBE-002
- worker-02 / PROBE-003

T002実装前後で内容を確認し、診断Resultとして必要なら回収する。

既知のprobe-only成果で不要なものは、Human intentが明確な範囲で除去してWorkerを再利用可能にしてよい。汎用 `clean -fdx` で無関係なデータまで消さない。

この2 Workerの復旧を、新finalize/recovery設計の実地確認に利用してよい。

## 11. Codex executable

現在の実用上の問題として、Codex Desktop付属CLIは存在するが通常PATHには無かった。

最低限、Local Operationsが安定してCodex executableを指定できるようにする。

推奨:

`LOCAL_OPERATIONS_CODEX_EXECUTABLE`

が設定されていればそのpathを使用し、未設定なら従来通り `shutil.which("codex")` を使う。

Codex Desktopのversioned internal pathをRepositoryへ固定しない。

追加のdiscovery frameworkや複雑なready gateは不要。

## 12. Tests

必要なtestsだけ追加/更新する。

最低限:

- FREE Worker → requested branchをfetch/checkout/update → dispatch
- completed Codex Task + worktree changes → commit → non-force push
- no-change Task → commitなしでResult取得 → FREE
- push reject → local成果を保持して失敗
- finalize responseにfinal agent message / commit SHAが含まれる
- Worker FREE後、次Taskで別branchへ切替可能
- `LOCAL_OPERATIONS_CODEX_EXECUTABLE` override
-既存duplicate dispatch / Worker同時利用防止のregressionなし

古い過剰gateのtestが本方針と衝突する場合は、obsolete contractとして更新/削除する。

## 13. Development E2E

`Local Operations Dev` で小さいprobeを1件通す。

```text
Chat-equivalent dispatch
→ Worker
→ requested branch最新化
→ Codexがharmless Result fileを作成
→ Codex completed
→ finalize_codex_task
→ Local Operations commit
→ non-force push
→ final agent message / commit SHAをresponse
→ Worker FREE
```

fixtureまたはprobe branchを使う。実GWI-0006 / GWI-0009 Taskはimplementation probeに使わない。

同じprobeでsubagent capabilityを再証明する必要はない。PROBE-004 PASSを既知の事実として扱う。

## 14. Documentation

affected source/testsと合わせてREADME / ENTRY / VALIDATION_KNOWLEDGEを更新する。

最低限:

- Workerはrequested branchへ都度同期し、default branch復帰不要
- Codexはworktree編集、Local Operationsはcommit/push
- `finalize_codex_task` でResult Intake
- direct ChatGPT callbackなし
- subagent利用可能
- executable override

古いproduction-style gateやstrict revision pinningを正常系として残さない。

## 15. T002 implementation bootstrap

T002自身を実装する時点では `finalize_codex_task` はまだ存在しない。

初回実装のRepository反映は既存の通常開発経路を使ってよい。T002完成後のE2Eから新方式を使う。

## 16. Repository reflection

実装後は現在のGWI branch / Draft PR #1へ通常のnon-force反映を行う。

- force pushしない
- mergeしない

remote HEADや全fileの厳格readbackをCompletion条件にはしない。push成功とPR上の更新が確認できれば十分。

## 17. Completion Report

簡潔に以下を報告:

-変更したlifecycle
- `finalize_codex_task` schema
- Codex executable override方式
- tests
- Development E2E結果
- probe Worker recovery結果
- implementation commit
- PR URL
- known limitation: automatic Chat callbackなし

## 18. HOLD / failure

次のような実害がある時だけ停止する。

- requested branchへ通常同期できない
- Workerに前Taskの未保存成果が残っている
- Codex turnが完了していない
- commit/pushに失敗する
- force/destructive操作なしでは続行できない
- secretをcommitしそうな状態

それ以外は診断情報として扱い、不要なblocking gateにしない。
