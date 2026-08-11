# Big Trades V2 Phase 6 Completion Report

作成日: 2026-08-12 JST

## 1. 結論

工程6（integration／performance／soak）は完了した。

- `BT2-C001`～`BT2-O296`: 296／296 PASS。
- contract未割当: 0。
- Big Trades target／既存orderflow統合suite: 497／497 PASS。
- repository全体: 1,129 passed、1 known failure、1 skipped。
- 工程0 baselineからの新規failure: 0。
- mandatory performance budget: 11／11 PASS。
- 120秒以上live soak: PASS。
- restart recovery: PASS。
- backfill: dry-runだけ実施し、production mutation 0。
- production feature: `big_trades.enabled=false`のまま。
- production DB migration／write／backfill: 0。
- container restart: 0。

本reportは工程6の完了報告であり、工程7のproduction activation完了報告ではない。

## 2. Git identity／restore基準

- branch: `feature/big-trades-v1`
- 工程6 commit: `2ad12d057311ffe0a079f08708d85a7481298a08`
- restore tag: `pre-big-trades-20260811`
- restore tag object: `8e81cb389d459afa68bb5a85bbe4e593d7bfe19b`
- tracked worktree: 工程6 commit直後clean。
- unrelated untracked user files: stage／変更／削除していない。

Big Trades V2 commit一覧:

1. `9fd7d6f` `docs: lock Big Trades V2 phase 0 baseline`
2. `23128fc` `feat: add Big Trades V2 pure core`
3. `bd7dd38` `feat: add Big Trades V2 configuration and artifacts`
4. `20b5c54` `feat: add Big Trades V2 storage and runtime`
5. `308b757` `feat: add Big Trades V2 web and API surface`
6. `3975828` `feat: add Big Trades V2 browser interface`
7. `2ad12d0` `feat: complete Big Trades V2 integration gate`

## 3. versions／activation状態

- logic version: `BTLOGIC-2.0`
- live soak settings: `bts1_dde49049894d6b1e7a4dc63778827a8869df325663cb6be888cea344bc8842ed`
- live soak activation: `bta1_b4615f66f5aaf20eb2cad384edc041f65c4c25cebfbc9c37704637c81cbcf7cb`
- live soak filter: Manual Min `10`、Max `0`。隔離fixtureだけの値。
- backfill research settings: `bts1_bd6aeb151474272c2f91c01d6e99272f7a0ecbd037631ad8fed91c5e570b6f0a`
- backfill research activation: `bta1_5390675bb2f39f06559930e5b00af268a47f1abc205832e4295c4a637de886d2`
- backfill namespace: `FIXED_RESEARCH`
- production calibration: 未activation。
- production activation: 未実施。

上記のManual値とresearch activationをproduction値として採用していない。

## 4. contract evidence

`contract_evidence_matrix.json`が指示書から296件を抽出し、各contractを収集済みpytest nodeへ割り当て、JUnit結果と照合した。

| 項目 | 結果 |
|---|---:|
| contract | 296 |
| PASS | 296 |
| FAIL | 0 |
| unmapped | 0 |
| collectionに存在しない割当node | 0 |

証跡:

- `contract_evidence_matrix.json`
- `pytest_big_trades_collection.txt`
- `pytest_big_trades.xml`

## 5. repository全体pytest

| 対象 | PASS | FAIL | SKIP | 所要時間 |
|---|---:|---:|---:|---:|
| WebApp以外 | 869 | 0 | 1 | 144.56s |
| WebApp | 260 | 1 | 0 | 25.27s |
| 合計 | 1,129 | 1 | 1 | 169.83s |

唯一のfailure:

```text
tests.webapp.test_dom_tape_fusion_ui::
test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

failure内容は工程0で固定済みの旧selector文字列
`body.phase5-fusion #right>#left{display:none!important}`と現行HTMLの不一致であり、開始前baselineと同一である。新規failureは0。

証跡:

- `pytest_full_core.xml`
- `pytest_full_webapp.xml`

## 6. performance

server microbenchmarkはfull-suite processのallocator状態と外部processの一時的なscheduler割込みを分離するため、独立processで3 trialを実施し、p95／p99はtrial中央値を採用した。各trial raw値も`performance_report.json`へ保存した。

| 指標 | 実測 | budget | 結果 |
|---|---:|---:|---|
| active zone 5,000 total per-trade p95 | 0.114542ms | 0.15ms | PASS |
| active zone 5,000 total per-trade p99 | 0.127054ms | 0.40ms | PASS |
| active zone 5,000 boundary query p99 | 0.022351ms | 0.25ms | PASS |
| cluster finalize p99 | 0.382260ms | 1.50ms | PASS |
| horizon snapshot finalize p99 | 0.265204ms | 1.00ms | PASS |
| daily session transition p99 | 206.9524ms | 500ms | PASS |
| browser 5,000 event＋20,000 interaction merge 最大 | 98.105ms | 150ms | PASS |
| Canvas 2,000 marker＋2,000 zone p95 | 0.1ms | 8ms | PASS |
| mode switch p99 | 0.5ms | 100ms | PASS |
| TICK OFF→ON source age p95差 | 0ms | 1ms | PASS |
| BAR_UPDATE OFF→ON source age p95差 | 0.457ms | 1ms | PASS |

active zone 10／100／1,000／5,000はすべてbudget内。boundary index query hot pathのzone dictionary全scan禁止guard、randomized brute-force一致、price-path range-query randomized一致もPASS。

## 7. 6,000／25,000／queue／Tape／Book

- 6,000 trade: observed／cluster accounting欠落0。
- 25,000 trade: WebSocket／Tape overflowはaccepted、dropped、pendingの総和が入力と一致し、silent drop 0。
- storage queue: high-watermarkとqueue fullを明示counterへ記録。
- Tape: OFF／ON batchとaccountingが完全一致。
- Book: OFF／ON snapshot、gap count、sync状態が完全一致。
- CPU／RSS: boundedness contract PASS。

## 8. live soak／restart recovery

120.181491秒、100 trade／秒、合計12,000 tradeをtemporary isolated DuckDBへ処理した。

| 項目 | 結果 |
|---|---:|
| runtime errors | 0 |
| invalid trades | 0 |
| storage queue full | 0 |
| pending origins／updates | 0／0 |
| events／fills／zones | 120／240／120 |
| interactions／snapshots／checkpoints | 358／234／237 |
| RSS growth | 40,681,472 bytes |
| production mutation | 0 |

restart recoveryはevent／zone identity維持、origin重複0、visible gap、source-order continuity、interaction ordinal continuityを確認した。

証跡: `live_soak_120s.json`

## 9. Big Trades OFF／ON health

productionはOFFのままであり、実serviceのstatusは`DISABLED`。ON比較はproductionを有効化せず、隔離runtime fixtureで実施した。

- TICK source age p95差: 0ms。
- BAR_UPDATE source age p95差: 0.457ms。
- Tape accounting差: 0。
- Book gap／sync差: 0。
- runtime error: 0。
- browser merge collision: 0。
- live soak queue full／drop: 0。

production configは`big_trades.enabled=false`。container `37ed40868792`はrestart count 0、runningであり、工程6でrestartしていない。

## 10. protected chart／既存機能

protected source SHA-256は工程0manifestに対して9／9一致、mismatch 0。

Phase 5実browser evidenceを工程6回帰でも参照した。

- viewport: 1280×900。
- protected `#bottom／#chartwrap／#chart／#main／#center／#right／#tape／#liveobservation／#flowtop`のgeometry delta: 全て0px。
- horizontal overflow: 0px。
- Console error: 0。
- page error: 0。
- failed request: 0。
- before screenshot SHA-256: `f25f172bf0d4b8fbd2ce6b885cf89c16d97af6341f426ce44d3b9211ecda81e7`
- after screenshot SHA-256: `258081239ebc9f8e0f55feecfa36318a762b983678ac49f383bdc70729277c1b`

既存CVD、Footprint、Flow Price Response、Large Trade detector、Tape、DOM pulse、Heatmapの意味と出力を専用回帰で照合した。

## 11. 3件のend-to-end lineage trace

`lineage_traces.json`に、3件それぞれについて次を保存した。

```text
raw trades
  → 40ms same-side cluster
  → accepted BigTrade event
  → exact execution-range Reaction Zone
  → source-ordered interactions
  → 1s／5s snapshots
  → big_trades.js validator＋EventStore＋ReactionZoneStore UI projection
```

3件ともraw fill、cluster summary、event全row、zone全row、interaction履歴、linked event、snapshot、UI marker／zone／history countをID付きで照合し、browser `validated=true`。

## 12. Manual／Automatic equivalence

同一2 fills、同一aggregate quantity `12`に対して、Manual threshold `10`とAutomatic MEDIUM threshold `10`を別々に適用した。

- Manual accepted: true。
- Automatic accepted: true。
- event ID: 同一。
- execution fact比較23 field: 全一致。
- filter mode、settings ID、calibration ID、content hash: lineage差として意図的に別。

「同じexecutionが同じthresholdで受理される」ことと「どの設定で受理したかを隠さない」ことを同時に確認した。

## 13. break／retest／reentry／opposite event trace

origin BUY zone `100..101`のsource-order historyに次を保存した。

```text
ZONE_CREATED
FIRST_EXIT_UP
RELATION_ABOVE
TOUCH_FROM_ABOVE
REENTER_FROM_ABOVE
RELATION_INSIDE
RELATION_BELOW
CROSS_UP
RELATION_ABOVE
...
```

後続SELL event `100..101`はorigin zoneへ独立eventとしてlinkされ、zone identityはmergeされていない。system factsには自動の「absorption confirmed」等を追加していない。

## 14. gap／stale／fail-closed例

- gap: `SOURCE_GAP_STARTED`と`SOURCE_GAP_ENDED`をinteraction履歴とUI gap segmentへ保存。
- stale: 5秒snapshotの`validity=MISSING_STALE`を保存し、price／relationを捏造していない。
- calibration unavailable: Automatic設定にactive calibrationがないfixtureは`accepted=false`、`AUTOMATIC_UNAVAILABLE`、表示status `CALIBRATION_UNAVAILABLE`。
- runtime source gap status: `DEGRADED_SOURCE_GAP`。

## 15. backfill dry-run

production DuckDBは稼働processによりlock中だったため接続せず、read-only Parquet mirrorのcompleted trade shardだけを使用した。

| 項目 | 結果 |
|---|---:|
| selected trade shards | 250 |
| input trades | 42,148 |
| duplicate rows | 0 |
| clusters | 6,608 |
| accepted events／zones | 111／111 |
| fills／interactions／links | 13,109／10,676／542 |
| snapshots／checkpoints | 861／5,515 |
| isolated DuckDB | 11,284,480 bytes |
| temporary output deleted | true |
| production writer connection attempts | 0 |
| production backfill | false |
| production mutation | 0 |

証跡: `backfill_dry_run.json`

## 16. 主な変更file

runtime／core:

- `src/orderflow/big_trades/price_path.py`: append-only range index。
- `src/orderflow/big_trades/zone_index.py`: boundary／interval index。
- `src/orderflow/big_trades/runtime.py`: indexed link候補、horizon heap、ack drain、delayed-link source-order修正。
- `src/orderflow/big_trades/horizons.py`: next horizonとflat canonical hash経路。
- `src/orderflow/big_trades/ids.py`: byte-equivalent flat record canonical hash。
- `src/orderflow/big_trades/reaction_zones.py`: delayed link observation source key。
- `src/orderflow/big_trades/models.py`: immutable derived値cache。
- `src/orderflow/big_trades/time_buckets.py`: UTC fast path。
- `src/database/big_trades_storage.py`: queue high-watermark。

browser／wire:

- `webapp/static/big_trades.js`: 5,000 event＋20,000 interaction bulk hydration、schema reuse、dedup／collision／state復元。
- `webapp/big_trades_protocol.py`: non-Decimal field分類の明示。

検証／運用tool:

- `tests/performance/test_big_trades_phase6.py`
- `tests/performance/big_trades_browser_benchmark.js`
- `tools/big_trades_phase6_benchmarks.py`
- `tools/big_trades_phase6_soak.py`
- `tools/big_trades_phase6_traces.py`
- `tools/backfill_big_trades.py`
- `tools/big_trades_contract_evidence.py`
- 関連orderflow／database／pipeline／WebApp regression tests。

## 17. rollback確認

- 最短停止状態はすでに`big_trades.enabled=false`で維持されている。
- restore tagとobjectを照合済み。
- Big Trades commitは上記7件へ分離済みで、無関係なuser fileを含まない。
- code rollback時はdirty stateを確認後、対象Big Trades commitだけを`git revert`する。`git reset --hard`／`git clean`は禁止。
- Big Trades table／artifact／historyはrollback時に削除しない。

工程6ではproductionを有効化していないため、production config切替・DB backup restore・service restartを伴うrollback実測は行っていない。これは工程7 activation直前／異常時の作業である。

## 18. 残存制約

工程6の未解決blocker: 0。

工程7だけ、次が未実施である。

1. production instrument別の最終Manual Min／Max、またはactive calibration versionの明示確定。
2. initial activation modeとeffective source timeの明示確定。
3. production DB／config backupとrestore実測。
4. production migrationとfeature enable。
5. production health／queue／DB commit／WebSocket continuity／Canvas確認。
6. 30分以上のproduction live soak。
7. production data 3件以上のraw→UI照合。

したがって、現時点の正確な状態は「実装と工程6検証は完了、production activationは未実施」である。

