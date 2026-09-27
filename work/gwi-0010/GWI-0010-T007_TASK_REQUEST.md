# GWI-0010-T007 Task Request

Task Key: `GWI-0010-T007`
Task Name: `Native Codex Result Reflection V0`
Stage: `implementation / integration`

Repository: `sentokun155/ai-local-operations`
Branch: `gwi-0010-ai-local-operations`

## Goal

Codex-native / Desktop Taskが `C:\Dev\DevEnv` のai-local-operations checkoutへ残したTask-owned成果物を、Controller Chatから**明示pathだけ**Repositoryへcommit / normal non-force pushできるbounded Toolを追加する。

T006でこのGapが実際に発生した。

- T006はCodex-native surfaceで完了。
- Unity Pluginはnative surfaceでのみ観測可能。
- T006 TaskはGit commit/pushを禁止した。
- T006成果物はDevEnv local worktreeに残っているが、Local Operations Worker lease外なので `finalize_codex_task` では取得できない。
- unrelated local files / untracked filesを巻き込んではならない。

このTaskはT006成果物そのものを変更・再生成しない。

## Tool

Candidate:

`reflect_development_task_artifacts(work_identity, task_key, paths)`

### Fixed scope

- Repository rootは固定で `C:\Dev\DevEnv`。
- Repository identityは `sentokun155/ai-local-operations`。
- generic repository path入力は受けない。
- shell command入力は受けない。
- `paths` はrepository-relative pathの明示list。
- path traversal / absolute path / .git内部は拒否。

## Behavior

1. DevEnvがexpected repositoryであることを確認。
2. current branchを取得。
3. requested `paths` を正規化・検証。
4. requested pathのうち実際に変更/追加されているものだけを対象とする。
5. **requested paths以外のlocal changeはstageしない・変更しない・削除しない。**
6. 対象が無ければ `UNCHANGED` を返す。
7. 対象pathに既存finalizeと同等のsecret/credential path/text screeningを適用。
8. `git add -- <explicit paths>` のみ。
9. commit message: `Local Operations: <work_identity>/<task_key> native reflection`
10. current branchへnormal non-force push。
11. commit SHA / reflected paths / remaining unstaged-untracked paths countを返す。
12. push failure時はlocal commitを保持し、force/reset/rebase/cleanしない。

## T006 practical target

Tool実装後、Controllerは次のexact pathsだけを反映する予定:

- `work/gwi-0010/GWI-0010-T006_RESULT.md`
- `work/gwi-0010/design/t006/GWI-0010-T006_UNITY_PLUGIN_CAPABILITY_MATRIX.md`
- `work/gwi-0010/design/t006/GWI-0010-T006_UNITY_PLUGIN_REPLICATION_DESIGN.md`

これら以外のDevEnv local files（既存の未追跡bat/shortcut等を含む）は触らない。

## Tests

最低限:

- explicit 3 pathsだけstage/commitし、unrelated untracked fileを残す
- nonexistent / unchanged paths
- absolute / traversal / .git path拒否
- secret-like path拒否
- secret-like staged text拒否
- push failureでlocal commit保持
- wrong repository identity / detached branch等でHOLD
- existing finalize/recovery tests regressionなし

full supported test suiteを実行できる場合は1回実行。
T004/T005で既知のWorker dependency limitationが残る場合は、利用可能なtestsを実行し、未実行を正確に報告する。環境制約を突破しない。

## Runtime boundary

このCodex Task自身では:

- DevEnv local T006成果物を読まない
- T006成果物をstage/commit/pushしない
- Productionを触らない
- Worker recoveryをしない
- Dev Tunnelをrestartしない

source/tests/docsとしてreflection Toolを実装するだけ。

実装完了後:
- current GWI branchへLocal Operations finalizeで反映。
- HumanがDev Plugin catalogを更新。
- Controller ChatがT006 exact pathsをreflection ToolでRepositoryへ反映。
- その後ControllerがT006 Resultを評価する。

## Result

`work/gwi-0010/GWI-0010-T007_RESULT.md`

Final:
`GWI-0010-T007 <PASS|HOLD> — <one-line result>`
