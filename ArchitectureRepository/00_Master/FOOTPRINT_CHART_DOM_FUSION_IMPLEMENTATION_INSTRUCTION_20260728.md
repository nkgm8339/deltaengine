# DeltaEngine05M Footprint Chart × LIVE DOM 融合実装指示書

作成日時: 2026-07-28 14:58:40 JST
文書状態: **DRAFT — USER REVIEW REQUIRED**
現在の承認範囲: **指示書作成のみ**
実装開始条件: 本指示書に対するユーザーの明示的な実装GO

参照モック:

- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_dom_fusion_mock.html`

---

## 1. 目的

DeltaEngine05Mがすでに計算している各価格帯のFootprintを、単一足の価格表ではなく、
複数足を横方向へ連続表示するFootprint Chartとして読めるようにする。

さらに、現在のOrder BookをFootprintの右端へ同一価格軸で接続し、
次の二つを同じ価格で直接比較できるようにする。

1. 過去に成立した成行約定
2. 現在板に待機している指値流動性

主目的は、攻撃的約定、価格反応、Imbalance、POC、現在の板防御を、
人間が時刻と価格を暗算せず一画面で観測できるようにすることである。

この画面は売買シグナルを作る画面ではない。
既存の独立観測値を見える形へ配置する表示機能である。

---

## 2. 絶対に変更しない範囲

本実装では、次を変更しない。

- Flow Price Responseの検出条件、6時間窓、状態分類、保存、事後成績
- 完成済み3段チャートの計算意味
- PRICE・CVD・Deltaの8パターン判定
- CVD、Delta、Volume、OIの計算
- FootprintのBUY／SELL集計ロジック
- Imbalance detectorの対角比較条件
- Absorption detectorの検出条件
- Flow Event detectorの検出条件
- Strategy Engine、Hook、Condition、Pattern、Order Trigger
- execution権限、`execution_enabled`、HFM発注経路
- raw trade、raw book、Hook journalの削除、修正、truncate

Footprint Chartへ複数の観測値を並べても、単一score、confidence、BUY／SELL判断へ
再統合してはならない。

---

## 3. 現行実装で確認済みの事実

### 3.1 Footprint

- `src/orderflow/footprint.py`は、正規化済み約定価格を価格keyとして使用する。
- 各価格帯へ`buy_volume`と`sell_volume`をDecimalで集計する。
- 形成中足は`current_tick_snapshot()`で取得できる。
- 確定足は`FootprintBar.levels`として価格昇順で得られる。
- WebSocketの`CANDLE`と`BAR_UPDATE`は、画面用に価格降順の
  `footprint.levels[]`を配信する。
- `bid`フィールドはsell volume、`ask`フィールドはbuy volumeである。
- 現在のブラウザは、ページを開いている間の最大300本をメモリへ保持する。

### 3.2 Footprint履歴

- 現行`candles`テーブルはOHLC、Volume、Delta、CVDを保存する。
- 価格帯別Footprintは`candles`テーブルへ保存されていない。
- `/api/history/candles`も価格帯別Footprintを返さない。
- そのため、ページ再読込後は過去足のFootprint価格帯を復元できない。

### 3.3 Order Book

- `OrderBookStateManager`は同期済み板Snapshotを保持する。
- 現行`CANDLE` payloadはOrder Bookを同梱する。
- 現行`BAR_UPDATE` payloadは軽量化のためOrder Bookを明示的に含めない。
- したがって現在のフロントOrder Bookは、確定足配信だけではLIVE DOMとして不十分である。
- 分析経路は全depth updateを処理する。画面配信用の間引きと分析入力を混同してはならない。

### 3.4 現在の未コミット作業

次の関連fileには、Session VWAP等の既存未コミット変更がある。

- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/static/index.html`

実装者はこれらをユーザーの既存作業として保持し、reset、checkout、上書き、巻き戻しを行わない。
本機能の差分を既存変更へ慎重に追加する。

---

## 4. 用語と色の意味

### 4.1 Footprint BID

- 意味: Bidへぶつけたaggressive sell volume
- 配置: 各足の価格帯セル左側
- 色: `#FF4058`

### 4.2 Footprint ASK

- 意味: Askを取ったaggressive buy volume
- 配置: 各足の価格帯セル右側
- 色: `#19C979`

### 4.3 Passive BID Depth

- 意味: 現在板に待機する買い指値数量
- 配置: LIVE DOM列のBID側
- 色: 緑

### 4.4 Passive ASK Depth

- 意味: 現在板に待機する売り指値数量
- 配置: LIVE DOM列のASK側
- 色: 赤

Footprint BIDとPassive BIDは同じBIDという語を含むが意味が異なる。
DOM列の境界へ必ず`LIVE DOM · PASSIVE LIQUIDITY`と表示する。

### 4.5 色の責務

- セル背景の濃さ: 出来高または板数量の大きさだけ
- 緑／赤のセル輪郭と矢印: Imbalance成立
- 黄色: 足別POC、Value Area、visible wall candidate
- シアン: 現在価格、Session VWAP、LIVE DOM境界
- 白: 選択足
- 紫: 既存Divergence用途を維持し、通常Footprint出来高には使用しない

色だけへ意味を依存させず、枠、ラベル、位置を併用する。

---

## 5. 目標画面

### 5.1 水平構造

```text
PRICE
  └─ Footprint bar 1
      └─ Footprint bar 2
          └─ ...
              └─ Footprint LIVE bar
                  └─ LIVE DOM · PASSIVE LIQUIDITY
```

- 左端: 共通価格軸
- 中央: 時間順に並ぶ複数Footprint足
- 右端: 現在のLIVE DOM
- DOMは常に右端へ固定し、過去方向ドラッグで流れない
- FootprintとDOMは同一価格行へ配置する

### 5.2 表示本数

- 標準: 10本
- 最大拡大: 3本
- 最大縮小: 20本
- 初期表示: 最新10本
- マウスホイール: カーソル位置を中心に3〜20本で拡大縮小
- ドラッグ: 過去方向へ移動
- `LIVE LOCK`: 最新形成中足へ復帰

### 5.3 各Footprint足

各足は次を持つ。

- 時刻
- 確定足／形成中足
- 各価格帯の`BID × ASK`
- 中央のローソク足実体とヒゲ
- 足別POC
- VAH／VAL／Value Area
- BUY／SELL Imbalance
- Stacked Imbalance
- Delta
- Volume
- CVD変化量
- OI変化量
- 観測Event marker

`Signal`という項目名は使わず、`EVENTS`とする。
Event markerはAbsorption、Imbalance、Exhaustion、Flow Event等の観測事実であり、
BUY／SELL指示ではない。

### 5.4 LIVE DOM

LIVE DOMは次を表示する。

- Passive Bid quantity
- Passive Ask quantity
- 数量に比例するdepth bar
- Best Bid
- Best Ask
- Spread
- 上位depthの累積数量
- Book Imbalanceの観測値
- Visible wall candidate
- sync状態
- source timeまたはage

Wall candidateは「表示範囲内で相対的に厚い板」であり、
サポート／レジスタンス確定、iceberg、約定保証と表示してはならない。

### 5.5 項目の常設

- データが無い場合も項目名と位置を消さない。
- 値だけを`—`へする。
- DOM gap、resync、stale時に古い値をLIVEとして残さない。
- panelの出現／消失で画面高を変えない。

---

## 6. 価格行と表示集約

Footprintの計算正本は、現在どおり正規化済み約定価格の完全な価格帯データとする。

BTCUSDTの1分足をexchange tickの1段ごとに全表示すると行数が過大になる場合があるため、
チャートには表示専用price bucketを導入する。

### 6.1 原則

- raw Footprint価格帯を変更しない。
- detectorへbucket値を渡さない。
- storageにはraw price levelを保存する。
- bucket aggregationはブラウザ表示境界だけで行う。
- 同じbucketへ含まれるbuy volume、sell volumeを加算する。

### 6.2 PRICE STEP

画面へ次の表示設定を置く。

- `AUTO`
- `1 tick`
- `2 ticks`
- `5 ticks`
- `10 ticks`
- `20 ticks`
- 必要に応じてそれ以上

`AUTO`は、現在表示中の価格範囲を概ね20〜40行で読めるstepへ丸める。
ズーム変更時に計算正本は変えず、表示bucketだけを再生成する。

### 6.3 POCとValue Area

- serverのraw Footprintを正本として保持する。
- chartに表示するPOC／VAは、現在の表示bucketへ集約したvolumeから再計算する。
- tooltipまたは設定欄へ`DISPLAY STEP`を明示する。
- 表示stepを変更した場合、POC／VA表示も同じbucket定義で更新する。

---

## 7. Footprint履歴保存

### 7.1 新規保存単位

確定足の価格帯別Footprintを、既存`candles`とは別の専用tableへ保存する。

推奨table名:

`footprint_levels`

最低限のcolumns:

| column | meaning |
|---|---|
| bar_time | UTC bar start |
| symbol | instrument |
| timeframe | `1m`等 |
| price | raw normalized trade price |
| buy_volume | aggressive buy volume |
| sell_volume | aggressive sell volume |

論理一意key:

`(bar_time, symbol, timeframe, price)`

### 7.2 保存契約

- 確定FootprintBarだけを保存する。
- 形成中足を確定履歴として保存しない。
- 同一bar再処理で二重加算しない。
- BackgroundStorageWriter経由で市場loopをblockしない。
- 既存candles、trades、Flow tablesを変更しない。
- 保存失敗時にpipeline全体を停止させず、healthとlogへ明示する。
- 非正値price、負volume、非有限値を保存しない。

### 7.3 履歴API

新規endpoint:

`GET /api/history/footprints`

query例:

- `limit`
- `before`
- `timeframe`

応答はoldest-firstのbar配列とする。

```json
{
  "bars": [
    {
      "bar_time": "2026-07-28T05:20:00+00:00",
      "timeframe": "1m",
      "levels": [
        {"price": "64520.0", "bid": "12.4", "ask": "18.9"}
      ]
    }
  ],
  "next_before": "..."
}
```

- 初回は最新40本を推奨する。
- 過去ドラッグ時に追加pageをlazy loadする。
- 1リクエストで無制限の価格帯を返さない。
- `bid`はsell volume、`ask`はbuy volumeという現行payload契約を維持する。

### 7.4 過去データ

- 既存raw tradesを削除・修正しない。
- 過去Footprintのbackfillは別操作とし、通常起動時へ無条件で入れない。
- backfillする場合は、非正値約定ガード後のclean境界と現行bar alignmentを使用する。
- backfill件数、期間、reject件数、hashまたは入力manifestを記録する。

---

## 8. LIVE DOM WebSocket契約

### 8.1 新規message

推奨type:

`BOOK_UPDATE`

最低限のpayload:

```json
{
  "event_time": "2026-07-28T05:20:01.123+00:00",
  "last_update_id": 123456,
  "sync_state": "SYNCED",
  "bids": [{"price": "64500.0", "qty": "23.4"}],
  "asks": [{"price": "64520.0", "qty": "45.7"}],
  "depth_levels": 50
}
```

### 8.2 配信周期

- 分析経路: 全depth updateを従来どおり処理
- 表示経路: 最新Snapshotを100〜200ms間隔でcoalesce
- 推奨初期値: 100ms
- queueへ全Snapshotを積まず、表示時点の最新値だけを送る
- UI送信間引きを検出器、Hook、storageへ適用しない

### 8.3 fail closed

次の場合、`SYNCED`として配信しない。

- 初期Snapshot未取得
- update ID gap
- resync中
- empty book
- locked book
- crossed book
- stale

UIは該当時にDOM数量を`—`へし、
`UNSYNCED`、`RESYNCING`、`STALE`等を固定位置へ表示する。

---

## 9. DOM表示集約

Footprintの表示price bucketとDOMのprice rowを一致させる。

- 同じbucketへ入る板数量を合計する。
- BidとAskを別々に集計する。
- Best Bid／Askのraw価格はbucket表示とは別に保持する。
- Spreadはraw Best Ask − raw Best Bidで計算する。
- cumulative depthはbestから外側方向へ加算する。
- current priceを挟んでAskを上、Bidを下へ表示する。

Visible wall candidateは表示補助である。
初期実装では、表示中DOM各sideの数量分布に対する相対上位値として輪郭表示してよいが、
既存Hookの較正済みthresholdやStrategy Conditionと同一視してはならない。
画面上は必ず`WALL CANDIDATE`とする。

---

## 10. 既存3段チャートとの境界

本実装の標準案は次とする。

1. 上側にFootprint × LIVE DOM融合チャート
2. 既存の完成済み3段チャートはその下で維持
3. 3段チャートのPRICE／CVD+Delta／VOLUME比率、Flow帯、8パターンを変更しない
4. Footprint側の足選択と3段チャート側の足選択は、同じbar timeで同期してよい

参照モック下部のCVD、Delta、Volumeは、完成済み3段チャートとの位置関係を示す。
同じpaneを二重実装しない。

参照モックのOI paneについては、次のどちらかを実装前に確定する。

- **A（推奨）**: 現行OI top bar／選択足詳細を維持し、新しい独立OI paneは作らない
- B: Footprint Chart専用の固定高OI paneを追加する

Bは既存3段チャートの変更ではなく独立pane追加として扱うが、
画面高と常設位置が変わるため、ユーザーの明示承認を必要とする。

---

## 11. 既存Order Book panel

融合DOMが本番表示へ入った後、現行の独立Order Book panelと同じ内容を二重表示しない。

推奨:

- DOM融合表示が正常なときは、旧Order Book panelを画面から外す。
- detector、OrderBookStateManager、配信sourceは削除しない。
- DOMがfail closedしても旧panelを自動出現させない。
- DOM列の項目を固定表示し、値だけを`—`へする。

旧panel撤去はpresentationだけであり、Order Book機能停止ではない。

---

## 12. 実装対象file（予定）

### Backend

- `Delta_Engine_Pro4web/src/database/schema.py`
- `Delta_Engine_Pro4web/src/database/storage.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/src/config.py`
- `Delta_Engine_Pro4web/config/config.yaml`

### Frontend

- `Delta_Engine_Pro4web/webapp/static/index.html`

### Tests

- Footprint storage test
- Footprint history API test
- `BOOK_UPDATE` payload test
- DOM throttle／coalescing test
- gap／resync／stale fail-closed test
- Footprint chart DOM structure test
- zoom 3／10／20 test
- price bucket aggregation test
- POC／VA aggregation test
- browser layout and console error test

既存fileの変更範囲は実装時に再監査し、不要なfileを触らない。

---

## 13. 試験条件

### 13.1 計算不変

- 同じtrade入力に対するFootprint raw levelsが実装前後で一致
- 同じFootprintBarに対するImbalance結果が実装前後で一致
- Flow Price Response結果が実装前後で一致
- 8パターン結果が実装前後で一致

### 13.2 履歴

- 確定足だけが保存される
- 同一足再処理で二重加算されない
- 再起動後に最新Footprint履歴が復元される
- lazy loadがbar time順序を壊さない
- price level順序が安定する

### 13.3 LIVE DOM

- 100〜200ms表示周期内で最新Snapshotを配信
- 分析側のdepth event件数を減らさない
- gap時に数量を消して`UNSYNCED`
- resync後に新Snapshotから復帰
- crossed／locked／empty／staleを表示しない
- Best Bid、Best Ask、Spreadがraw snapshotと一致

### 13.4 UI

- 初期10本
- 最大拡大3本
- 最大縮小20本
- wheel anchor維持
- drag history
- LIVE LOCK
- selected bar
- FootprintとDOMの価格行一致
- POC／VA／Imbalance／VWAPの色競合なし
- 項目の出現／消失によるpanel高変動なし
- 1280px以上の対象画面で横overflowなし
- browser console errorなし

### 13.5 回帰

- WebApp対象試験
- Orderflow対象試験
- Storage対象試験
- 全体pytest
- 実Edgeでライブ表示

テスト件数だけを完成根拠にせず、実データで価格行、約定量、板数量、時刻同期を照合する。

---

## 14. 段階実装

### Phase 1 — 契約と保存

- schema
- Footprint確定足保存
- 履歴API
- API試験

### Phase 2 — LIVE DOM配信

- `BOOK_UPDATE`
- latest-value throttle
- sync／gap／stale
- payload試験

### Phase 3 — Footprint Chart

- 共有価格軸
- 3／10／20本
- price bucket
- candle、POC、VA、Imbalance
- lazy history

### Phase 4 — DOM融合

- 右端固定DOM
- Best Bid／Ask
- Spread
- cumulative depth
- wall candidate
- 旧Order Book panelのpresentation整理

### Phase 5 — 統合検証

- 選択同期
- 実ブラウザ
- 再起動復元
- 全回帰
- 文書更新

各Phase完了後にcheckpointを更新する。
blockerが一部に発生しても、独立して安全に進められる試験・文書化を継続する。

---

## 15. Rollback

本機能はpresentationと追加保存経路として分離し、rollback可能にする。

- `BOOK_UPDATE`配信をconfigで無効化可能にする。
- Footprint Chartを無効化した場合、旧単一足Footprint表示へ戻せるようにする。
- 新規`footprint_levels` tableを既存tableから分離する。
- rollback時にraw trades、candles、Flow dataを削除しない。
- 旧Order Book sourceとdetectorを削除しない。

rollbackは表示と新規配信を止める操作であり、保存済み研究データを破壊しない。

---

## 16. 実装前にユーザーが確定する一点

参照モック下部のOI表示について、次を確定する。

1. **A（推奨）: 既存OI表示を使用し、新しいOI paneは追加しない**
2. B: Footprint Chart専用OI paneも常設する

それ以外の主仕様は次で固定する。

- Footprintは連続複数足
- 標準10本、最大拡大3本、最大縮小20本
- Order Bookは右端へ同一価格軸で融合
- LIVE DOMは100ms推奨の表示投影
- 過去Footprintは専用保存とlazy history
- 旧Order Book panelは二重表示しない
- 既存Flow Price Responseと3段チャートの計算は変更しない

---

## 17. Checkpoint

現在時刻: 2026-07-28 14:58:40 JST
承認範囲: 指示書作成のみ
完了済み:

- 3本詳細モック作成
- 連続10本モック作成
- Footprint × LIVE DOM融合モック作成
- 現行Footprint／履歴／Order Book配信経路のread-only確認
- 本実装指示書の作成

未完了:

- ユーザーによる指示書確認
- OI pane方針A／Bの確定
- source code実装
- test追加
- browser実機検証
- PROJECT_MEMORY更新

今回変更したfile:

- `ArchitectureRepository/00_Master/FOOTPRINT_CHART_DOM_FUSION_IMPLEMENTATION_INSTRUCTION_20260728.md`
- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_3bar_mock.html`
- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_reference_mock.html`
- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_dom_fusion_mock.html`

検証結果:

- 3本モックPNG: 1440×900
- 連続10本モックPNG: 1600×1000
- DOM融合モックPNG: 1600×1000
- 稼働中フロントページ変更: なし
- source code変更: なし

blockerの限定範囲:

- 実装開始はユーザーの明示GO待ち
- OI pane追加有無だけ実装前確定が必要

次の再開位置:

1. ユーザーが本指示書を確認
2. OI方針AまたはBを確定
3. Phase 1の最初のsource変更前にcheckpointを更新
