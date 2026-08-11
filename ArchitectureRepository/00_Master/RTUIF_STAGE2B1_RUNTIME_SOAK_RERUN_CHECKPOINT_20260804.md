# DeltaEngine05M — RTUIF Stage 2B-1 Runtime Soak 再実測checkpoint

作成日: 2026-08-04 08:56:52 JST  
対象repository: `C:\Users\user\Desktop\DeltaEngine05M`

## 開始前checkpoint

- 承認範囲: ユーザーの `yare` を、直前に提示されたStage 2B-1の6工程を実行する明示承認として受領した。
- 完了済み:
  - `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全1,274行を全文確認した。
  - Stage 2B-1指示書、実装報告書、runtime soak引継ぎを全文確認した。
  - 引継ぎ書の「soak未実施」と、実装報告書の既存600秒soak記録が矛盾することを確認した。
  - 最新のユーザー指示を優先し、既存証拠を上書きせず新規runとして再実測する方針を固定した。
  - host source/config/protected 10件のSHA-256がStage 2B-1正本値と一致することを確認した。
  - 正規Stage 2B-1 image `sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c` と、temporary overlay image `sha256:1d77ffbff68e8d9f8264218a3245139e089fd200063fa218f68209feb3fb74c9` の存在を確認した。
  - 正規imageを使用するcontainer `7dd38166a586a57664b8777ddd534b7fd108a32bd8e219f3d48939627c9aaf3c` が稼働中であることを確認した。
  - overlay Dockerfileの親が上記正規image tagへ固定され、計装差分が4ファイルだけである既存構成を確認した。
- 未完了:
  - 現runtime health、container inspect、image/overlay manifestの新run開始前証拠化。
  - temporary overlayへのclean recreateとreadiness。
  - 600秒runtime soak、closed log解析、3,000ms超分類。
  - 正規imageへの復元、終了SHA/health検証、最終報告。
- 変更file: 本checkpointのみ。source本体、protected、timeout値、UI freshnessは未変更。
- 検証結果: 指定SHA 10件一致。正規imageとoverlay image存在。container restart/OOMの詳細とhealthは次工程で固定する。
- blockerの限定範囲: なし。既存文書の状態矛盾は新規runで再測定することで解消する。
- 次の再開位置: 現runtime/API/container/manifestを新規証拠rootへ記録し、正規image readinessを確認する。
- 禁止事項: `git add` / `commit` / `push`、source本体・protected・timeout値・UI freshnessの変更を行わない。

## 進行checkpoint

### 2026-08-04 09:04 JST — overlay切替前

- 承認範囲: Stage 2B-1 runtime soak再実測。source本体、protected、timeout値、UI freshnessの変更は禁止。
- 完了済み:
  - 新規証拠root `C:\tmp\rtuif_stage2b1_runtime_rerun_20260804_090000` を作成した。既存runは上書きしていない。
  - 現containerは正規image `sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c`、restart 0、OOM false、計装module不在。
  - `/health=ok`、`/api/health=GREEN`、book gap 0、pipeline exception 0、event lag 0ms、Tape dropped 0 / send failure 0 / balanced trueを確認した。
  - container内source/config/protected 10件のSHAがhost正本値と一致した。
  - 正規imageを`FROM`に固定したtemporary overlayを再buildした。新tagは`rtuif-stage2b1-instrumentation:20260804-rerun-090000`、image IDは`sha256:e57276297e3fba9378fbf2b24da61a9ed6911b399128b04febc92249cd900fb2`。
  - `/app`全manifest比較は親1,605 file、overlay 1,607 file。差分はmodified 2件（`src/pipeline.py`, `webapp/main.py`）とadded 2件（計装module 2件）のみ。removed 0。
- 未完了: overlay clean recreate、readiness、600秒soak、解析、正規image復元、終了SHA/health、最終報告。
- 変更file:
  - repository内は本checkpointのみ。
  - temporary evidence内は新規rootの複製資材と、再実測tagへ向けた`stage2b1_overlay.override.yml`のみ。
- 検証結果: preflight gate PASS。現runtimeは開始時GREEN、正規SHA一致、overlay差分は計装4件だけ。
- blockerの限定範囲: なし。計装path不在確認の`ls`は期待どおり非0終了したが、対象2fileの不存在を直接確認した結果である。
- 次の再開位置: overlay imageへclean recreateし、startup後readinessを別名証拠へ記録する。

### 2026-08-04 09:11 JST — 600秒soak開始前

- 承認範囲: temporary overlay上のread-only計装、host WebSocket observer、container cgroup samplerによる600秒測定。
- 完了済み:
  - overlayへclean recreateした。container IDは`0a0f6ed92ed72d6d805e955dc485f0b93ce2015bfc095cb20f55683568d324d6`、image IDは`sha256:e57276297e3fba9378fbf2b24da61a9ed6911b399128b04febc92249cd900fb2`。
  - restart 0、OOM false、status running、計装module 2件存在。
  - readiness observerはexit 0。`ready=true`、`health_ok=true`、`api_green=true`、`subscribed=true`、`book_synced=true`。
  - readiness evidence SHA-256は`bc9ce62ee48c09a81c3a551eeac36ffdbc0a41e979f1c20387efc9e525e1411c`。
  - soak前APIはGREEN、book gap 0、pipeline exception 0、event lag 0ms、Tape dropped 0 / pending 0 / send failure 0 / balanced true。
  - 計装log開始点は`candidate_timings.jsonl` 8,275,940 bytes、`primary_loop_observation.jsonl` 1,698,331 bytes。canonical集計はsupervisorの開始・終了wall timeで切り出す。
- 未完了: 600秒supervisor完走、graceful stopによる計装flush、closed log解析、正規image復元、最終報告。
- 変更file: repository内は本checkpointのみ。runtime source bind、protected、timeout値、UI freshnessは変更0。
- 検証結果: 長時間処理開始gate PASS。
- blockerの限定範囲: なし。承認待ち中にoverlay計装logが増加したが、canonical境界外として除外可能。
- 次の再開位置: label `stage2b1_rerun` で600秒supervisorを完走する。

### 2026-08-04 09:22 JST — 600秒soak完走直後

- 承認範囲: 同上。次はpost-soak状態保存、overlay graceful stop、closed log回収と解析。
- 完了済み:
  - canonical requested 600.0秒を完走した。
  - supervisor elapsed 600.5639729秒。
  - observerは1 segment、5,122,951 bytes、elapsed 600.5543075秒、exit 0。
  - cgroup sampler exit 0。
  - supervisor自身のexit 0。早期終了、observer再接続segment、出力上書きはない。
- 未完了: post-soak API/container証拠、計装writer close、closed log回収、遅延分類、正規image復元、終了SHA/health、最終報告。
- 変更file: repository内は本checkpointのみ。測定成果物は新規evidence root内だけ。
- 検証結果: canonical duration/observer/sampler完走gate PASS。効果・非破壊gateはclosed log解析前なので未判定。
- blockerの限定範囲: なし。
- 次の再開位置: overlay稼働中のpost-soak health/inspectを保存後、graceful stopして計装2 logを回収する。

### 2026-08-04 09:40 JST — closed解析完了／exact復元修正中

- 完了済み:
  - overlayはgraceful stop、exit 0、restart 0、OOM false。closed log 2件を回収した。
  - `candidate_timings_closed.jsonl`: 96,094,008 bytes、SHA-256 `c5cc6e717bd5f58b4c87c49223dde6a2e258f870de1d218e88a8a8ac0b5ba37b`。
  - `loop_observation_closed.jsonl`: 6,434,514 bytes、SHA-256 `8f65cf378261ef4b68b7773ea0e6435bff77767f41c1d01c2944c1877275219c`。
  - canonical解析はPASS。canary wake max 414.631ms、3,000ms超0件。server生成間隔max 1,356.872ms、browser受信間隔max 1,450.038ms。
  - ready burst event max 23、wall max 313.454ms。raw event max 313.387ms、`handle_trade` max 312.446ms、storage tick max 2.202ms。
  - heartbeat 558/healthy 558、heartbeat sequence gap 0。Book WebSocket sequence error 0。Tape sequence error 0。
  - 3,000ms超が0件のため、backlog型0、単一event型0、other task/queue resume型0。
- 未完了: exact正規image復元、終了SHA/health、manifest、最終報告。
- 復元工程の限定blocker:
  - 初回復元`docker compose up`がbase composeの`build:`を実行し、正規tagをhost再build image `sha256:d5c78792ca3313dc5f8d542878cae8f0df53fd68aa459cb1089f30a9214b8a84`へ付け替えた。
  - containerはGREEN、計装module不在だが、要求image ID `sha256:a9c39d4f...`と一致しないため復元未完了として扱う。
- 変更file: source本体・protected・timeout値・UI freshness変更0。Docker image tag/container stateのみ復元修正対象。
- 次の再開位置: 旧正規image ID `sha256:a9c39d4f...`の存在を確認し、tagを戻して`--no-build --pull never`でexact recreateする。誤build imageは削除しない。

### 2026-08-04 09:45 JST — 最終checkpoint

- 承認範囲: Stage 2B-1 runtime soak再実測、解析、復元、証拠・報告作成。全工程を承認範囲内で完了した。
- 完了済み:
  - exact正規imageを復元。container `0b997ee8eeaa301b710c38d62d5c345a769537f810b43092d654760471b647df`、image `sha256:a9c39d4f2e8bdbaf69e20ee7ace13cae5a84616a40f34b25641f615f9aa8de8c`、restart 0、OOM false、running。
  - exact restore readinessは`ready=true / api_green=true / subscribed=true / book_synced=true`。計装module不在。
  - 最終APIはGREEN、book gap 0、pipeline exception 0、event lag 0ms、Tape dropped 0 / send failure 0 / balanced true。
  - host／container source/config/protected 10件は開始SHAと全一致。
  - 最終報告書`RTUIF_STAGE2B1_RUNTIME_SOAK_RERUN_REPORT_20260804.md`を作成した。
- 未完了: なし。本承認範囲の実作業は終了。
- 変更file:
  - `ArchitectureRepository/00_Master/RTUIF_STAGE2B1_RUNTIME_SOAK_RERUN_CHECKPOINT_20260804.md`
  - `ArchitectureRepository/00_Master/RTUIF_STAGE2B1_RUNTIME_SOAK_RERUN_REPORT_20260804.md`
  - 新規temporary evidence root配下の計装資材・生ログ・解析・manifest。
  - source本体、protected、timeout値、UI freshnessの変更0。
- 検証結果:
  - runtime効果gate PASS: canary max 414.631ms、server max 1,356.872ms、browser max 1,450.038ms、3,000ms超0。
  - Book sequence error 0、gap 0、Tape failure 0、message継続。
  - strict非破壊gate FAIL: canonical BOOK_UPDATE 3,143件中STALE 1件（直前・次はSYNCED）。
  - 総合NO-GO。Stage 2B-2、budget、timeout、他source変更へ進んでいない。
- blockerの限定範囲: 次のrelease判断はstrict全SYNCED不達の扱いに限定され、現在runtime復元・運転を妨げるblockerはない。
- 次の再開位置: ユーザーが本報告とevidenceを確認し、STALE 1件の扱いまたは次工程を明示する地点。
- Git操作: `git add` / `commit` / `push` / branch操作0。
