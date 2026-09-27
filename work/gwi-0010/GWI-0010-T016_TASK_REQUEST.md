# GWI-0010-T016 Task Request — Unity Open Lifecycle 状態遷移再構成

## Work Identity

- Work Key: `GWI-0010`
- Work Name: `Chat→Codex MCP Dispatch / Local Worker Pool`
- GWI Authority: `sentokun155/ai-dev-control#16`

## Task Identity

- Task Key: `GWI-0010-T016`
- Task Name: `Unity Open Lifecycle 状態遷移再構成`
- Task Stage: `Implementation / Remediation`
- Logical Role: `Implementation Actor`
- Desired Task Title: `GWI-0010-T016 Unity Open Lifecycle 状態遷移再構成 — 実装 / Implementation Actor`

## Repository / Branch

- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T016_TASK_REQUEST.md`

## Persistence / Delivery

`REMOTE_REFLECTION_REQUIRED`

self-verification PASS後のみ、通常commit、non-force push、remote HEAD確認、changed-content re-readを行う。

禁止:

- force push / force-with-lease
- reset / clean
- rebase
- merge
- Production更新

## Authority / Required Reads

優先順位:

1. Humanの現在指示
2. `sentokun155/ai-dev-control#16` Current State
3. 本Repositoryの`AGENTS.md` / current committed implementation
4. T004 / T012 / T014 / T015のTask Request・Result・Controller verification record
5. shared Delegation / Safe Repository Reflection contract

最低限読む:

- `work/gwi-0010/GWI-0010-T004_RESULT.md`
- `work/gwi-0010/GWI-0010-T012_RESULT.md`
- `work/gwi-0010/GWI-0010-T014_TASK_REQUEST.md`
- `work/gwi-0010/GWI-0010-T015_TASK_REQUEST.md`
- `src/local_mcp/unity_project_open.py`
- `tests/test_unity_project_open.py`
- `src/local_mcp/unity_probe.py`
- `tests/test_unity_probe.py`
- `tests/test_execution_boundary.py`
- `server.py`

T004の境界は不変:

- normal Codex Worker = repository-only
- Unity Editor起動等のHost runtime effect = Controller / Local Operations Host
- Worker自身へHost-effect Authorityを追加しない

## Previous Candidate Disposition

T014 / T015のlocal candidatesは、それぞれHost verificationでFAILしたため使用・finalize・pushしない。

T016はremote committed branchからfreshに修正する。

T015 Host verification:

- Python `3.13.14`
- `test_unity_project_open.py`: 22 tests / 9 FAIL / 5 ERROR
- `test_unity_probe.py`: 25 PASS
- `test_execution_boundary.py`: 2 PASS
- `test_worker_pool.py -k get_lease`: 1 PASS
- `compileall`: PASS
- `git diff --check`: PASS

この結果から、generic regressionではなく`unity_project_open.py`のstate classification / transition orderが未完成と判断する。

## Objective

個別assertionへ場当たり的にpatchするのではなく、`open_leased_unity_project`を**明示的なbounded state transition**として再構成する。

### Required transition order

```text
Resolve exact lease/project
  ↓
Pipeline discovery for exact project path
  ↓
Current status observation
  ↓
Classify current target state
  ├─ duplicate exact target -> HOLD
  ├─ exact target ready + exact version -> ALREADY_READY
  ├─ exact target ready + wrong version -> HOLD
  ├─ exact target starting/running -> wait existing target; never open again
  ├─ discovery/status fatal error -> HOLD
  └─ exact target absent -> verify Editor availability
                                ↓
                         recheck exact lease
                                ↓
                         send unity open once
                                ↓
                   ACCEPTED or UNCERTAIN outcome
                                ↓
                         bounded readiness wait
                                ↓
                     ready / specific HOLD
```

この順序をコードとtestsの両方で固定する。

## Required Result Contract

すべての返却pathで、bounded field:

`openRequestOutcome`

を必ず返す。

値:

- `NOT_SENT`
- `ACCEPTED`
- `UNCERTAIN`

意味:

- `NOT_SENT`: このinvocationでは`unity open`を送っていない
- `ACCEPTED`: open commandがtimeoutせずaccepted/completed
- `UNCERTAIN`: subprocess timeout等によりcommand completionは不明だが、launchが進行中の可能性がある

raw stdout/stderr/command lineを返さない。

既存`openRequestSent`との整合も保つ:

- NOT_SENT -> false
- ACCEPTED / UNCERTAIN -> true

## State Classification Requirements

### S01 — Pipeline discovery

exact normalized target pathのPipeline candidateをboundedに取得する。

- 0件: absent candidate
- 1件: candidate stateを判定
- 2件以上: `HOLD / TARGET_PROJECT_AMBIGUOUS`

Pipeline discovery自体がunexpected failureなら:

`HOLD / UNITY_PIPELINE_UNAVAILABLE`

として止める。そこから`unity open`へ進まない。

### S02 — Ready target

exact path candidate/statusがreadyの場合:

- Editor version == declared version -> `ALREADY_READY`
- Editor version != declared version -> `HOLD / UNITY_EDITOR_VERSION_MISMATCH`

open requestは送らない。

### S03 — Starting/running target

exact targetがPipeline上に存在するがstatus readyではない場合:

- existing launchとして扱う
- `unity open`を送らない
- bounded readiness waitへ入る

readyになれば:

- `ALREADY_READY`
- `openRequestOutcome = NOT_SENT`

timeoutなら:

- `HOLD / UNITY_STARTING_STATE_UNRESOLVED`
- duplicate openなし

### S04 — Absent target

Pipeline/statusともexact targetが存在しないと判定できた場合のみ、新規open候補。

ただし、その前にrequired Editorがinstalledか確認する。

Editor未導入:

`HOLD / UNITY_EDITOR_UNAVAILABLE`

openしない。

### S05 — First-effect lease recheck

`unity open`直前にexact lease:

- worker_id
- work_identity
- task_key
- repository identity

を再確認。

不一致/消失:

`HOLD / WORKER_LEASE_NOT_FOUND`

- `openRequestOutcome = NOT_SENT`
- `openRequestSent = false`

### S06 — Open accepted

open commandが正常完了した場合:

- `openRequestOutcome = ACCEPTED`
- readiness observationへ進む

ready -> `OPENED_READY`

bounded timeout -> existing specific not-ready HOLD。

### S07 — Open timeout / uncertain

open subprocess timeout:

- immediate `UNITY_OPEN_TIMEOUT` returnは禁止
- `openRequestOutcome = UNCERTAIN`
- readiness observationへ進む
- second open禁止

readyになれば成功。

readyにならないままbounded deadline:

`HOLD / OPEN_REQUEST_OUTCOME_UNCERTAIN`

### S08 — Transient status during startup

既にtarget launchが存在すると分かっている場合だけ、startup中のsupported transient observationをbounded retryできる。

例:

- no ready instance yet
- one bounded status timeout

ただしunexpected/non-transient status failureは即HOLD。

fatal status error後に新規openへfall throughしてはいけない。

### S09 — Readiness-time lease continuity

wait loop中もleaseを確認する。

leaseが変化/消失:

`HOLD / WORKER_LEASE_NOT_FOUND`

Editorをclose/killしない。

## T015 Host Failure Matrix

次をすべて回収する。

### F01 Result field

複数testで `openRequestOutcome` KeyError。

すべてのsuccess/HOLD返却でfieldを存在させる。

### F02 Open timeout

Current candidate:

`UNITY_OPEN_TIMEOUT`

期待:

`OPEN_REQUEST_OUTCOME_UNCERTAIN`

または後続ready成功。

### F03 Wrong version

Current:

`UNITY_EDITOR_NOT_READY`

期待:

`UNITY_EDITOR_VERSION_MISMATCH`

### F04 Pipeline discovery failure

Current:

`UNITY_EDITOR_NOT_READY`

期待:

`UNITY_PIPELINE_UNAVAILABLE`

### F05 Duplicate Pipeline candidate

Current:

`UNITY_EDITOR_NOT_READY`

期待:

`TARGET_PROJECT_AMBIGUOUS`

### F06 Starting candidate

Current:

- timeout -> generic `UNITY_EDITOR_NOT_READY`
- later ready -> `OPENED_READY`

期待:

- timeout -> `UNITY_STARTING_STATE_UNRESOLVED`
- later ready -> `ALREADY_READY`
- no open request

### F07 Transient startup status

Current:

`HOLD`

期待:

bounded retry後 `ALREADY_READY` when target becomes ready.

### F08 Unexpected initial status failure

Current path may proceed incorrectly.

期待:

- HOLD
- no open
- `openRequestOutcome = NOT_SENT`

### F09 Command ordering

Required Editor unavailable caseのexpected observation order:

```text
pipeline discovery
-> status observation
-> editors --installed
```

つまりEditor installation checkを先に行ってcurrent target state classificationを飛ばさない。

## Tests

`tests/test_unity_project_open.py`をstate transition contractに合わせて整備する。

最低限:

1. absent -> open accepted -> ready
2. ready exact -> ALREADY_READY / NOT_SENT
3. lease change before open -> no first effect
4. lease change during wait -> HOLD
5. open accepted then readiness timeout
6. open timeout -> uncertain -> eventual ready
7. open timeout -> uncertain -> bounded HOLD
8. duplicate pipeline target -> HOLD before status/open as intended by test contract
9. wrong-version target -> HOLD no open
10. discovery failure -> HOLD no open
11. starting target -> eventual ready / ALREADY_READY
12. starting target -> bounded specific HOLD
13. transient startup no-instance / timeout -> retry, no open
14. unexpected status failure -> HOLD, no open
15. required Editor unavailable ordering
16. secrets/raw payload never exposed
17. different path never mistaken for target
18. MCP schema remains lease identity only

## Required Verification

使用可能なPython 3.13+環境で:

```text
python -m unittest discover -s tests -p "test_unity_project_open.py" -v
python -m unittest discover -s tests -p "test_unity_probe.py" -v
python -m unittest discover -s tests -p "test_execution_boundary.py" -v
python -m unittest discover -s tests -p "test_worker_pool.py" -k get_lease -v
python -m compileall src tests
git diff --check
```

PASS条件:

- unity project open suite: 0 FAIL / 0 ERROR
- probe suite: 0 FAIL / 0 ERROR
- execution boundary: 0 FAIL / 0 ERROR
- focused lease test: PASS
- compileall: PASS
- diff check: PASS

Worker内Python 3.13環境が使えない場合:

- 実装candidateをlocal保持
- exact Host verification commandをResultへ残す
- PASSを主張しない
- remote reflectionしない

## Live-effect Boundary

このTaskでreal Unityは操作しない。

禁止:

- real `open_leased_unity_project`
- Unity Editor start/stop
- Dev/Prod restart
- Unity tests
- Product repository mutation
- descriptor/token/ACL access
- Worker security変更

## Result

`work/gwi-0010/GWI-0010-T016_RESULT.md`

Verdict:

- `PASS / UNITY_OPEN_STATE_MACHINE_READY`
- `HOLD / IMPLEMENTATION_VERIFICATION_INCOMPLETE`
- `HOLD / STATE_TRANSITION_UNRESOLVED`

## Completion Report

日本語で:

- Verdict
- changed paths
- state transition再構成内容
- T015 F01-F09 disposition
- tests/results
- unverified items
- commit / remote HEAD
- next Controller E2E

Final:

`GWI-0010-T016 <PASS|HOLD> — <一文要約>`
