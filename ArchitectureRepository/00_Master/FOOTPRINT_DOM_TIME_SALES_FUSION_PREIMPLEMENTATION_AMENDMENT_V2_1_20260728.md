# Footprint × LIVE DOM × Time & Sales 実装前補遺 V2.1

version: 2.1 amendment
作成日時: 2026-07-28 15:23:50 JST
状態: **APPROVED**
現在の承認範囲: V2.1採用、OI A、Phase 0A〜0C、GO-5〜GO-11（Phase 1〜6）
source code実装: Phase 1〜Phase 6完了

対象正本候補:

`ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`

本補遺はV2を削除または上書きしない。
V2とV2.1の記述が衝突する場合、本補遺V2.1を優先する。

反映対象:

1. 未コミット変更の復元点
2. Footprint永続化の容量とretention
3. Frontend描画技術
4. Tape sequenceのscope
5. 表示timezone
6. OI A案の技術評価

DeltaEngine実装と無関係なモデル使用量・クレジット消費の記述は、
本指示書へ含めない。

---

## 1. 助言の採否

| no. | advice | decision |
|---:|---|---|
| 1 | Phase 1前に未コミット状態の復元点を作る | **修正して採用** |
| 2 | Footprint levelsの増加量とretentionを決める | **修正して採用** |
| 3 | FootprintをCanvas、Tapeをvirtualized listにする | **採用** |
| 4 | tape sequenceのscopeとreset手順を定義する | **採用** |
| 5 | UTC／JST表示を明記する | **採用** |
| 6 | OIはA案 | **採用・ユーザー確定済み** |

---

## 2. 未コミット変更の復元点

### 2.1 判断

「branchを作るだけ」では未コミット差分の内容を保存できない。
現在のdirty working treeを安全に復元するには、
意図した変更だけを確認済みcommitへ保存した後、
そのcommitから本機能用branchを作る必要がある。

ただし、現状にはsource変更だけでなく、監査DB、capture、debug artifact、
未追跡文書等が含まれる可能性がある。
全fileを無条件に一括commitしてはならない。

したがって、次の手順へ修正して採用する。

### 2.2 Pre-Phase Baseline Gate

Phase 1の最初のsource変更前に、次を行う。

1. `git status --short`で全変更を列挙
2. 各fileを次へ分類
   - intended source
   - intended test
   - intended document
   - runtime data
   - debug capture
   - temporary artifact
   - unknown
3. intended差分をread-only review
4. 関連testを実行
5. commit対象file一覧をcheckpointへ記録
6. ユーザーへcommit対象と除外対象を提示
7. ユーザーの明示承認後にbaseline commit
8. commit SHAをcheckpointへ保存
9. そのcommitからfeature branchを作成

推奨branch名:

`feature/footprint-dom-tape`

推奨baseline commitの意味:

`Session VWAPおよび現在承認済みUI状態の復元点`

実際のcommit messageは、監査後の内容に一致させる。

### 2.3 commit対象外

次を内容確認なしにcommitへ含めない。

- DuckDB／WAL
- WebSocket capture
- JSONL debug capture
- pytest temporary directory
- browser profile
- screenshotの一時生成物
- raw market data
- access denied directory
- source由来不明のartifact

設計モックと承認済み指示書は、ユーザーがbaselineへ含めると承認した場合だけ含める。

### 2.4 権限境界

- 本補遺はgit commit実行を承認しない。
- 本補遺はbranch作成を承認しない。
- commit対象確定後に、ユーザーへ明示承認を求める。
- `git reset --hard`、`git checkout --`は禁止を維持する。

---

## 3. Footprint levels容量試算の訂正

### 3.1 助言値の適用範囲

助言の「一日約1.5万〜6万行」は、
5分足を前提にした概算としては近い。

しかし現行の主Footprintとチャートは1分足である。

1本50〜200 raw price levelsと仮定した単純試算:

### 1分足

```text
1,440 bars/day × 50 levels  = 72,000 rows/day
1,440 bars/day × 200 levels = 288,000 rows/day
```

```text
26,280,000〜105,120,000 rows/year
```

### 5分足

```text
288 bars/day × 50 levels  = 14,400 rows/day
288 bars/day × 200 levels = 57,600 rows/day
```

```text
5,256,000〜21,024,000 rows/year
```

したがって、現行1分足では助言値より大きくなる可能性がある。

実際の価格帯数はvolatility、symbol、exchange tick、normalization、
sessionによって変わるため、仮定だけでretentionを固定してはならない。

---

## 4. Phase 1A Storage Sizing Gate

schemaをproduction固定する前に、保存済みclean tradesからread-only sizingを行う。

### 4.1 最低測定期間

- 24時間以上
- 可能なら72時間
- 低volatilityと高volatilityを両方含む期間

### 4.2 測定項目

- bars
- price levels per bar
  - minimum
  - median
  - p95
  - p99
  - maximum
- rows/day推計
- bytes/row
- bytes/bar
- DuckDB file増加量
- Parquet圧縮後bytes
- latest 40 bars query latency
- previous 40 bars query latency
- 300 bars aggregate size
- index／constraint有無による差
- write batch latency
- background queue high watermark

### 4.3 比較候補

少なくとも次を比較する。

#### A. Normalized row table

1 price level = 1 row

利点:

- SQLが単純
- price level検索が容易
- API成形が明確

欠点:

- row数が大きい
- unique indexが大きくなる可能性

#### B. One bar = nested level collection

1 bar = 1 row、levelsをlist／structとして保持

利点:

- bar単位queryとpayloadへ近い
- row数が小さい

欠点:

- schema、writer、部分検索が複雑
- DuckDB／PyArrow実装検証が必要

production schemaは、測定結果と実装複雑性を並べて決める。

---

## 5. RetentionとArchive方針

### 5.1 原則

- raw tradesはauthoritative sourceとして現行方針を維持する。
- Footprint levelsはraw tradesから再構築可能なderived dataである。
- raw dataをretention対象として削除しない。
- derived Footprintも未検証のまま削除しない。
- archive確認前にhot dataをpurgeしない。

### 5.2 推奨初期案

ユーザー承認前の提案値:

- Hot DuckDB: 直近30日
- Archive Parquet: 期間制限なし
- Partition: UTC dateまたはUTC hour
- Raw trades: 現行保持方針を変更しない

Hot DuckDBから古いderived rowsを外す処理は、
次のarchive verification通過後だけ許可する。

### 5.3 Archive verification

- source row count
- archive row count
- symbol
- timeframe
- min bar_time
- max bar_time
- min price
- max price
- summed buy volume
- summed sell volume
- file SHA-256
- readback test

一致しない場合はhot rowsを維持する。

### 5.4 自動purge境界

- Phase 1では自動purgeを有効化しない。
- sizing reportをユーザーへ提出する。
- retention日数、archive単位、purge実行を別途承認する。
- purgeはderived Footprintだけを対象とする。
- raw trades、candles、Flow、Hook journalへ波及させない。

### 5.5 Unique index

`(bar_time, symbol, timeframe, price)`は論理一意keyとして維持する。

ただし、大規模ART／unique indexを無条件に作成しない。

- indexあり
- indexなし＋append-order／writer idempotency
- nested bar storage

をsizing gateで比較する。

---

## 6. Frontend描画方式

### 6.1 採用方式

次の責務分担を採用する。

| component | technology |
|---|---|
| shared price grid | Canvas |
| Footprint cells／text | Canvas |
| candle／wick | Canvas |
| POC／VA／Imbalance | Canvas |
| Session VWAP／current price | Canvas |
| LIVE DOM depth bars | 同じCanvas |
| controls／status | HTML DOM |
| selected detail／tooltip | HTML DOM overlay |
| Time & Sales | virtualized HTML list |

FootprintとLIVE DOMは同じCanvas／同じgeometry modelで描画し、
価格行の1pxずれを防ぐ。

### 6.2 Canvas理由

最大表示概算:

```text
20 bars × 40 price rows × BID/ASK = 1,600 value cells
```

各cellへwrapper、text、background、border、markerをDOM nodeで作ると、
数千nodeと頻繁なstyle updateが発生する。

Canvasにより次を避ける。

- full DOM rebuild
- layout thrashing
- per-cell style recalculation
- LIVE bar更新時の大量node mutation

### 6.3 Canvas描画契約

- CSS pixelとdevice pixel ratioを分離
- Retina／125%／150% scalingで文字を確認
- `requestAnimationFrame`でdrawを集約
- dirty flagで必要layerだけ更新
- data modelとrender stateを分離
- Canvasサイズ変更時だけfull geometry rebuild
- market updateごとにDOM全体を再構築しない

dirty layer例:

- live Footprint
- DOM depth
- selection
- viewport
- static history

### 6.4 Hit testing

Canvas内選択のため、共通geometryから次を計算する。

- bar index
- bar_time
- price bucket
- DOM side
- selected cell bounds

不可視の推測hitboxを増やさず、
描画に使ったgeometryと同じ値をhit testingへ使う。

### 6.5 Accessibility／exact values

Canvasだけに値を閉じ込めない。

- selected cell detailをHTMLへ出す
- keyboard選択を用意
- tooltipへexact BID／ASK／price／time
- current selectionをscreen-readable textへ反映

### 6.6 Time & Sales virtualization

- browser ring buffer: 500 trades
- visible DOM rows: 20〜40
- scroll位置に応じてrowを再利用
- 一tradeごとに全500 rowを再生成しない
- row click、keyboard、copy可能性を維持

---

## 7. Tape sequence scope

### 7.1 採用scope

`sequence`はserver process／replay session単位とする。

新規field:

`stream_id`

形式:

- UUID
- server process起動時に生成
- replay session開始時に生成

`sequence`:

- `stream_id`内で1から単調増加
- connection単位ではresetしない
- WebSocket reconnect後も同じserver processなら継続

### 7.2 Payload追加

```json
{
  "stream_id": "52d4f9a2-...",
  "first_sequence": 91201,
  "last_sequence": 91218,
  "trades": []
}
```

### 7.3 Client手順

#### 同じstream_id

- expected next sequence = previous last + 1
- 不一致なら`TAPE GAP`
- history hydrate
- `(symbol, trade_id)`でdedup

#### 新しいstream_id

- server restartまたはnew replay sessionとして扱う
- old expected sequenceを破棄
- false gapを出さない
- UIへ`STREAM RESTART`境界を一度表示
- recent Time & Sales historyをhydrate
- `(symbol, trade_id)`でdedup
- new stream sequenceを基準に再開

### 7.4 stream境界

stream_id変更を約定eventとして扱わない。
market direction、signal、Hookへ渡さない。

---

## 8. Timezone契約

### 8.1 Storage／API

- event_time: UTC
- received_time: UTC
- bar_time: UTC
- JSON: timezone付きISO 8601
- internal comparison: UTC epoch

### 8.2 UI default

表示timezoneの初期値:

`Asia/Tokyo`

表示label:

`JST`

Time & Sales:

`HH:mm:ss.SSS JST`

Footprint bar:

`HH:mm JST`

### 8.3 同期

次は同じdisplay timezone formatterを使う。

- Footprint
- Time & Sales
- selected detail
- Flow Event
- OI
- 3段チャート
- tooltip

ブラウザの暗黙local timezoneへ依存しない。

### 8.4 詳細表示

selected detail／tooltipでは次を確認可能にする。

- JST
- UTC ISO
- exchange event time

表示timezoneを変更できるようにする場合も、
storageとAPIのUTC契約は変更しない。

---

## 9. OI方針の技術判断

助言のA案に技術的に賛成する。

採用:

**A — 新しいOI paneを追加しない**

理由:

- Time & Sales追加で横幅と描画負荷が増える。
- Footprint価格行の高さを優先すべきである。
- 現行top barにOI current／1m／5mがある。
- 各Footprint足へ`OI Δ`を置く。
- 選択足詳細にOI OPEN／CLOSE／CHANGE／SAMPLESがある。
- 10秒pollを滑らかな高頻度lineに見せない。
- 完成済み3段チャートを圧縮しない。

2026-07-28、ユーザーが`OIはA`と明示し確定した。

---

## 10. Phase順序の更新

V2のPhase 1前に、次を追加する。

### Phase 0A — Baseline Audit

- dirty inventory
- intended／artifact分類
- current tests
- commit proposal

### Phase 0B — Baseline Commit

- ユーザー承認
- intended filesだけcommit
- commit SHA記録
- feature branch作成

### Phase 0C — Storage Sizing

- 24〜72h read-only sample
- rows／bytes／latency
- row table vs nested comparison
- retention proposal

その後:

- Phase 1 — Footprint storage
- Phase 2 — LIVE DOM
- Phase 3 — TAPE backend
- Phase 4 — Canvas Footprint Chart
- Phase 5 — DOM／Tape融合
- Phase 6 — 統合検証

Phase 0Aはread-onlyで実行できる。
Phase 0Bのcommit／branchはユーザー承認を必要とする。
Phase 0Cはread-only sizingから始める。

---

## 11. 実装GOの分割

安全のためGOを次へ分ける。

### GO-0

V2＋V2.1設計承認

### GO-1

OI A案確定

### GO-2

Phase 0A read-only baseline audit

### GO-3

baseline commit対象とbranch作成の承認

### GO-4

Phase 0C read-only storage sizing

### GO-5

sizing結果を受けたschema／retention承認

### GO-6

Phase 1 source implementation

GO-0だけでGO-3／GO-6まで自動承認されたと解釈しない。

---

## 12. 更新試験条件

### Baseline

- commit対象fileが明示される
- excluded artifactが明示される
- baseline tests
- commit SHA
- branch starting SHA

### Storage

- rows/bar distribution
- 1日／30日／1年推計
- DuckDB bytes
- Parquet bytes
- latest 40 query
- previous 40 query
- archive readback
- no purge before approval

### Canvas

- 3／10／20 bars
- 40 price rows
- DPR 1／1.25／1.5／2
- text readability
- hit testing
- selection
- requestAnimationFrame render
- render p95
- no DOM node growth

### Tape sequence

- same stream reconnect
- new stream restart
- false gapなし
- real gap検出
- history dedup
- replay stream isolation

### Timezone

- UTC storage
- JST default
- millisecond display
- DSTに依存しないAsia/Tokyo
- Footprint／Tape同一時刻同期

---

## 13. Checkpoint

現在時刻: 2026-07-28 15:23:50 JST
承認範囲:

- 助言5項目の評価
- V2.1補遺作成
- source code変更なし
- git commit／branch作成なし

採用:

- Canvas Footprint／LIVE DOM
- virtualized Time & Sales
- stream_id＋process/session scoped sequence
- UTC storage＋JST default display

修正して採用:

- baseline commitは全file一括でなく、監査・承認済みfileだけ
- retentionは5分足概算でなく1分足の実測を基準
- unique indexは無条件作成せずbenchmark

未確定:

- baseline commit対象
- feature branch作成
- Phase 0C GO
- storage schema
- retention日数
- automatic purge
- Phase 1 GO

今回追加したfile:

- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`

source code変更:

- なし

blockerの限定範囲:

- baseline commit／branchはPhase 0B明示承認待ち
- storage sizingはPhase 0C明示GO待ち
- Footprint source実装はPhase 1明示GO待ち

次の再開位置:

1. Phase 0A remediationを完了
2. exact baseline commit対象を再提示
3. ユーザーのPhase 0B承認後にcommit／branch作成

---

## 14. 2026-07-28 GO-5 Decision Record

Phase 0C sizing report提出後のユーザー「GO」を、§11のGO-5として受領した。

承認済みstorage decision:

- A. normalized row tableを採用する。
- `footprint_levels`とsmall `footprint_bar_manifest`を分離する。
- `(bar_time, symbol, timeframe, price)`は論理一意keyとして維持する。
- 4列level ART／unique indexは初期作成しない。
- bar manifestの小さいphysical primary key、bar内price重複検証、single writer
  transactionで冪等性を保証する。
- Hot DuckDBは直近30日をtargetとする。
- Archive ParquetはUTC日次、ZSTD、期間制限なしとする。
- Phase 1ではautomatic purgeをOFFにする。
- raw trades、candles、Flow、Hook journalのretentionは変更しない。

30日はHot targetであり、automatic purge OFFの間は30日を超えたrowsを自動削除しない。
将来のpurgeはarchive verificationと別の明示承認を必要とする。

GO-5で承認されていないもの:

- Phase 1 source implementation
- production schema mutation
- archive／purge jobの有効化
- git commit／push

本節は§13の作成時点statusのうち、Phase 0C GO、storage schema、retention日数、
automatic purgeの未確定状態を更新する。次の承認境界はGO-6である。

---

## 15. 2026-07-28 GO-6／Phase 1 Completion Record

ユーザーの「GO」をGO-6として受領し、Phase 1を実装した。

- normalized levels＋small manifest: 実装完了
- level 4列ART／unique index: 作成なし
- confirmed rollover bar only: 実装・回帰試験完了
- forming／shutdown finalize bar: Footprint履歴保存なし
- UTC日次ZSTD archive: 実装完了
- automatic purge: OFF／未実装
- restart history API: 実装完了
- targeted: 36 passed
- full regression: **622 passed, 1 skipped**
- production data mutation: なし
- commit／push: なし

完了報告:

`FOOTPRINT_DOM_TIME_SALES_PHASE1_COMPLETION_REPORT_20260728.md`

§14の「Phase 1 source implementation未承認」はGO-6により解消した。
次はGO-7（Phase 2 LIVE DOM）である。

---

## 16. 2026-07-28 GO-7／Phase 2 Completion Record

ユーザーの「GO」をGO-7として受領し、Phase 2を実装した。

- `BOOK_UPDATE`: additive payload v1.2として実装完了（envelope `v: 1`維持）
- LIVE DOM sampling: 100ms
- depth: bid／ask各top 50
- projection: read-only latest state、analysis全depth経路のcount不変
- fail closed: no snapshot／resync／stale／empty／locked／crossed／invalid
- reconnect: latest 1件再送
- replay: projector非起動
- targeted: **112 passed**
- full regression: **632 passed, 1 skipped**
- production data mutation: なし
- commit／push: なし

完了報告:

`FOOTPRINT_DOM_TIME_SALES_PHASE2_COMPLETION_REPORT_20260728.md`

次はGO-8（Phase 3 TAPE backend）である。

---

## 17. 2026-07-28 GO-8／Phase 3 Completion Record

ユーザーの「GO」をGO-8として受領し、Phase 3を実装した。

- accepted-trade source: DataNormalizer正常受理直後。`TICK`からの再構成なし
- Live／Replay: 共通observer、duplicate／invalid除外、例外隔離
- batch: 100ms、最大250件、pending capacity 10,000、drop oldest
- stream: process／replay session scoped UUID、sequenceはstream内1始まり
- gap: overflow／send failureをsequence gapと`dropped_count`で明示
- accounting: `accepted = sent + pending + in_flight + dropped`
- reconnect: 同一stream継続、Tape batch非cache、新streamでclient gap state reset
- WebSocket: additive `TAPE_UPDATE` payload v1.3（envelope `v: 1`維持）
- history: 最大500件、oldest-first、exact notional、UTC、symbol、複合cursor
- replay: replay accepted tradeだけを配信し、live tape非混在
- targeted: **113 passed**
- full regression: **644 passed, 1 skipped**
- production data mutation: なし
- commit／push: なし

完了報告:

`FOOTPRINT_DOM_TIME_SALES_PHASE3_COMPLETION_REPORT_20260728.md`

次はGO-9（Phase 4 Canvas Footprint Chart）である。

---

## 18. 2026-07-28 GO-9／Phase 4 Completion Record

ユーザーの「GO」をGO-9として受領し、Phase 4を実装した。

- renderer: Canvas。Footprint price cellのDOM nodeは作成しない
- bars: 初期10、control 3／10／20、wheel 3〜20、drag history、LIVE LOCK
- axis: 全表示足の共通価格軸、20〜40 virtual rows
- display step: AUTO／1／2／5／10／20 ticks、raw levels非変更
- statistics: display bucket後にPOC／VA／diagonal Imbalance／Stackedを再計算
- layers: static history、live Footprint、reference、selectionのdirty redraw
- scale: CSS pixel hit testing＋DPR backing store 1／1.25／1.5／2
- history: latest40 hydrate、exclusive cursor lazy load、`bar_time` dedup
- accessibility: pointer／keyboard、HTML exact detail、screen-readable selection
- timezone: 足はJST、detailはJST＋UTC ISO＋exchange `bar_time`
- 3-bar detail: Delta／Volume／CVD Δ／OI Δ／EVENTS
- actual Edge warm full render p95: **7.3ms**
- actual Edge reference partial render p95: **0.4ms**
- Phase 4対象: **5 passed**
- WebApp対象回帰: **67 passed**
- full regression: **649 passed, 1 skipped**
- production data mutation: なし
- commit／push: なし

完了報告:

`FOOTPRINT_DOM_TIME_SALES_PHASE4_COMPLETION_REPORT_20260728.md`

次はGO-10（Phase 5 DOM／Tape frontend融合）である。

---

## 19. 2026-07-28 GO-10／Phase 5 Completion Record

ユーザーの「GO」をGO-10として受領し、Phase 5を実装した。

- LIVE DOM: Footprintと同じCanvas price geometryへ固定列として融合
- passive depth: Bid green／Ask red、Best cyan、visible wall yellow
- fail closed: stale／unsynced／disconnect時は古い数量を表示しない
- partial render: `BOOK_UPDATE`は`liveDom` dirty layerだけを更新
- Time & Sales: 右端固定、recent 500件ring、32 row再利用virtual list
- actual viewport: 15px row、実Edgeで23行表示
- filter: side、minimum quantity、minimum notional、large-only
- large trade: 常設threshold、黄色outline
- stream: same-stream sequence gap／drop表示、new-stream reset／restart表示
- history: 最大500件hydrate、`(symbol, trade_id)` dedup
- selection: Tape／Footprint／LIVE DOMをbar time＋display bucketで同期
- timezone: 一覧JST、detailでJST millisecond＋UTC ISO＋exchange event time
- old Order Book: presentationから除外、source／detectorは維持
- target: **12 passed**
- full regression: **656 passed, 1 skipped**
- actual Edge: page error 0、横overflowなし
- production data mutation: なし
- commit／push: なし

完了報告:

`FOOTPRINT_DOM_TIME_SALES_PHASE5_COMPLETION_REPORT_20260728.md`

次はGO-11（Phase 6 restart／reconnect／replay／live no-loss統合検証）である。

---

## 20. 2026-07-28 GO-11／Phase 6 Completion Record

ユーザーの「Go」をGO-11として受領し、Phase 6を完了した。

- replay speed: 0=fast、正値=source event time倍率としてruntime接続
- replay callbacks: worker threadからWebApp loopへthread-safeに転送
- replay Tape time: batch末尾accepted tradeのmarket time
- replay isolation: live OI／LIVE DOM projector／live shadow writeなし
- restart: new stream UUID、sequence 1、履歴を新connectionから復元
- reconnect: same stream継続、Tape batch非cache、Book latest 1件、history dedup
- accounting: 6,000 accepted = 6,000 sent、drop 0、balance true
- overflow: 25,000 accepted = 10,000 sent + 15,000 dropped、gap明示
- browser: 500 ring、23 visible rows、32 pool、page error 0、横overflowなし
- target: **186 passed**
- full regression: **661 passed, 1 skipped**
- production data mutation: なし
- commit／push: なし

実装／隔離統合はPASS。ただし現稼働環境は旧v3.6.21、Parquet I/O errorでRED、
Cドライブ空き約0.72 GiBのためdeployment／operational activationはNO-GOとした。

完了報告:

`FOOTPRINT_DOM_TIME_SALES_PHASE6_COMPLETION_REPORT_20260728.md`

次はdisk／storage保全、旧dead container対応、新image配備の別承認境界である。

---

## 21. 2026-07-28 Operational Remediation Completion Record

追加承認により、Phase 6後のdisk／storage remediationとproduction activationを完了した。

- 削除: 存在しない`D:\MT5XM`由来の旧XMTrading `.hc`／`.hcc` history cacheのみ、
  21,260 files／97,337,847,530 bytes
- 保持: DeltaEngine data、現HFM、共通quote、旧terminal MQL5／ticks、raw／archive／research
- C空き: 約0.97 GiB → 削除直後91.67 GiB、最終82.82 GiB
- deploy image: `sha256:81b5ae72cb4ff2847a914e71863c4870ba2a1383bc6f47983c00d203f7ab5e01`
- image内Phase 1〜6対象: **116 passed, 4 skipped**
- production: storage pending 0、Footprint failure 0、Book SYNCED、Tape drop 0／balanced true、
  Hook drop／disk reject／writer error 0
- browser: Tape LIVE、DOM SYNCED、Footprint LIVE、3段チャート表示、page／console error 0
- reconnect最終eventから15分後の23:34:23 JST: 全health check GREEN
- 23:37 JST: 新しいBinance ping timeout／book gapでoverall YELLOW。ただし
  pipeline／bar／latency／Tape／storage／Bookは正常
- deploy後log: StorageError／Traceback／Parquet I/O error再発なし

production operational activationは**PASS**、Binance upstream feed degradationはACTIVE。
API versionはbumpしておらず`v3.6.21`表示のままなので、image IDをdeployment identityとする。
exact旧imageでなくpre-Footprint fallback rollback imageを保持した。

完成済みFlow Price Response、3段チャート、8パターン、OIを変更せず、
Strategy runtime／注文authorityも拡張していない。

完了報告:

`FOOTPRINT_DOM_TIME_SALES_OPERATIONAL_REMEDIATION_REPORT_20260728.md`
