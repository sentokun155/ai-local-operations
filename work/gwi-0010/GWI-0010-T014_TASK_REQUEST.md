# GWI-0010-T014 Task Request — Unity Worker Project Open 起動ライフサイクル修正

## Work Identity

- Work Key: `GWI-0010`
- Work Name: `Chat→Codex MCP Dispatch / Local Worker Pool`
- GWI Authority: `sentokun155/ai-dev-control#16`

## Task Identity

- Task Key: `GWI-0010-T014`
- Task Name: `Unity Worker Project Open 起動ライフサイクル修正`
- Task Stage: `Implementation / Remediation`
- Logical Role: `Implementation Actor`
- Desired Task Title: `GWI-0010-T014 Unity Worker Project Open 起動ライフサイクル修正 — 実装 / Implementation Actor`

## Repository / Branch

- Repository: `sentokun155/ai-local-operations`
- Branch: `gwi-0010-ai-local-operations`
- Task Request: `work/gwi-0010/GWI-0010-T014_TASK_REQUEST.md`

## Persistence / Delivery

`REMOTE_REFLECTION_REQUIRED`

このTaskはRepository-owned implementation/remediationである。self-verification後、通常commit、non-force push、remote HEAD確認、changed-content re-readを行う。force push / rebase / reset / merge / Production更新は許可しない。

## Authority / Source Priority

1. Humanの現在指示
2. `sentokun155/ai-dev-control#16` のGWI Current State / Authority boundary
3. 本Repositoryの `AGENTS.md` とcurrent implementation
4. T004 / T012 / T013のRepository-backed Evidence
5. shared Delegation / Reflection contract

最低限読むこと:

- `work/gwi-0010/GWI-0010-T004_RESULT.md`
- `work/gwi-0010/GWI-0010-T012_TASK_REQUEST.md`
- `work/gwi-0010/GWI-0010-T012_RESULT.md`
- `src/local_mcp/unity_project_open.py`
- `src/local_mcp/unity_probe.py`
- `tests/test_unity_project_open.py`
- `server.py`

T004の次境界を維持する:

- normal Codex Worker: repository-only execution
- Controller Chat / Local Operations Host: Host runtime effect
- Unity Editor起動はController-owned Host runtime effect

WorkerへHost effect Authorityを追加しない。

## Human clarification from T013

T013で既存default Unity projectが後から消えたが、これはHumanがsame-project duplicate warningを見て手動で既存Unityを閉じたためである。

したがって:

- Local Operationsがdefault projectを閉じた、と結論してはいけない。
- different project pathsの複数Editor共存が失敗した、と結論してはいけない。
- coexistenceはT014修正後のController E2Eでfreshに再検証する。

## Observed defect

Controller live E2Eで次を観測した。

1. `open_leased_unity_project(worker-01, GWI-0010, GWI-0010-T013)` を実行。
2. Hostはexact target `C:\Dev\WorkerRoot\worker-01\2dhakusura` を解決し、Unity Editor processを実際に起動した。
3. しかしLocal Operationsの`_run_cli`は`COMMAND_TIMEOUT_SECONDS = 10`で`unity open`をtimeoutし、Toolは即 `HOLD / UNITY_OPEN_TIMEOUT` を返した。
4. Unity processはtimeout後も起動を継続し、Pipeline candidateとしてtarget path / PIDが観測された。
5. 後に同じprojectは `ready / 6000.3.9f1` になった。
6. その前に同じbounded Toolを再度呼ぶと、起動中projectをready instanceとして認識できず、再度`unity open`を送りsame-project duplicate-open warning経路へ入った。
7. projectがreadyになった後の再実行では `ALREADY_READY` が成功した。

つまり:

- process timeout != launch failure
- starting/running candidate != absent project
- retry時にstarting candidateを認識せずopenを再送することが主な欠陥

## Objective

`open_leased_unity_project` をbounded / idempotentなUnity project launch lifecycleとして修正し、次を満たす。

1. `unity open` process timeoutを即時launch failureとして扱わない。
2. timeout後もtarget projectのbounded readiness observationを継続する。
3. target projectがPipeline上でstarting/running candidateとして既に存在する場合、重複した`unity open`を送らない。
4. targetが最終的にexact path + declared Editor versionでreadyになれば成功する。
5. bounded wait後もreadyにならなければ、launch outcomeを過大評価せずspecific HOLDを返す。
6. lease identity / path resolution / secret filtering / no-close boundaryを維持する。

## Required Work

### R01 — Separate command completion from launch outcome

現在の:

```
unity open
-> subprocess timeout
-> HOLD / UNITY_OPEN_TIMEOUT
```

をそのまま維持しない。

`unity open` timeoutは少なくとも:

`OPEN_REQUEST_OUTCOME_UNCERTAIN / launch may still be progressing`

として扱い、その後のtarget observationへ進めること。

命名は既存reason vocabularyに整合するよう決めてよい。

### R02 — Detect target starting/running candidate before a new open

new open requestの前に、exact resolved project pathをHost側Unity discovery surfaceで確認する。

少なくともlive E2Eで観測できた `unity pipeline list` 相当のsupported routeを検討する。

target pathのcandidateが1件存在し、Editor processがstarting / loading / not-yet-ready状態である場合:

- 新しい`unity open`を送らない。
- existing candidateをboundedにready待ちする。
- duplicate target candidateが複数ならHOLD。

arbitrary process scanningやcommand-line scrapingに広げない。

### R03 — Readiness observation

readiness判定はexact normalized project path + declared Editor versionに固定する。

ready確認に使うsurfaceはcurrent CLI behaviorを実測し、必要なら:

- `status --project-path`
- `pipeline list`

を組み合わせてよい。

`status`がstartup途中に一時的にnonzero / no-instanceを返す場合、それだけで即failureにしない設計を検討する。ただしunexpected errorを無制限に飲み込まない。

bounded timeoutは維持する。

### R04 — Retry idempotence

同じactive leaseに対してToolが再呼出しされても:

- target ready -> `ALREADY_READY`
- target starting/running -> new `unity open`を送らずwait
- target absent -> openを最大1回送る

となること。

Task間を跨ぐ永続launch ledgerはV0で必須にしない。現在のHost-observable Unity stateで十分なら新DB/state machineを作らない。

### R05 — Preserve safety boundary

変更してはいけないもの:

- arbitrary project path input禁止
- arbitrary Unity CLI args禁止
- exact active lease requirement
- Worker slot containment
- ProjectVersion.txt authority
- Editor install/upgrade禁止
- Editor close/kill/restart禁止
- descriptor / bearer token非露出
- CONTROL_PLANE_API_KEY child env除去
- shell=False
- Product file mutation禁止
- Production変更禁止

## Verification

最低限、focused testsに以下を追加・更新する。

1. `unity open` subprocess timeout後にtargetがreadyになる -> success
2. `unity open` subprocess timeout後もtargetがreadyにならない -> bounded HOLD
3. invocation開始時にtarget Pipeline candidateがstartingとして存在 -> `open`を送らない
4. starting candidateが後にready -> success
5. starting candidateがtimeoutまでreadyにならない -> HOLD、duplicate openなし
6. ready target -> existing `ALREADY_READY`維持
7. absent target -> openは1回だけ
8. duplicate target candidate -> HOLD
9. statusがstartup途中だけ一時的にnonzero/no-instanceでも、supported transientとして確認できるcaseはbounded waitを継続
10. actual unexpected status errorは無制限retryせずHOLD
11. secrets/raw CLI output非露出
12. no close/kill
13. leaseが途中で変わればHOLD
14. exact Editor version mismatchはHOLD

既存focused suitesも実行する。

- `test_unity_project_open.py`
- `test_unity_probe.py`
- `test_execution_boundary.py`
- Worker lease関連のrelevant tests

full suiteが既存のknown hangで完走しない場合、focused PASSとfull未完了を分離して正確に報告する。

## Live-effect Boundary

このImplementation Task自身ではreal Unity Editorをopen/closeしない。

- live `open_leased_unity_project` 実行禁止
- Dev/Prod restart禁止
- descriptor ACL変更禁止
- Worker security変更禁止
- actual Worker project Unity test禁止

live E2EはT014 candidate reflection後にControllerが実施する。

## Result

作成:

`work/gwi-0010/GWI-0010-T014_RESULT.md`

Result vocabulary:

- `PASS / UNITY_OPEN_LIFECYCLE_REMEDIATION_READY`
- `HOLD / UNITY_STARTING_STATE_UNRESOLVED`
- `HOLD / IMPLEMENTATION_VERIFICATION_INCOMPLETE`

PASSはimplementation candidateがController E2E readyであることだけを意味する。

## Post-implementation Controller E2E

T014反映後:

1. Dev runtime/tool catalog refresh
2. Humanがdefault projectを開いた状態をbaseline確認
3. 別Worker checkoutのUnity projectをController-owned Host Toolでopen
4. initial import/startup中にTool timeout/duplicate openが発生しないこと
5. exact Worker path/versionでready確認
6. default projectがHuman操作なしで維持されるかfresh確認
7. Git cleanliness確認

Worker自身にHost MCP actionを実行させない。T004 boundaryを維持する。

## Completion Report

日本語で簡潔に:

- Verdict
- changed paths
- lifecycle修正内容
- duplicate-open抑止方法
- tests / results
- unverified items
- final commit / remote HEAD
- next Controller E2E

Final message:

`GWI-0010-T014 <PASS|HOLD> — <一文要約>`
