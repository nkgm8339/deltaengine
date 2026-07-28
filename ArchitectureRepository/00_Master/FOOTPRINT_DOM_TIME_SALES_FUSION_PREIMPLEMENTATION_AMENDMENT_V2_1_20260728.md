# Footprint × LIVE DOM × Time & Sales 実装前補遺 V2.1

version: 2.1 amendment
作成日時: 2026-07-28 15:23:50 JST
状態: **APPROVED**
現在の承認範囲: V2.1採用、OI A、Phase 0A remediation
source code実装: 未着手

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
