# 統計的大口候補判定 — 実装指示書（草案）

## 0. この文書の目的

公開約定・板データから、個別参加者や親注文を特定せずに、通常の約定分布から外れた「大口執行らしいイベント」を統計的に検出する。

この機能は、既存のFlow Price Response、三段チャート、CVD、Δ、出来高、Tapeの計算・表示を置き換えない。既存機能と並列に追加し、判定根拠を保存・表示できる状態を作る。

## 1. 用語と禁止事項

### 1.1 用語

- `large_candidate`: 統計的に大きい約定または執行群。親注文・参加者本人の確定ではない。
- `trade_event`: 正規化済みの個別約定。
- `execution_cluster`: 短時間・同一方向に連続した約定群。同じ親注文であることは仮定しない。
- `reference_distribution`: 比較対象となる直近の約定分布。
- `impact`: 執行後の価格変化、価格帯進行、または板反応。

### 1.2 禁止事項

- `large_candidate`を「大口確定」「親注文確定」「大口本人」と表示しない。
- 既存の固定`large_trade_min_qty`判定を、統計判定で勝手に置換しない。
- 直近データの中央値だけを根拠に、恣意的な金額閾値を決めない。
- CVD、Δ、価格反応だけから大口と断定しない。
- 未検証の`large_candidate`を売買シグナル、勝率、確率として表示しない。
- Binance公開データにない注文ID、親子関係、参加者識別子を生成しない。

### 1.3 数値型の鉄則

- `price`、`quantity`、`notional`、出来高、閾値、分位点、z-score、MAD、価格変化など、すべての価格・数量・金額・統計量はPythonの`Decimal`で扱う。
- `float()`は禁止する。暗黙のfloat変換、JSON decode後のfloat計算、numpy/scipy等によるfloat化も禁止する。
- JSONへ出すDecimalは文字列へ直列化する。件数、秒、tick数、順位などの整数だけJSON numberを許可する。
- Decimal計算の丸め、精度、ゼロ除算、非有限値の扱いをテストで固定する。

### 1.4 Protected filesと承認境界

以下は既存機能の保護対象であり、初期実装では変更しない。

- `webapp/static/orderbook_heatmap.js`
- `webapp/static/time_sales.js`
- `webapp/static/footprint_canvas.js`
- `src/orderflow/flow_price_response.py`
- `webapp/static/index.html`の既存三段チャート・Flow Price Response描画部分

上記へ表示接続が必要になった場合は、変更理由、影響範囲、代替案、回帰項目を指示書へ追記し、明示承認を得る。初期実装は新規の独立module/UI領域で完結させる。

## 2. 現状との境界

現状には次の既存判定がある。

- バックエンドの固定数量判定: `flow_detector.large_trade_min_qty`（現行既定値5.0 BTC）
- Time & Salesの手入力金額フィルタ: `LARGE ≥`
- Sweep、Tape、Exhaustion等の既存FlowEvent

統計的大口候補判定は、これらを変更せず別モジュール・別イベント種別として追加する。

既存Hook Detectorの`large_trade`、`large_market_buy/sell`、`large_buy_cluster/sell_cluster`等とは独立並行とする。同一時刻に両方が発火した場合も各イベントを別の`detector`名で保存し、黙って統合しない。

統計判定の出力をStrategy Engine、365 variants、predicate入力、risk gate、注文経路へ接続することを禁止する。runtime activation zeroを維持する。

既存のFlow Price Responseおよび三段チャートの背景帯は変更しない。統計的大口候補を背景帯へ自動的に混ぜない。

## 3. 判定対象データ

### 3.1 必須入力

各tradeについて次を使用する。

- `event_time`
- `symbol`
- `side`（BUY / SELL）
- `price`
- `quantity`
- `notional = price × quantity`
- `trade_id`（利用可能な場合）

板反応を判定する場合は、tradeの時刻以前・直後で同期できるbook snapshotを使用する。ただし板snapshotがないイベントは、約定分布判定だけで処理し、板反応を未観測として記録する。

### 3.2 パイプライン配置と実行モデル

- 分布収集器は`src/orderflow/`配下の独立した同期moduleとして実装する。
- 正規化済みtradeを、既存のsingle-loop market-data処理が既存detectorへ渡す同じ段階で、読み取り専用に渡す。
- 新しいasyncioタスク、thread、process、executor、queue consumerを追加しない。ADR-003（single-loop/no-threads）を維持する。
- 分布更新はO(1)または償却O(log n)を目標とし、tradeごとの全履歴再走査を禁止する。
- 実装前に`pipeline.py`の既存trade正規化→detector→storage/pushの接続点を調査し、変更hunkを限定する。

### 3.3 分布の分離

比較分布は少なくとも次の条件を混ぜない。

- symbol
- side（BUY / SELL）
- quantity と notional
- 必要に応じて時間帯・流動性状態

分布を共有する場合は、その理由と歪みをテストで明記する。

## 4. 統計的判定

### 4.1 個別約定

判定の時間順序を固定する。**trade Aは、Aを分布へ追加する前のreference_distributionで評価し、判定イベントを生成した後にAを分布へ追加する。** A自身を自分の分位点・外れ値計算へ含めない。分布更新後の状態は次のtradeから使用する。

個別約定について、少なくとも次を計算する。

- quantityの分位点
- notionalの分位点
- MADベースのrobust z-score（初期判定の唯一の外れ値根拠）
- 通常のz-scoreは保存可能な参考値だが、判定条件・candidate根拠・UI表示には使用しない
- 直近分布のサンプル数
- 分布の更新時刻

最低限、`sample_count`が設定値未満の場合は判定を`INSUFFICIENT_SAMPLE`とし、large候補を出さない。

分布保持は、初期実装ではメモリ内rolling windowを基本案とする。DuckDB/Parquetは履歴保存と再計算用とし、live判定の都度DBを読まない。rolling windowの上限、symbol単位のメモリ量、再起動時のwarm-start方法を実装前に決める。

### 4.2 執行群

個別約定だけではなく、短時間の同方向連続執行を別イベントとして評価する。

- cluster window
- 同方向trade数
- 累積quantity
- 累積notional
- 価格帯数
- 最初と最後の価格
- 価格進行幅
- 分布に対する累積量の分位点

同一親注文であるとは扱わず、`execution_cluster`という観測上の名称を使う。

個別tradeの`LARGE_CANDIDATE`と、そのtradeを含む`CLUSTER_CANDIDATE`は**両方発火させる**。2つを黙って統合・相殺しない。各イベントに共通の`cluster_id`（親注文IDではなく、同一判定窓に属する表示用グループID）を付け、UIでは同一`cluster_id`を視覚的にグルーピングする。個別イベントとclusterイベントの二重pushによる負荷を計測し、RTUIF gateを満たさない場合はUI側で折り畳むが、サーバー側の観測イベントを勝手に削除しない。

`cluster_id`はReplay/liveで一致する決定論的な文字列とする。ランダムUUID、プロセス起動ごとの連番、wall-clockの現在時刻は使用しない。canonical keyは次の順序で構成する。

```text
STATCL1|symbol|side|cluster_start_event_time_utc_ms|cluster_start_trade_id
```

- `symbol`と`side`は正規化済み値を使用する。
- `cluster_start_event_time_utc_ms`はclusterに属する最初のtradeのexchange event timeをUTC epoch millisecondsへ正規化する。
- `cluster_start_trade_id`は最初のtradeのexchange trade IDを文字列化する。
- trade IDがない入力では、canonical keyへ`NO_TRADE_ID|price|quantity`（Decimalの正規化文字列）を追加する。
- canonical keyをUTF-8でSHA-256化し、`cluster_id = "sc1_" + lowercase_hex_digest`とする。
- 同一canonical keyが同一symbol stream内で再登場する場合は、入力列の順序に依存する連番で上書きせず、`collision_index`をcanonical keyへ含めて再現可能にする。collisionはテストで発生条件を固定する。

`cluster_id`は親注文ID、注文ID、参加者IDを意味しない。cluster境界（開始・終了・再開）は同じevent_time列から同じ結果になることを必須とする。

cluster方式の検討対象は次の3つに限定する。

- 固定時間窓: 直近Nミリ秒を常に評価
- スライディング窓: trade到着ごとに期限切れを除去して評価
- イベント駆動: 同方向・価格連続性などの開始条件で開始し、終了条件で確定

初期実装の候補はスライディング窓とし、固定時間窓・イベント駆動との差をテストベクトルで比較してから確定する。窓幅、価格許容幅、side分離、終了条件を未決のまま実装しない。

### 4.3 判定状態

判定状態は少なくとも次を持つ。

- `NORMAL`
- `LARGE_CANDIDATE`
- `CLUSTER_CANDIDATE`
- `INSUFFICIENT_SAMPLE`
- `INVALID_DATA`

`LARGE_CANDIDATE`の根拠は、単一の閾値ではなく、判定に使った特徴量をpayloadへ保存する。

### 4.4 板反応の初期範囲

初期実装の`book_reaction`は`UNOBSERVED`のみを許可する。板の消失、補充、吸収、反発などの分類は初期実装の判定・payload・UIに追加しない。板反応分類は、同期許容差、snapshot欠損、判定条件、回帰を別途定義したフェーズ2で扱う。

### 4.5 evidence列挙

初期実装の`evidence`は次の閉じた列挙値だけを許可する。

- `QUANTITY_TAIL`
- `NOTIONAL_TAIL`
- `QUANTITY_MAD_OUTLIER`
- `NOTIONAL_MAD_OUTLIER`
- `SAME_SIDE_CLUSTER`
- `CLUSTER_NOTIONAL_TAIL`
- `CLUSTER_QUANTITY_TAIL`

列挙値を追加する場合は、意味、生成条件、既存保存データへの影響、テストを指示書へ追記する。`book_reaction`由来のevidenceは初期実装では追加しない。

### 4.6 信頼度の扱い

信頼度を表示する場合、真の大口である確率とは呼ばない。

表示可能な名称は、例えば次のいずれかに限定する。

- `EXTREMENESS`
- `DISTRIBUTION RANK`
- `EVIDENCE COUNT`

統計的な特徴量を機械学習で一つの確率へ圧縮しない。導入する場合は、学習データ、正解ラベル、評価方法を別文書で定義する。

## 5. 判定イベントのpayload

新イベント種別は既存`FLOW`を破壊せず、`STATISTICAL_LARGE_CANDIDATE`として追加する。

必須payload:

```json
{
  "state": "LARGE_CANDIDATE",
  "symbol": "BTCUSDT",
  "side": "BUY",
  "event_time": "...",
  "cluster_id": null,
  "price": "...",
  "quantity": "...",
  "notional": "...",
  "quantity_percentile": "...",
  "notional_percentile": "...",
  "sample_count": 0,
  "reference_window_sec": 0,
  "cluster_trade_count": 0,
  "cluster_quantity": "...",
  "cluster_notional": "...",
  "price_levels": 0,
  "price_progress_ticks": 0,
  "book_reaction": "UNOBSERVED",
  "evidence": ["NOTIONAL_TAIL", "SAME_SIDE_CLUSTER"],
  "is_parent_order": null,
  "is_participant_identified": false
}
```

`is_parent_order`は公開データから判定できないため、常に`null`または未提供とする。`is_participant_identified`は常に`false`とする。

`price_progress_ticks`のtickは、対象symbolの取引所`tickSize`（Binance exchangeInfo等で取得した最小価格刻み）を意味する。BTCUSDTでtickSizeが0.10 USDなら、価格進行0.30 USDは3 ticksとなる。tickSizeを取得できない場合は値を計算せず`null`とし、別の丸め幅や表示桁数をtickとして代用しない。

payload中のDecimal値はすべてJSON文字列で送る。`sample_count`、`reference_window_sec`、`cluster_trade_count`、`price_levels`、`price_progress_ticks`は整数JSON numberとする。nullは未観測・未計算を表し、0とは区別する。

新イベントをpushする場合は、`push_broker.py`の既存PriorityQueue、送信失敗、stale判定、ブラウザqueueへの影響を測定する。イベントは既存TICKを遅延させない。RTUIF soak gateとして、server/browserの最大遅延3000ms未満、receiver/ws overflow 0、drop 0、book gap 0を満たすまでGOとしない。

## 6. UI要件

### 6.1 表示場所

既存の三段チャート、Flow Price Response帯、CVD、Δ、出来高を変更しない。

追加表示は次のいずれかの独立領域とする。

- Time & Salesの大口候補行
- 大口候補イベント一覧
- DOM / Tapeと時刻同期したイベントマーカー

### 6.2 表示内容

画面には少なくとも次を表示する。

- `LARGE CANDIDATE`または`CLUSTER CANDIDATE`
- BUY / SELL
- 約定量・金額
- 分布順位
- サンプル数
- 連続執行量・件数
- 価格進行幅
- 板反応（観測済み／未観測）
- 判定根拠の一覧

「大口」「親注文」「勝率」「追随推奨」という表示は禁止する。

初期UI接続で`orderbook_heatmap.js`、`time_sales.js`、`footprint_canvas.js`を変更しない。独立panelまたは既存pushを読み取る別表示を優先する。protected fileを変更する案はレビュー後の別承認とする。

### 6.3 UIでの意味分離

- 固定数量の`LARGE`表示
- 手入力金額の`LARGE ≥`
- 統計判定の`STATISTICAL LARGE CANDIDATE`

を同じものとして表示しない。各判定の定義と閾値を画面上で確認できるようにする。

## 7. 保存と検証

### 7.1 保存

判定イベントと、判定時点の特徴量を保存する。後から閾値・分布・判定結果を再計算できる形式にする。

### 7.2 回帰テスト

最低限、次を追加する。

- 分布サンプル不足時に候補を出さない
- 同一入力が同じ判定を返す
- 同一入力が同じ`cluster_id`を返し、liveとReplayで`cluster_id`が一致する
- trade IDあり／なし、同一canonical key衝突時の`cluster_id`生成が決定論的である
- BUY / SELL分布を混ぜない
- quantityとnotionalの単位を混同しない
- 異常値・非正値・未来時刻を拒否する
- cluster window境界が決定論的である
- 既存LargeTradeDetectorの結果が変わらない
- 既存Flow Price Responseと三段チャートのpayload・表示が変わらない
- WebSocket切断・再接続時に分布が二重加算されない
- 実装開始時に`tests/webapp/test_api.py`、`test_push_broker.py`、`test_absorption_realtime_display.py`、既存orderflow/pipeline回帰への影響を調査し、影響なしまたは必要な期待値更新を記録する
- Replay/EventSourceで同じtrade列を流した場合、liveと同じ候補・特徴量が再生成される
- Replay warm-start時にseed済み分布がliveで二重加算されない

### 7.3 統計評価

正解ラベルが存在しないため、最初から「大口判定の正解率」と呼ばない。

まず評価するのは、次の再現性と条件付き観測値である。

- 同じ記録から同じ候補が再生成されるか
- 候補の分布順位が安定しているか
- 候補後の価格進行、停滞、逆行
- 通常イベントとの条件付き差
- 時間帯・流動性別の性能差

結果は`研究結果`として保存し、未検証のまま売買シグナルへ接続しない。

Replayは既存EventSource経路を使い、別の統計計算経路を作らない。Replay開始時の分布初期化、warm-start範囲、未来データ混入防止、live/replayのevent_time順序をテストで固定する。

外部統計ライブラリ（scipy、numpy等）は初期実装で追加しない。Decimalを維持する自前の分位点、中央値、MAD計算を実装する。外部依存が必要な提案は、Decimal変換、Docker image容量、起動時間、既存requirementsへの影響を別途提示し承認を得る。

## 8. 実装順序

1. `pipeline.py`、既存Hook Detector、`push_broker.py`、Replay/EventSource、`test_api.py`を調査し、接続点・protected file・回帰影響を記録する。
2. 既存テストと現在の判定を固定する。
3. 分布収集器を読み取り専用で追加する。
4. 個別約定の統計特徴量を生成する。
5. 執行群の候補を生成する。
6. 新イベントpayloadを追加する。
7. Replay/live同値を検証する（同じEventSource経路で、同じtrade列から同じ候補・特徴量が出ることを確認する）。
8. 独立UIへ表示する。
9. 保存済み特徴量と分布スナップショットからの再計算同値を検証する（保存値を再読込して同じ判定・順位・根拠を再生成できることを確認する）。
10. RTUIF soak gateを含め、runtimeでCPU、queue、drop、latencyを監視する。
11. 実績評価が終わるまで既存シグナル・注文経路へ接続しない。

## 9. 完了条件

- 既存のFlow Price Response、三段チャート、CVD、Δ、出来高、Tapeの回帰が全てPASS
- 固定`large_trade_min_qty`判定の出力が変更されていない
- 統計判定の入力、分布、サンプル数、特徴量が再現可能
- 大口候補と親注文・参加者識別を明確に分離
- UI上で判定根拠を確認できる
- 記録データから同一候補を再生成できる
- runtimeのreceiver overflow、event lag、book gapを悪化させない
- RTUIF soak gate（server/browser最大遅延3000ms未満、receiver/ws overflow 0、drop 0、book gap 0）を通過する
- 有効性未検証の状態で売買シグナル・注文実行へ接続しない

## 10. 未決事項と決定順序（実装前に決める）

未決事項には相互依存があるため、次の順序で設計判断を確定する。

1. **流動性状態の分割方法**（出来高、板厚、spread等の観測値と分割境界）
2. **分布の基準期間**（状態ごとのrolling期間、warm-start範囲）
3. **最低サンプル数**（状態ごとに判定を許可する下限）
4. **分位点・MAD外れ値の閾値**（heavy-tailを前提にrobust値を採用）
5. **cluster時間幅・価格許容幅・終了条件**
6. **板snapshot許容時刻差**（フェーズ2で使用する場合のみ）
7. **保存期間・再計算方式**
8. **独立UIの配置とcluster折り畳み表示**

実装者が順序を飛ばして中央値、固定金額、任意のcluster窓を決めてはならない。各決定は、根拠、データ量、メモリ/CPU影響、回帰項目を追記して指示書を改訂する。
