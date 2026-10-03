# GWI-0010-T005 Validation Routing Decision

Status: **PASS / ROUTING_DECISION_READY**  
Date: 2026-09-27  
Basis: [Capability Matrix](GWI-0010-T005_CAPABILITY_MATRIX.md)

## 推奨する境界

次の実装は、Controllerから開始するbounded validation toolの最小版とPython/uv adapterを先にする。Unityは同じ結果・process管理を使う明示的なadapterとして後続実装する。任意shell文字列を受け取るgeneric runnerは作らない。本書は設計入力であり、toolの実装・実行許可ではない。

- ACTOR_LOCAL: repository内のsource/docs/tests編集、read-only Git、既に利用可能なtoolchainによる短時間の限定検査。正式要件を満たさないfallbackは診断として報告する。
- HOST_EXECUTED: leaseとrepoを解決し、必要環境を準備し、承認されたprofileの検証processを起動・監視・回収する。Git persistenceは既存finalize、Dev/Prod runtime操作は既存Controller責務を維持する。
- HUMAN_OR_EXTERNAL: login/license acceptance、interactive GUI、Human判断、unsupported repair。環境不足を理由にActorのscopeを広げない。

Host validationはrepository codeを実行するため、bounded引数だけではsandboxにならない。承認済みrepository/profileに限定し、runtime用API key等を継承させない。profile変更が任意host実行権限を自動取得する形にしない。Personal toolとして信頼できるrepositoryへのController判断で足り、独立した認可サービスは不要。

## Questions A–E

| Question | Decision | 理由 / 境界 |
|---|---|---|
| A: PREPAREの拡張 | 宣言されたvalidation能力のreadiness診断を加える。checkout readyとvalidation readyを別項目で返す | 環境不足でも安全な編集は可能。全dispatchを一律blockしない。正式検証を要求する段階で不足を止める |
| B: generic bounded tool | `run_repository_validation(taskIdentity, profileId)`相当の小さな共通入口を推奨 | repo/cwd/branchは既存leaseから解決。任意command、任意absolute path、任意envを入力にしない |
| C: Unity | 共通入口の明示的Unity adapter。別top-level toolは今は不要 | mode、Editor version、XML、生成物、license/process特有の処理をPython adapterへ混ぜない |
| D: declaration | repository-owned configを検証要件のAuthorityにする | Task Requestはprofile選択、Worker configはhost実装path/capacity。二重の要求version管理を避ける |
| E: provisioning | hostがper-worker環境を準備。pre-provisionも可、認証はHuman | Actorのnetwork/sandboxを変更しない。DevEnv venvに依存しない |

### 宣言場所の比較

| Location | 適切な内容 | 採否 |
|---|---|---|
| repository-owned config | profile ID、adapter、相対project root、test selection、toolchain requirement、timeout上限、artifact種別 | 採用。名前/形式は次Taskで最小限決定 |
| Worker Pool config | host executable discovery override、cache root、同時実行数 | host能力のbindingのみ。test command/version requirementを複製しない |
| Local Operations hard-code | 対応adapterのbounded引数生成とresult parsing | repo別commandや2Dhakusura仕様のhard-codeは不採用 |
| Task Request | 対象profile、今回のscope、必要なacceptance | 恒常的toolchain設定を毎Taskに再記述しない |
| bounded registry | 承認済みrepo/profileとadapter種別の対応 | 必要なら既存host configに小さく追加。別Authority registryサービスは不要 |

Pythonの要求version/依存は既存`pyproject.toml`/`uv.lock`を参照する。UnityのEditor versionは対象repoの`ProjectSettings/ProjectVersion.txt`、package要求は`Packages/manifest.json`/`packages-lock.json`を参照する。今回そのUnity repositoryを読んだり変更したりしていない。6000.1.x / URP / Entities 1.3はTask Requestからの前提であり、installed packageの実測値ではない。

## Proposed lifecycle

1. PREPAREは従来のrepo/branch準備後、選択profileについてavailable/missing/unknownと理由を返す。自動installやversion upgradeを暗黙に始めない。
2. Actorが編集し、実行可能なbounded検査を行う。Resultに不足している正式検証を記載する。
3. Controllerがhost validationを開始する。既存leaseからrepo/branch/cwdを照合し、そのWorkerで編集・switch・finalizeが並行しないようにする。未commit差分もそのまま検証対象にできる。
4. hostは必要なら別途許可されたprovisionを実施し、profileに対応する実行引数を生成する。ネットワークを要するrestoreもhost責務。lockを更新せず、利用不可ならenvironment unavailableとして止める。
5. 長期processはrun ID、PID/開始時刻、task/lease、deadline、artifact directoryを保持してstart結果を返す。Controllerがpollし、必要時cancel。待機timeoutはprocess完了と同義にしない。
6. 終了時にexit、stdout/stderr、結果ファイル、timeout/cancel/crashの別を回収する。raw artifact、test summary、判定を分離し、欠落XMLやimport失敗をtest PASSにしない。
7. 検証中にsourceが変わっていないことを一度確認し、Resultへ関連付ける。開始時HEADとdirty差分の識別で十分。remote revision equalityやclean-checkout gateは追加しない。その後の保存/解放は既存finalizeのauthorityで行う。

これは検証runの最小状態管理であり、Global Work lifecycleやHuman Decision policyをLocal Operationsへ移す提案ではない。同一task/profileのactive runを二重起動せず、応答不明時は既存runを照会する。未知のprocessを自動再起動しない。

## Python / uv

P05でPATHがDevEnv venvに向き、起動はexit 101となった。P06のbundled Python 3.12.14はmcpなし。正式環境の代替にはしない。hostが利用可能なPython >=3.13を明示解決し、各Worker repo専用venvでlockに沿って準備する。

`uv run --locked`はlockが整合していることに加えて、実行可能なinterpreter、venv/cacheの権限、必要dependency/build backendが要る。通常のrunは環境同期を伴い得るため、version probeの代わりに無条件実行しない。networkが使えないときは必要な配布物が全て利用可能な場合だけoffline成立とする。[uv running commands](https://docs.astral.sh/uv/concepts/projects/run/)

hostで準備した後もWorker sandboxから同じinterpreterが起動できるとは限らない。そこで短いreadiness probeを行い、使えればActor testも許可、使えなければhost検証を正式経路にする。DevEnvのvenvを共有・変更しない。editable installや別checkoutのmodule混入を避けるため、cwdとimport元も次Taskで確認する。

uv cacheはhost所有の共有cacheでよい。uv自身はcacheの並行利用とvenv lockを扱うが、それは別repoが同一venvを共有すべき理由にはならない。cacheを直接削除・書換えせず、使用中のcleanを避ける。[uv cache safety](https://docs.astral.sh/uv/concepts/cache/)

shared immutable cacheは必須にしない。offline配布が必要になった場合のseedとして検討できるが、uvが使用するwritable cache/lock領域との分離を検証する必要がある。現時点で新しいcache配布機構は不要。

## Unity readiness / adapter

**Unity execution readinessはUNVERIFIED。** 標準Editor/Hub配置を発見できず、PATHのunity.exeはVersionInfo=1.0.0で6000.1 Editorとは確認できない。非標準installation、license状態、DCCFのUTF version、package availabilityは不明。Unity project/testを起動していない。

将来adapterで扱う事項:

| Concern | Proposed handling / limitation |
|---|---|
| Editor discovery | host設定の明示path、Hub標準配置/installation情報を候補にし、Editor実体versionをProjectVersion.txtと照合する。PATH名だけで選ばない。不一致でprojectをupgradeしない |
| Hub依存 | test起動はEditor executableを直接使用する。Hubはdiscovery/setup/loginで必要になり得るが、毎回testをHub経由にする必要はない |
| invocation | `Unity.exe -batchmode -runTests -projectPath <leased-project> -testPlatform EditMode` または `PlayMode`、`-testResults <run>/results.xml -logFile <run>/Editor.log`。固定adapterが引数を組立てる |
| option注意 | `-quit`はrunTestsと併用しない。`-nographics`はURP/graphicsを含む全profileの既定にしない。UTF package versionに対する実機確認を次Taskで行う |
| generated files | Library/Temp/Logs/obj等はcloneごとに分離し、対象repoのignoreを確認する。LibraryをWorker間で共有しない。今回のPython repoにはLibrary ignoreがないためgeneric推測をしない |
| packages | manifest/lockからhost restoreを行う。UPM cache access/networkが不足なら環境不足。認証が要るregistryはHuman setup。package versionを勝手に更新しない |
| installation sharing | 同じEditor binaryを別cloneの候補にできるが、このhostでの並列成功・license条件は未確認。初期はUnity concurrency=1に制限してresource競合を避ける |
| project concurrency | 同一projectでGUI Editorとbatch testを同時に動かさない。Worker leaseに加えてproject使用状況を確認。未知の既存Editorをkillしない |
| EditMode / PlayMode | 別profile・timeoutを宣言する。PlayModeはruntime/frame/graphicsを伴う可能性があり、EditModeと同じ時間・メモリと仮定しない。具体的資源値は未測定 |
| artifacts | run専用XML、Editor.log、必要時UPM log、process exit、duration、実Editor/package version、対象差分識別を回収。XML内test failureと起動/compile/license失敗を分離 |
| hang/crash | deadlineで所有process treeのみ停止、部分log保持、XML欠落はinfrastructure error。lease解放前に残存確認。Library削除やrepairを自動回復策にしない |
| licensing | 初回login/license acceptanceはHuman。既存licenseの利用可否はhost preflightで診断する。credentialを引数/logに渡さない。license適合・並列権利は本Taskでは判定しない |

Editor直接起動、batchmode、同一project制約、logとquitの挙動は[Unity 6000.1 command line](https://docs.unity3d.com/6000.1/Documentation/Manual/EditorCommandLineArguments.html)を参照。EditMode/PlayModeとNUnit XMLは[UTF 1.3 command line](https://docs.unity3d.com/Packages/com.unity.test-framework@1.3/manual/reference-command-line.html)を参照した。これはDCCFがUTF 1.3を使用しているという主張ではない。

UPMには共有global cacheがあるが、その配置・権限はhost側で解決する。[Unity 6000.1 UPM cache](https://docs.unity3d.com/6000.1/Documentation/Manual/upm-cache.html) 本設計ではcache管理をhostに集め、projectのLibraryとは区別する。

URP/Entities/DCCF/2Dhakusuraのtest選択、scene、package設定は対象repository側に置く。Local OperationsにはUnity mode、version照合、process/artifact処理だけを実装し、製品固有ルールを埋め込まない。

## Concurrency / output boundary

現行app-serverのwait timeoutは待機終了であり、子孫process停止ではない。直接processのterminate/killだけに依存せず、host runnerが所有processを追跡する。Windows Job Object等は候補だが、方式の採否は次Taskの短命child/grandchild fixtureで決める。system全体の同名process停止は使わない。

長期対象はUnity import/tests、network restore、長いcompiler/test suite。短いread-only/version probeは現在の同期実行で足りる。runごとのartifact path、上限付きstdout/stderr、disk不足の診断を設け、巨大log/cacheをGitへ入れない。要約とResult locatorはrepoに残し、必要なEvidenceだけ明示的に取り込む。

## Next implementation tasks（提案のみ、Task作成なし）

1. **Host validation V0 + Python/uv adapter**: repository profile、leaseに結びつく実行、per-worker env、限定provision、result回収、timeout/cancelを実装。focused testsと1回のDevelopment E2Eで、正式Python/locked deps、対象import元、dirty差分の検証、子孫終了、重複run防止を確認する。Production操作は不要。
2. **T004 filtering / actual route verification**: 公開設定を使う場合のper-task scopeと実tool catalogをDevで確認する。contract-onlyを採用する場合も残る露出を明示する。これはPython runnerだけでは解消しない。
3. **Unity adapter / host readiness**: 対象repoでEditor/UTF version、license、UPM依存、EditMode/PlayModeの必要条件を確認してから、別途許可されたfixtureでXML/log、version mismatch、同一project競合、timeoutを検証する。

## T004を閉じられるか

将来のPython host routeはT004の正式Python + locked dependency full suite不足を解消する経路になり得る。ただし実際のPASSが必要であり、T005はその代替ではない。さらにT004に残るtool filtering判断とrepository-only Development E2Eを別途完了しなければT004全体を閉じられない。historical HOLDは保持する。
