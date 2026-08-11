# DeltaEngine05M — MARKET DATA STALE / receiver_out overflow 恒久修正 checkpoint

## 2026-08-07 23:22:15 +09:00 — 最初の変更前

- 承認範囲: ユーザーの「全然改善されていない、いい加減な対応をするな」という最新指示を、現在再発中の `TICK_SOURCE_STALE` と内部queue overflowについて、原因測定、source/testの恒久修正、candidate配備、runtime検証まで行う指示として受領した。
- 明示的な保護境界: 完成済みFlow Price Response、3段チャート、8パターン、OI、Footprint、Heatmap、Tapeの計算意味を変更しない。Strategy execution権限、LIVE注文、MT5 algorithmic tradingを有効化しない。Git commit / pushは行わない。
- 完了済み:
  - `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文とroot `AGENTS.md`を確認した。
  - 2026-08-07 23:10 JSTのruntimeで `/api/health=RED`、event lag `60,944ms`、`receiver_out` overflow少なくとも840件、Book gap、CPU約95〜144%を直接確認した。
  - Binance接続断や表示だけの問題ではなく、単一main consumerが受信速度へ追いつかず、`receiver_out`でraw eventをdropしていることを確認した。
  - 過去の2026-08-04記録にも同一overflowとNO-GOが明記されており、Stage 2B-1 chunk化とLIVE DOM rearm修正は本件のthroughput不足を解消していなかったことを再確認した。
  - 別processのlive profileで、depth処理、Hook DOM feature生成、Absorptionのwindow再集計を主要CPU候補として確認した。profileはproduction containerを変更していない。
- 未完了:
  - production process自体のsample profileと、module別service capacityの確定。
  - 計算結果を変えないhot-path最適化、queue/accounting監視、決定論的burst試験。
  - 関連回帰、repository全体回帰、candidate image、runtime soak。
- 変更file: 本checkpoint 1件のみ。
- 検証結果: 現runtimeは使用NO-GO。再起動だけでは過去同様に再発するため恒久修正とは扱わない。
- blockerの限定範囲: なし。既存dirty worktreeのうち対象外変更は保持し、変更対象とhunkを限定する。
- 次の再開位置: production processのsampling profileを取得し、上位hot pathを現行sourceと照合して最小修正範囲を確定する。

## 2026-08-07 23:33:15 +09:00 — 原因測定・最小source修正・targeted test完了

- 承認範囲: 初回checkpointと同じ。candidate配備前に、計算意味を変えないhot-path最適化とqueue観測をsource/testへ限定して実施した。
- 完了済み:
  - production processを外部samplingし、同一book updateからStrategy、Hook DOM、web projectionが別々にsnapshot copy/sortを繰り返していることを確認した。
  - `OrderBookStateManager.snapshot()`を、次の受理済みstate transitionまで同一snapshotを再利用する方式へ変更した。snapshotは従来どおり作成時点のdict copyを保持し、diff/gapでcacheを無効化する。
  - Strategy/Hook/web projectionがsnapshot内の同一ordered levelsを再利用するよう変更した。Flow Price Response、3段チャート、signal判定式、表示level値は変更していない。
  - `DropOldestQueue`へput/get/high-watermark/drop-kind別のaccountingと警告rate-limitを追加し、pipelineから `/api/stats` に公開できるようにした。
  - targeted test 55件がPASS。`py_compile`と対象fileの`git diff --check`もPASS。
  - HEAD baselineとcandidateを同じsynthetic depth workloadで各5回比較し、中央値は4.598ms/updateから3.696ms/updateへ約19.6%短縮した。snapshot単体2000回は約93.55msから0.259msへ短縮し、state非更新中のidentity再利用を確認した。
- 未完了:
  - 関連test範囲の拡大とrepository全体回帰。
  - candidate image build/recreateと、実feedでのreceiver drop、event lag、book sync、healthのsoak確認。
- 変更file:
  - `Delta_Engine_Pro4web/src/orderflow/orderbook.py`
  - `Delta_Engine_Pro4web/src/orderflow/hooks/dom_features.py`
  - `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
  - `Delta_Engine_Pro4web/webapp/book_projection.py`
  - `Delta_Engine_Pro4web/src/acquisition/event_queue.py`
  - `Delta_Engine_Pro4web/src/pipeline.py`
  - `Delta_Engine_Pro4web/webapp/main.py`（既存の未commit変更を保持し、queue stats hunkのみ追加）
  - `Delta_Engine_Pro4web/tests/orderflow/test_orderbook.py`
  - `Delta_Engine_Pro4web/tests/acquisition/test_acquisition.py`
  - 本checkpoint
- 検証結果: source-level candidateはtargeted testと同条件benchmarkを通過。ただし実feedでdrop=0を確認するまで使用GOとは判定しない。
- blockerの限定範囲: なし。synthetic integrated benchmarkは同時稼働中のproduction CPU負荷で揺れるため、5-run中央値のみ比較値として採用した。
- 次の再開位置: orderflow/strategy/webapp/live-pipelineの関連回帰を実行し、失敗をcandidate由来と既存baselineに分離する。PASS後にrollback用image参照を保存してcandidateをbuild/recreateする。

## 2026-08-07 23:34:57 +09:00 — 関連回帰完了・全体回帰開始前

- 承認範囲: 変更なし。candidateはまだruntimeへ配備していない。
- 完了済み: orderflow、strategy_engine、API、book update、phase6 integration、market freshness UI、live pipeline、pipeline wiring/absorptionの横断回帰323件が30.02秒で全PASSした。
- 未完了: repository全体回帰、candidate build/recreate、実feed soak。
- 変更file: 直前checkpointから追加変更なし（本checkpointのみ追記）。
- 検証結果: 完成済みorderflow/strategy/live pipelineの関連回帰にcandidate由来のfailureなし。
- blockerの限定範囲: なし。全体回帰で既知baseline failureが再現した場合は、本修正との因果を対象test/source diffで分離する。
- 次の再開位置: repository全体の`pytest -q`を実行する。結果確定前にはimage buildへ進まない。

## 2026-08-07 23:46:03 +09:00 — 全体回帰timeout・candidate build前

- 承認範囲: 初回checkpointと同じ。ここからservice imageのbuild/recreateを行うが、Strategy execution/LIVE注文は有効化しない。
- 完了済み:
  - repository全体の`pytest -q`を実行したが、308秒でcommand timeoutとなり完走しなかった。pytest failure出力はなく、対象横断323件PASSとは分けて記録する。
  - 対象fileの`git diff --check`はPASS。
  - 配備前runtimeはcontainer `delta_engine_pro4web-deltaengine_clone-1`、image ID `sha256:8237efba63482d0f1ebb45ac970bcc6401c9cddf14db346c0f362e1a480c7be1`、started `2026-08-07T13:49:04.739339757Z`、status runningと確定した。
- 未完了: rollback tag作成、candidate image build/recreate、API/log/queue soak、全体回帰timeout位置の追加分離。
- 変更file: 直前checkpointから追加source変更なし（本checkpointのみ追記）。
- 検証結果: candidateに直接関係する回帰は323件PASS。全体回帰はPASSとは扱わず「timeout」とする。
- blockerの限定範囲: 全体回帰の完走確認のみ。対象横断回帰・決定論的負荷比較・static checkが通っているため、実feedで本障害を検証するcandidate配備は継続する。
- 次の再開位置: 現行image IDへrollback tagを付け、candidateをbuildする。build後はimage IDを記録し、serviceのみforce-recreateする。

## 2026-08-07 23:48:23 +09:00 — candidate image完成・service切替前

- 承認範囲: 変更なし。次操作は`deltaengine_clone` service 1個のforce-recreateに限定する。
- 完了済み:
  - 旧imageを`delta_engine_pro4web-deltaengine_clone:rollback-20260807-2346`として保持した。IDは`sha256:8237efba63482d0f1ebb45ac970bcc6401c9cddf14db346c0f362e1a480c7be1`。
  - candidate buildが成功した。新image IDは`sha256:73e8d97c742fdfef451e3f0d7aaba07410404a4a71d43f403853824c62b3a1fe`。
  - candidate image内で変更moduleの`py_compile`がPASSした。
- 未完了: service切替、起動確認、実feed soak、全体回帰timeout位置の追加分離。
- 変更file: 直前checkpointからsource追加変更なし（本checkpointのみ追記）。
- 検証結果: image buildおよびimage内static compileはPASS。runtime GOは未判定。
- blockerの限定範囲: なし。rollback imageを保持済み。
- 次の再開位置: `docker compose up -d --force-recreate deltaengine_clone`でserviceを切り替え、container image ID、起動log、health/stats schemaを確認する。続けてreceiver drop・lag・book syncを時系列監視する。

## 2026-08-07 23:50:34 +09:00 — candidate切替・初期観測完了

- 承認範囲: 変更なし。以後はcandidate runtimeのread-only API/log/CPU監視を行う。
- 完了済み:
  - `deltaengine_clone` serviceのみforce-recreateし、containerがcandidate image `sha256:73e8d97c742fdfef451e3f0d7aaba07410404a4a71d43f403853824c62b3a1fe`で`2026-08-07T14:49:15.564228603Z`に起動したことを確認した。
  - 起動約45秒時点でhealth GREEN、event lag 0ms、sequence gap 0、pipeline exception 0、book synced true、receiver queue 60/10000、receiver high-watermark 78、receiver overflow 0、ws overflow 0、tape drop 0/accounting balancedを確認した。
  - `/api/stats`にqueue name/maxsize/qsize/high-watermark/put/get/overflow/drop-kindが公開され、今回の受信前dropをAPIで直接監視できることを確認した。
- 未完了: queue backlogが時間とともに増えないこと、receiver overflow=0、event lag正常、book sync維持の連続soak。
- 変更file: 直前checkpointからsource追加変更なし（本checkpointのみ追記）。
- 検証結果: 初期起動はPASS。ただし過去の誤判定を避けるため、この短時間GREENだけでは恒久修正GOとしない。
- blockerの限定範囲: なし。`book_projection_state`は初期観測時点でSTALEだったため、soak中に他のmarket freshness stateと合わせて追跡する。
- 次の再開位置: 30〜60秒間隔でhealth、event lag、receiver/ws queue、overflow、book gaps/sync、CPUを採取し、旧runtimeで再発した20分級まで監視を継続する。

## 2026-08-07 23:54:40 +09:00 — 第1candidate NO-GO・追加修正前

- 承認範囲: 初回checkpointと同じ。第1candidateはruntimeで不十分と判定し、source/testへ戻って追加hot-pathを修正する。
- 完了済み:
  - 起動約2〜3分の時系列でreceiver overflowは0だったが、event lagが2,897msから4,569msへ増加し、receiver queueが60から724（high-watermark 868）へ増加、CPU約98〜101%だった。
  - backlog増加が明白なため10分monitorを早期終了し、第1candidateをGOにしなかった。
  - production profileで次点だった`AbsorptionDetector._evaluate()`を分離計測した。10秒窓内5,000 tradeの同一workload 3回は17.322秒、14.809秒、17.648秒（中央値17.322秒）。全tradeごとにwindow全件を再走査するO(n²)処理を確認した。
- 未完了: Absorption windowの増分集計、旧実装との逐tick同値test、再benchmark/関連回帰、第2candidate build/recreate/soak。
- 変更file: 直前checkpointからsource追加変更なし（本checkpointのみ追記）。
- 検証結果: 第1candidateは初期drop=0でもbacklogが増えたためruntime NO-GO。短時間GREENを改善完了とは扱っていない。
- blockerの限定範囲: なし。candidate containerは注文権限を変更せず稼働継続中。rollback imageも保持中。
- 次の再開位置: `AbsorptionDetector`にside別quantity合計とprice出現数を保持し、append/prune時だけ更新する。元のwindowとsnapshot更新規則は保持し、reference実装との逐tick結果/counter一致をtestする。

## 2026-08-07 23:56:35 +09:00 — Absorption増分集計・同値test完了

- 承認範囲: 変更なし。完成済みAbsorptionの判定意味は変更せず、内部集計経路だけを置換した。
- 完了済み:
  - `AbsorptionDetector`へBUY/SELL quantity合計とprice出現数を追加し、trade appendとwindow prune時だけ更新するO(n)総処理へ変更した。window境界、snapshot capture、threshold、stall/replenish、BUY優先、counter増分規則は保持した。
  - pre-optimizationのfull-window scanをtest referenceとして残し、240 tick（window pruneと途中parameter変更を含む）すべてでresult、window aggregate、5種counterの一致を確認した。
  - Absorption/pipeline/realtime display関連17件、`py_compile`、`git diff --check`がPASSした。
  - 同一5,000 trade workloadの3回は0.123秒、0.144秒、0.118秒（中央値0.123秒）。旧中央値17.322秒から約141倍短縮した。events/failure counters/current resultもbenchmark前後で同じだった。
- 未完了: 横断323件再実行、第2candidate image build/recreate、実feed 20分級soak。
- 変更file:
  - `Delta_Engine_Pro4web/src/orderflow/absorption.py`
  - `Delta_Engine_Pro4web/tests/orderflow/test_absorption.py`
  - 本checkpoint
- 検証結果: 単体同値とisolated performanceはPASS。runtime GOは未判定。
- blockerの限定範囲: なし。
- 次の再開位置: 第1candidateと同じ横断test集合を再実行する。PASS後に第2candidate imageをbuildし、serviceを再作成する。

## 2026-08-07 23:57:37 +09:00 — 第2candidate build前

- 承認範囲: 変更なし。次はimage build、image内compile、service 1個のrecreateに限定する。
- 完了済み: 第1candidateと同一のorderflow/strategy/API/live-pipeline横断回帰が、追加同値test込み324件すべてPASS（32.62秒）。
- 未完了: 第2candidate build/recreate、実feed soak、全体回帰timeout位置の追加分離。
- 変更file: 直前checkpointから追加source変更なし（本checkpointのみ追記）。
- 検証結果: source/test candidateはGO。runtimeは未判定。
- blockerの限定範囲: repository全体回帰は前回308秒timeoutのまま。対象横断324件は完走PASSしている。
- 次の再開位置: 第2candidateをbuildし、image IDとimage内compileを確認してからserviceをforce-recreateする。

## 2026-08-07 23:59:41 +09:00 — 第2candidate完成・切替前

- 承認範囲: 変更なし。次操作は`deltaengine_clone` service 1個のforce-recreateに限定する。
- 完了済み: 第2candidate build成功。image IDは`sha256:cdbb731e5f052743f91d96f9dc39fb0fd5aaad363299c9b6eff8df96e5e73dc0`。image内で全変更moduleの`py_compile`がPASS。
- 未完了: service切替、起動確認、実feed 20分級soak。
- 変更file: 直前checkpointから追加source変更なし（本checkpointのみ追記）。
- 検証結果: build/image static checkはPASS。runtime GOは未判定。
- blockerの限定範囲: なし。original rollback imageは引き続き保持。
- 次の再開位置: serviceをforce-recreateし、初期API/log確認後、30〜60秒系列でreceiver backlog/drop・event lag・CPU・book syncを監視する。

## 2026-08-08 00:24:32 +09:00 — 第2candidate runtime GO・作業完了

- 承認範囲: 初回checkpointの範囲内で完了。Strategy execution/LIVE注文/MT5 algorithmic tradingは変更していない。Git commit / pushも行っていない。
- 完了済み:
  - serviceは第2candidate image `sha256:cdbb731e5f052743f91d96f9dc39fb0fd5aaad363299c9b6eff8df96e5e73dc0`で稼働中。全8変更moduleのworktree SHA-256とcontainer内SHA-256が一致した。
  - 起動20分48秒時点で45,354 trades、health GREEN、event lag 131ms、receiver queue 6/10000、receiver high-watermark 546、put/get 57,372/57,366、receiver overflow 0、drop-kind空、ws overflow 0、tape drop 0/accounting balanced、book gap 0、book synced true、projection SYNCEDを確認した。
  - その後の追加観測を含め、receiver queueはburst時最大546まで上がったが0〜1へ繰り返し戻り、10,000へ単調増加しなかった。起動後logに`E9002`/receiver overflow/book gap一致は0件。
  - 22分44秒時点でlatencyのみ一時YELLOW（4,492ms、receiver queue 40、drop 0）になったが、20秒後にGREEN、96ms、queue 0へ回復した。UIのTICK source stale閾値5,000msは超えていない。
  - ブラウザと同じWebSocket接続で`MARKET_HEARTBEAT upstream_fresh=true / pipeline_alive=true`と、その直後のTICK `source_age_ms=1,034`を確認した。server healthだけでなくUI供給経路もfresh。
  - source回帰は横断324件PASS、Absorption旧実装逐tick同値、変更module`py_compile`、全worktreeの`git diff --check`がPASS。
- 未完了: repository全体の単一`pytest -q`は前回308秒timeoutで、全体一括完走結果だけは未取得。今回変更に直接関係する横断324件は完走PASSしている。
- 変更file:
  - `Delta_Engine_Pro4web/src/orderflow/absorption.py`
  - `Delta_Engine_Pro4web/src/orderflow/orderbook.py`
  - `Delta_Engine_Pro4web/src/orderflow/hooks/dom_features.py`
  - `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
  - `Delta_Engine_Pro4web/webapp/book_projection.py`
  - `Delta_Engine_Pro4web/src/acquisition/event_queue.py`
  - `Delta_Engine_Pro4web/src/pipeline.py`
  - `Delta_Engine_Pro4web/webapp/main.py`（既存未commit変更を保持しqueue statsのみ追加）
  - `Delta_Engine_Pro4web/tests/orderflow/test_absorption.py`
  - `Delta_Engine_Pro4web/tests/orderflow/test_orderbook.py`
  - `Delta_Engine_Pro4web/tests/acquisition/test_acquisition.py`
  - 本checkpoint
- 検証結果: runtime GO。旧runtimeの`receiver_out` overflow→raw event drop→60秒級source lag→`TICK_SOURCE_STALE`の再発経路は、20分超の実feedで再現せず、backlog排出能力とUI fresh tickを確認した。
- rollback: `delta_engine_pro4web-deltaengine_clone:rollback-20260807-2346`（image ID `sha256:8237efba63482d0f1ebb45ac970bcc6401c9cddf14db346c0f362e1a480c7be1`）を保持。ただし旧imageは本overflowを再発したため、緊急時以外は戻さない。
- blockerの限定範囲: 全体pytest一括完走のみ。本障害修正のruntime利用を止めるblockerではない。
- 再発時の再開位置: `/api/stats`の`receiver_queue_qsize/high_watermark/overflow_count/dropped_by_kind`と`ws_queue_*`を最初に採取し、`/api/health` latency、book sync/gap、container image IDを同時に記録する。overflow_countが増えた場合は短時間GREENで完了判定しない。

## 2026-08-08 14:16:27 +09:00 — UPSTREAM_NOT_FRESH再発・根因確定とDNS修正前

- 承認範囲: ユーザーの「根本的になおせ」「やれ」を、現行`UPSTREAM_NOT_FRESH`の根因調査、設定修正、service再作成、実feed検証まで行う指示として受領した。LIVE注文・strategy executionは触らない。
- 完了済み:
  - 14:10 JSTのruntimeでhealth REDの主因は`ws_reconnect=166`、pipeline例外0、latency0ms、receiver overflow0だった。queue処理落ちではない。
  - container logで`E2001 connect failed: binance connect failed: [Errno -2] Name or service not known`が連続発生していた。接続URLは`wss://fstream.binance.com/ws`。
  - Docker内`/etc/resolv.conf`はDocker embedded DNS `127.0.0.11`（upstream `192.168.65.7`）であり、当該経路の一時名前解決失敗が166回の再接続とheartbeat `upstream_fresh=false`を生んだ。
  - 現行Docker DNS、`1.1.1.1`、`8.8.8.8`を隔離containerから個別検証し、3経路とも`fstream.binance.com`のA解決が可能であることを確認した。
  - その後feedは自動復帰し、WebSocketで`MARKET_HEARTBEAT upstream_fresh=true / pipeline_alive=true`、TICK source_age 0msを確認した。ただしDocker DNS依存が残るため再発防止としては不十分。
- 未完了: `docker-compose.yml`へ明示DNSを追加、service recreate、DNS固定後の連続実feed監視、再接続増分0の確認。
- 変更file: 直前checkpointからsource追加変更なし（本checkpointのみ追記）。
- 検証結果: 根因はDNS名前解決失敗と確定。単なる画面再読込・queue最適化では本件を直せない。
- blockerの限定範囲: 現在のfeedは復帰済みだが、DNS固定と再作成が完了するまで根本修正GOとはしない。
- 次の再開位置: `docker-compose.yml`の`deltaengine_clone`へ`dns: [1.1.1.1, 8.8.8.8]`を追加し、既存imageでserviceのみ再作成する。起動後に`/etc/resolv.conf`、feed接続、heartbeat、health、reconnect増分を確認する。

## 2026-08-08 14:19:49 +09:00 — 明示DNS反映・初期復帰確認

- 承認範囲: 変更なし。serviceは既存candidate imageのまま、compose DNS設定のみ反映した。
- 完了済み:
  - `docker-compose.yml`の`deltaengine_clone`へ`dns: [1.1.1.1, 8.8.8.8]`を追加し、serviceをforce-recreateした。
  - container `/etc/resolv.conf`で`ExtServers: [1.1.1.1 8.8.8.8]`、`fstream.binance.com`解決成功を確認した。
  - 14:19 JST初期観測でcontainer imageは既存`cdbb731e…`、health GREEN、ws reconnect 0、receiver queue 0、overflow 0、book synced true、trades 193。起動logにE2001/E2002なし。
- 未完了: 明示DNS反映後の連続監視、WebSocket heartbeat fresh、reconnect増分0、overflow/gap未再発の確認。
- 変更file: `Delta_Engine_Pro4web/docker-compose.yml`、本checkpoint。
- 検証結果: DNS root fixは設定・名前解決・初期feed接続までPASS。恒久GOは連続監視後に判定する。
- blockerの限定範囲: なし。現時点でupstreamは接続済み。
- 次の再開位置: 30秒間隔でhealth/ws reconnect/lag、receiver queue/drop、book gap/sync、tradesを採取し、5〜10分継続する。終了時にWebSocket `MARKET_HEARTBEAT upstream_fresh=true`を確認する。

## 2026-08-08 14:27:39 +09:00 — DNS固定後のruntime GO・根本修正完了

- 承認範囲: ユーザーの最新指示範囲内で完了。既存のFlow Price Response、3段チャート、注文実行権限は変更していない。commit / pushは行っていない。
- 完了済み:
  - `docker-compose.yml`へ`dns: [1.1.1.1, 8.8.8.8]`を追加し、serviceをforce-recreateした。container `/etc/resolv.conf`のupstreamが明示DNSへ切り替わった。
  - DNS固定後約8分30秒、12点を30秒間隔で監視した。全点で`health=GREEN`、`ws_reconnect=0`、receiver overflow=0、book gap=0、book synced=true。receiver queueは最大1、high-watermark 40。
  - 最終14:26:38 JSTでhealth GREEN、latency196ms、trades1607、receiver queue0、drop0、book synced true。
  - WebSocket実受信で`MARKET_HEARTBEAT upstream_fresh=true / pipeline_alive=true`、直後TICK `source_age_ms=0`を確認した。
  - DNS固定後10分ログに`E2001`、`E2002`、`Name or service not known`、`UPSTREAM_NOT_FRESH`、`E3004`は0件。対象diffの`git diff --check`もPASS。
- 未完了: なし。本件の再発防止設定と実feed検証を完了。
- 変更file: `Delta_Engine_Pro4web/docker-compose.yml`、本checkpoint。既存candidate image `cdbb731e…`は再buildせず、設定のみ反映。
- 検証結果: 14:07頃の赤帯は、Docker embedded DNSの一時名前解決失敗→E2001再接続166回→`upstream_fresh=false`という因果だった。明示DNS反映後は再接続0、fresh heartbeat、fresh TICKへ復帰したためruntime GO。
- blockerの限定範囲: なし。
- 再発時の再開位置: `/api/health`の`ws_reconnect`とcontainer logのE2001を確認し、`/etc/resolv.conf`のExtServersが明示DNSのままかを最初に確認する。画面再読込だけで済ませない。
## 2026-08-08 18:xx:xx +09:00 — 吸収表示の情報不足修正・変更前

- 承認範囲: ユーザーの「表示し直せ」「吸収が重要なのにおまけ扱い」を、吸収判定ロジックを変更せず、画面で判定根拠を常時確認できる表示へ拡張する指示として受領した。
- 保護境界: Absorptionの判定条件・閾値計算、Flow Price Response、3段チャート、注文実行権限は変更しない。commit / pushは行わない。
- 完了済み: 現状UIが方向・強度・価格帯の要約と、下段の一行`ABSORPTION —`しか表示せず、攻撃出来高・閾値・価格停滞数・判定状態を表示していないことを確認した。
- 未完了: 判定結果への根拠メタデータ追加、主要ABSORPTIONパネルの再設計、下段要約の補助表示、静的検証。
- 変更file: 本checkpointのみ。
- 検証結果: 変更前。次の再開位置は`src/orderflow/absorption.py`と`webapp/push_broker.py`のpayload拡張から開始する。

## 2026-08-08 18:xx:xx +09:00 — 吸収表示の根拠情報追加・source検証完了

- 完了済み: `AbsorptionResult`に攻撃出来高・閾値・停滞価格数を追加（既存result比較の意味は`compare=False`で保持）。push payloadへ同値の情報を追加した。
- 完了済み: 主要ABSORPTIONパネルを方向、ACTIVE、強度、攻撃出来高/閾値、停滞価格数、window秒、価格帯の表示へ変更。下段要約にも強度％を追加した。
- 変更file: `Delta_Engine_Pro4web/src/orderflow/absorption.py`, `Delta_Engine_Pro4web/webapp/push_broker.py`, `Delta_Engine_Pro4web/webapp/static/index.html`, 本checkpoint。
- 検証結果: `tests/orderflow/test_absorption.py` 13 passed、変更module `py_compile` PASS、`git diff --check` PASS。
- 未完了: candidate image build/recreate後のブラウザ供給確認。
- 次の再開位置: `deltaengine_clone` imageをbuildしserviceを再作成、ABSORPTION_STATE payloadとhealthをread-only確認する。

## 2026-08-08 18:20:00 +09:00 — 吸収表示反映・runtime確認完了

- 完了済み: `deltaengine_clone`を新imageでbuildし、serviceのみforce-recreateした。既存のDNS固定設定を維持している。
- 完了済み: 起動後`/api/health`はGREEN、sequence gap 0、ws reconnect 0、pipeline exception 0、latency 0ms、tape drop 0を確認した。
- 完了済み: 関連回帰52件PASS（absorption 13、realtime display/push broker 39）、`py_compile`と`git diff --check` PASS。
- 検証結果: 吸収表示拡張はruntimeへ反映済み。判定ロジック、Flow Price Response、3段チャートは未変更。
- 未完了: なし。commit / pushは行っていない。

## 2026-08-08 18:34:10 +09:00 — 吸収未発生時の表示欠落修正・反映完了

- 完了済み: 吸収が未発生の時も`—`だけにせず、`NO ACTIVE ABSORPTION / MONITORING`、window、stall条件、aggression条件、waiting状態を表示するよう修正した。下段要約も`MONITORING`表示へ変更した。
- 完了済み: JS構文検査と`git diff --check` PASS。新imageでserviceを再作成し、health GREEN、gap 0、reconnect 0、pipeline exception 0、latency 0msを確認した。
- 変更file: `Delta_Engine_Pro4web/webapp/static/index.html`、本checkpoint。
- 未完了: なし。commit / pushは行っていない。
## 2026-08-09 00:xx:xx +09:00 — 統計的大口候補判定 指示書草案作成前

- 承認範囲: ユーザーの「指示書に落とせるか」「まず書いてみる」を、実装を行わず、既存機能を保護した統計的大口候補判定の実装指示書を作成する作業として受領した。
- 保護境界: 既存のFlow Price Response、3段チャート、CVD、Δ、出来高、Tape、固定`large_trade_min_qty`判定、LIVE注文権限を変更しない。commit / pushは行わない。
- 未完了: 指示書草案の作成、ファイル確認。
- 次の再開位置: `ArchitectureRepository/00_Master/`へ草案ファイルを追加する。

## 2026-08-09 00:xx:xx +09:00 — 統計的大口候補判定 指示書草案作成完了

- 完了済み: `STATISTICAL_LARGE_CANDIDATE_IMPLEMENTATION_INSTRUCTION_DRAFT_20260809.md`を追加した。
- 草案の範囲: 既存機能を変更しない並列追加、統計分布・執行群・板反応の特徴量、判定payload、UI分離、保存、回帰、runtime保護、未決事項を定義した。
- 保護境界: 親注文・参加者の識別を主張しない。未検証の大口候補を売買シグナルや注文経路へ接続しない。
- 検証結果: 草案ファイル確認、`git diff --check` PASS。実装・image build・runtime変更は行っていない。
- 未完了: 草案のレビューと閾値・分布期間・cluster時間幅などの仕様確定。ユーザーまたはレビュー担当の指摘を受けて改訂する。

## 2026-08-09 00:xx:xx +09:00 — 統計的大口候補判定 指示書改訂開始

- 承認範囲: 提示されたレビュー指摘A〜Eを反映し、実装指示書の不足を補う文書改訂のみ行う。実装、Docker、runtime、既存機能の変更は行わない。
- 改訂対象: `STATISTICAL_LARGE_CANDIDATE_IMPLEMENTATION_INSTRUCTION_DRAFT_20260809.md`
- 反映項目: Decimal/`float()`禁止、protected files、ADR-003 pipeline配置、push/RTUIF soak、分布保持、Hook/Strategy境界、test_api影響、Replay互換、JSON直列化、外部依存、cluster方式。
- 未完了: 改訂本文の反映と検証。

## 2026-08-09 00:xx:xx +09:00 — 統計的大口候補判定 指示書改訂完了

- 完了済み: A〜Eのレビュー指摘を`STATISTICAL_LARGE_CANDIDATE_IMPLEMENTATION_INSTRUCTION_DRAFT_20260809.md`へ反映した。
- 反映内容: Decimal/`float()`禁止、protected filesと承認境界、ADR-003 single-loop配置、新asyncio task禁止、分布保持方式、RTUIF 3000ms soak gate、Hook/Strategy Engine境界、test_api影響、Replay/live同値、JSON型、外部依存、cluster方式の選択肢。
- 検証結果: 改訂本文の該当項目を`rg`で確認し、`git diff --check` PASS。
- 変更file: 指示書草案、checkpointのみ。実装、Docker、runtime変更なし。
- 未完了: 改訂版に対する次のレビュー。閾値、基準期間、cluster窓、流動性分割、保存期間などの設計判断は未確定のまま保持した。

## 2026-08-09 00:xx:xx +09:00 — 指示書レビュー3点の修正開始

- 承認範囲: 指摘されたSection番号重複、Section 9のRTUIF完了条件欠落、Section 8のReplay/再計算検証の重複を、指示書本文へ限定修正する。実装・Docker・runtime変更は行わない。
- 変更対象: `STATISTICAL_LARGE_CANDIDATE_IMPLEMENTATION_INSTRUCTION_DRAFT_20260809.md`
- 未完了: 本文修正と番号・参照確認。

## 2026-08-09 00:xx:xx +09:00 — 指示書レビュー3点の修正完了

- 完了済み: Section 3を`3.1 必須入力`、`3.2 パイプライン配置と実行モデル`、`3.3 分布の分離`へ整理し、重複番号を解消した。
- 完了済み: Section 9の完了条件へRTUIF soak gate（server/browser最大遅延3000ms未満、receiver/ws overflow 0、drop 0、book gap 0）を追加した。
- 完了済み: Section 8 Step 7をReplay/EventSource経路のlive同値、Step 9を保存済み特徴量・分布スナップショットからの再計算同値として明記した。
- 検証結果: section番号・追加文言を`rg`で確認し、`git diff --check` PASS。
- 変更file: 指示書草案、checkpointのみ。実装・Docker・runtime変更なし。
- 未完了: なし（次のレビュー待ち）。

## 2026-08-09 00:xx:xx +09:00 — 統計的大口候補判定 内容レビュー反映開始

- 承認範囲: 提示された7項目を指示書へ反映する文書修正のみ。実装・Docker・runtime変更は行わない。
- 反映項目: 分布更新順序、個別/cluster重複発火、`book_reaction`列挙値、`evidence`閉じた列挙、tick定義、heavy-tail時のrobust統計、未決事項の決定順序。
- 変更対象: `STATISTICAL_LARGE_CANDIDATE_IMPLEMENTATION_INSTRUCTION_DRAFT_20260809.md`
- 未完了: 本文修正と列挙・順序の検証。

## 2026-08-09 02:xx:xx +09:00 — Stage 1調査レポート作成完了

- 完了済み: 指定されたP-1〜P-8、F-1〜F-5、H-1〜H-5、B-1〜B-7、R-1〜R-6、T-1〜T-5、L-1〜L-4を読み取り専用で調査した。
- 完了済み: `ArchitectureRepository/00_Master/STAT_LARGE_CANDIDATE_STAGE1_REPORT_20260809.md`を作成した。各項目にファイル名・行番号・根拠を記録した。
- 完了済み: レポートSHA-256 `c29155df45bd995b9d9859d4a2138b4275e2d315372632814c567cdfebbac532`、22,291 bytes。
- 検証結果: `git diff --check` PASS。コード、テスト、依存、Docker、runtimeは変更していない。
- 未完了: Stage 1レポートのレビュー・承認。次のStage 2実装には進んでいない。

## 2026-08-09 00:xx:xx +09:00 — cluster_id生成方式の仕様追加完了

- 完了済み: `cluster_id`をランダムUUIDや起動依存連番ではなく、symbol、side、cluster開始UTC時刻、開始trade ID（または正規化price/quantity）から作るcanonical keyのSHA-256決定論的IDとして定義した。
- 完了済み: 個別tradeの`cluster_id=null`、cluster所属イベントの共通ID、trade ID欠損、canonical collision、Replay/live一致を指示書とテスト項目へ追加した。
- 検証結果: 指示書の`cluster_id`仕様と回帰項目を`rg`で確認し、`git diff --check` PASS。
- 変更file: 指示書草案、checkpointのみ。実装・Docker・runtime変更なし。
- 未完了: 次の設計レビュー待ち。

## 2026-08-09 00:xx:xx +09:00 — 統計的大口候補判定 内容レビュー反映完了

- 完了済み: tradeを追加前の分布で評価し、判定後に分布へ追加する順序を固定した。
- 完了済み: 個別`LARGE_CANDIDATE`と`CLUSTER_CANDIDATE`は両方発火し、`cluster_id`でUI groupingする規定を追加した。
- 完了済み: 初期`book_reaction`は`UNOBSERVED`のみ、`evidence`は閉じた列挙、`tick`は取引所tickSize、MADベースrobust値を判定根拠とする規定を追加した。
- 完了済み: 未決事項を流動性分割→基準期間→最低サンプル数→閾値→cluster→板時刻差→保存→UIの順で確定する手順にした。
- 検証結果: section、列挙値、判定順序、決定順序を`rg`で確認し、`git diff --check` PASS。
- 変更file: 指示書草案、checkpointのみ。実装・Docker・runtime変更なし。
- 未完了: 次の設計レビュー待ち。

## 2026-08-09 00:xx:xx +09:00 — cluster_id生成方式の仕様追加開始

- 承認範囲: `cluster_id`の生成方式を指示書へ明記する文書修正のみ。実装・Docker・runtime変更は行わない。
- 方針: Replay/live同値のため、ランダムUUIDやプロセス依存連番を使わず、cluster開始時点から決まる決定論的IDを定義する。
- 未完了: payload、cluster仕様、Replayテスト、完了条件への追記と検証。
