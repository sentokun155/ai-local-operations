# GWI-0010-T015 Task Request — Unity Open Lifecycle 検証失敗修正

## Work Identity

- Work Key: `GWI-0010`
- Work Name: `Chat→Codex MCP Dispatch / Local Worker Pool`
- GWI Authority: `sentokun155/ai-dev-control#16`

## Task Identity

- Task Key: `GWI-0010-T015`
- Task Name: `Unity Open Lifecycle 検証失敗修正`
- Task Stage: `Implementation / Remediation`
- Logical Role: `Implementation Actor`
- Desired Task Title: `GWI-0010-T015 Unity Open Lifecycle 検証失敗修正 — 実装 / Implementation Actor`

## Repository / Branch

- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T015_TASK_REQUEST.md`

## Persistence / Delivery

`REMOTE_REFLECTION_REQUIRED`

Repository-owned remediation task。self-verification後、通常commit、non-force push、remote HEAD確認、changed-content re-readを実施する。

force push / force-with-lease / rebase / reset / merge / Production更新は禁止。

## Authority / Source Priority

1. Humanの現在指示
2. `sentokun155/ai-dev-control#16` Current State / T014 Host verification record
3. 本Repositoryのcurrent committed source / `AGENTS.md`
4. T004 / T012 / T014 Task Request / Results
5. shared Delegation / Safe Repository Reflection contract

最低限読む:

- `work/gwi-0010/GWI-0010-T004_RESULT.md`
- `work/gwi-0010/GWI-0010-T012_RESULT.md`
- `work/gwi-0010/GWI-0010-T014_TASK_REQUEST.md`
- `src/local_mcp/unity_project_open.py`
- `tests/test_unity_project_open.py`
- `src/local_mcp/unity_probe.py`
- `tests/test_unity_probe.py`
- `tests/test_execution_boundary.py`
- `server.py`

T004境界を維持する:

- normal Codex Worker = repository-only
- Host runtime effect = Controller / Local Operations Host
- Unity Editor起動のlive actionをWorker自身で実行しない

## T014 disposition

T014 local candidateは`worker-03`に残っているが、Host verificationで失敗したため**使用・finalize・pushしない**。

T015はそのworking treeを前提にしない。remote committed branchからfreshに修正する。

Controller verification:

- Python: `3.13.14`
- `test_unity_project_open.py`: 23 tests / 10 FAIL / 1 ERROR
- `test_unity_probe.py`: 25 PASS
- `test_execution_boundary.py`: 2 PASS
- Worker lease focused test: 1 PASS
- compileall: PASS
- git diff --check: PASS

つまりglobal regressionではなく、T014で追加したUnity open lifecycle semanticsが未完成。

## Objective

T014で意図したbounded / idempotent launch lifecycleを、実装とtestsが一致する状態まで修正する。

必須結果:

1. target already ready -> `ALREADY_READY`
2. target starting/running -> duplicate `unity open`を送らずready待ち
3. target absent -> `unity open`を最大1回だけ送る
4. `unity open` subprocess timeout -> launch outcome uncertainとしてbounded readiness observationへ継続
5. eventual exact-path + exact-version ready -> success
6. bounded wait終了時もreadyでなければspecific HOLD
7. unexpected status failure後に勝手にopenしない
8. leaseが変わった場合はfirst external effect前およびreadiness中に止まる
9. result contractでopen request outcomeをboundedに観測可能
10. credential/raw outputを返さない

## Verified failure matrix to remediate

### F01 — Result contract missing

Test expectation:

`result["openRequestOutcome"]`

が存在すること。

Current T014 candidateではKeyError。

Implement a bounded enum-like field, for example:

- `NOT_SENT`
- `ACCEPTED`
- `UNCERTAIN`

Exact names should follow tests/current code, but semantics must distinguish:

- no open request
- command accepted/completed
- command timed out / request may still be progressing

Do not return raw command output.

### F02 — Pipeline duplicate candidate qualification

When exact normalized target project path appears as multiple Pipeline candidates:

- return HOLD
- reason: `TARGET_PROJECT_AMBIGUOUS`
- do not send `unity open`

Current candidate falls through to `UNITY_EDITOR_NOT_READY`.

### F03 — Pipeline wrong-version qualification

When exact target candidate is already ready but Editor version differs from declared `ProjectVersion.txt`:

- HOLD
- reason: `UNITY_EDITOR_VERSION_MISMATCH`
- no new open

Current candidate falls through to generic not-ready.

### F04 — Starting candidate semantics

When exact target exists in Pipeline discovery but is not yet ready:

- classify as existing starting/running target
- do not send open
- bounded wait for readiness

If later ready:

- return success representing an already-existing launch, not `OPENED_READY`
- expected semantics: `ALREADY_READY` / no new open request

If timeout:

- HOLD / `UNITY_STARTING_STATE_UNRESOLVED`
- no duplicate open

### F05 — Open timeout semantics

If target was absent and one `unity open` request is sent but subprocess times out:

- do not immediately return legacy `UNITY_OPEN_TIMEOUT`
- mark open outcome `UNCERTAIN`
- continue bounded readiness observation

If target later becomes ready:

- success
- `openRequestSent == true`
- `openRequestOutcome == UNCERTAIN`

If bounded wait expires:

- HOLD / `OPEN_REQUEST_OUTCOME_UNCERTAIN`
- do not send a second open

### F06 — Transient startup status

For an already observed target candidate, supported transient startup observations may include:

- no instance yet
- bounded status timeout

These must not automatically trigger a new open.

Retry within bounded readiness deadline.

### F07 — Unexpected status failure

An unexpected/non-transient status error must:

- HOLD
- not send `unity open`
- not enter unbounded retry

Current candidate can proceed to open.

### F08 — Lease recheck before first effect

Before any new `unity open` external effect:

- re-read exact active lease
- if lease changed/disappeared, HOLD
- `openRequestSent == false`

Readiness observation should also stop if lease changes.

## Implementation guidance

Prefer minimal changes inside:

- `src/local_mcp/unity_project_open.py`
- `tests/test_unity_project_open.py`

Use `unity pipeline list` only as bounded discovery support; do not duplicate broad logic from `unity_probe.py` unless a small reusable helper is clearly safer.

Do not introduce:

- persistent launch DB/state machine
- process command-line inspection
- arbitrary filesystem path input
- generic shell runner
- descriptor read
- ACL modifications
- Editor close/kill/restart

Keep path comparison Windows-normalized and exact to the resolved lease project.

## Required Verification

Use supported Python 3.13+ environment when available.

Minimum:

```text
python -m unittest discover -s tests -p "test_unity_project_open.py" -v
python -m unittest discover -s tests -p "test_unity_probe.py" -v
python -m unittest discover -s tests -p "test_execution_boundary.py" -v
python -m unittest discover -s tests -p "test_worker_pool.py" -k get_lease -v
python -m compileall src tests
git diff --check
```

Acceptance for candidate reflection:

- `test_unity_project_open.py`: all PASS
- other listed focused suites: all PASS
- compileall PASS
- diff check PASS

If Worker Python environment cannot execute these again, do not claim PASS. Preserve candidate locally and return exact Host verification command/result needed.

## Live-effect Boundary

This T015 implementation Task must not:

- call real `open_leased_unity_project`
- start/stop Unity Editor
- restart Dev/Prod runtime
- run Unity tests
- modify Product repositories
- touch descriptor/token/ACL
- alter Worker security

Live Controller E2E happens only after verified remote reflection.

## Result

Create:

`work/gwi-0010/GWI-0010-T015_RESULT.md`

Verdict:

- `PASS / UNITY_OPEN_LIFECYCLE_REMEDIATED`
- `HOLD / IMPLEMENTATION_VERIFICATION_INCOMPLETE`
- `HOLD / LIFECYCLE_SEMANTICS_UNRESOLVED`

## Completion Report

日本語で簡潔に:

- Verdict
- changed paths
- failure matrix F01-F08 disposition
- tests/results
- unverified items
- commit / remote HEAD
- next Controller E2E

Final:

`GWI-0010-T015 <PASS|HOLD> — <一文要約>`
