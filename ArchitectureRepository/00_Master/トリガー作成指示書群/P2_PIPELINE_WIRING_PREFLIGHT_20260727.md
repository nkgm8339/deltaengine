# P2 Pipeline配線 v1 — Stage 1 Pre-flight結果

作成日: 2026-07-27 JST
判定: **FAIL — Stage 2停止**

## 1. 結果

Pre-flight結果:

1.1 CvdResult: **FAIL**（`symbol`、`event_time`、`tick_delta`、`tick_cvd`が`CvdResult`直下にない）
1.2 FlowResponseSnapshot: **PASS**
1.3 OrderBookStateManager: **PASS（代替手段あり）**
1.4 AbsorptionResult: **PASS**
1.5 ImbalanceResult: **PASS**

判定: **FAIL有り → Stage 2に進まない**。

## 2. 根拠

### 2.1 CVD

`CvdCalculator.process()`の返り値は`CvdResult`であり、直下の公開fieldは
`accepted`、`update`、`closed_candle`、`rejection`だけである
（`Delta_Engine_Pro4web/src/orderflow/cvd.py:112-124`）。

要求された4属性は、accepted時に`CvdResult.update`として生成される
`CvdUpdate`に存在する（`cvd.py:248-254`、`CvdUpdate`定義は`cvd.py:77-84`）。

従って、指定された配線行の
`producer.observe_cvd(cvd_result)`は不適合であり、
`if cvd_result.update is not None: producer.observe_cvd(cvd_result.update)`
というpipeline内の薄い橋渡しが必要である。rejected resultではupdateがNoneのためomitされ、
既存のfail-closed挙動を維持できる。

### 2.2 FlowResponseSnapshot

`FlowResponseSnapshot`は要求された`event_time`、`symbol`、`window_sec`、`delta`、
`last_price`をすべて公開fieldとして持つ
（`Delta_Engine_Pro4web/src/orderflow/flow_price_response.py:39-60`）。
`FlowPriceResponseDetector.process()`はsnapshot tupleを返す
（`flow_price_response.py:167-206`）。PASS。

### 2.3 OrderBook

`OrderBookStateManager`直下のpublic属性は`symbol`のみで、`bids`／`asks`はprivate stateである
（`Delta_Engine_Pro4web/src/orderflow/orderbook.py:103-115`）。
一方、公開`snapshot()`が`OrderBookSnapshot | None`を返し、そこに`symbol`、`bids`、`asks`がある
（`orderbook.py:144-157`、`OrderBookSnapshot`定義は`orderbook.py:68-75`）。
従ってpipelineでは`book_state.snapshot()`を取得し、Noneでない場合だけ
`producer.observe_book(snapshot, approved_tick_size=...)`を呼ぶ。PASS（代替手段）。

### 2.4 Absorption

`AbsorptionDetector.current()`は`Optional[AbsorptionResult]`を返し
（`Delta_Engine_Pro4web/src/orderflow/absorption.py:142-144`）、
`AbsorptionResult.classification`が公開されている
（`absorption.py:42-58`）。PASS。

### 2.5 Imbalance

`ImbalanceResult`は`symbol`を公開fieldとして持ち
（`Delta_Engine_Pro4web/src/orderflow/imbalance.py:73-79`）、
`ImbalanceDetector.detect()`が当該resultを返す
（`imbalance.py:176-180`）。PASS。

## 3. Stage 2停止理由と最小アダプター案

停止理由はCvdResultとCvdUpdateの型境界が指示書の直接呼出し例と一致しないためである。
SnapshotProducer自体は変更禁止なので、pipeline.py内で次の最小橋渡しを行う案を提示する。

```python
cvd_result = cvd.process(normalized)
if cvd_result.update is not None:
    producer.observe_cvd(cvd_result.update)
```

同様にBookは次の公開snapshot経路を使う。

```python
book_state.apply(update)
book_snapshot = book_state.snapshot()
if book_snapshot is not None:
    producer.observe_book(book_snapshot, approved_tick_size=_BTCUSDT_TICK_SIZE)
```

このアダプター案は`SnapshotProducer`変更なしで実現可能だが、P2 Stage 2の承認が必要である。

## 4. 変更・検証状態

- P2 Stage 2: 未着手。
- `pipeline.py`: 無変更。
- `snapshot_producer.py`: 無変更。
- 検出器、config、正本、runtime、raw data、収録基盤: 無変更。
- commit/push: なし。
- 次の再開位置: CvdResult.update橋渡しとOrderBook snapshot代替を反映したP2 Stage 2再承認後。
