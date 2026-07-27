# 指示書: P2 Pipeline配線 v1

作成日: 2026-07-27
作成者: Claude web
対象ブランチ: ui-refresh-v2
ベースライン: 578 passed, 1 skipped

---

## 0. 本指示書のスコープ

P1で完成した`SnapshotProducer`（`src/strategy_engine/ingestion/snapshot_producer.py`）を、
Live/Replay両パイプライン（`src/pipeline.py`）に配線する。

**やること:**
- pipeline.pyにSnapshotProducerをimport
- Live/Replay両パイプラインでSnapshotProducerをインスタンス化
- 5検出器の公開結果を`observe_*`メソッドで供給
- バー確定時に`build_market_state()`を呼び、結果を`self._last_market_state`に格納
- 配線の回帰テスト追加

**やらないこと:**
- Strategy Engineへの接続（P3以降）
- configへのtick_size追加（P3以降）
- 既存検出器コードの変更
- _evaluate_and_storeのシグネチャ変更
- 正本CSV/ポリシーの変更

---

## 1. Stage 1: Pre-flightインターフェース検証

**Stage 2に進む前に、以下5件の属性突合を実施し結果を報告せよ。**
1件でも不一致があればStage 2に進まず停止・報告。

### 1.1 CvdCalculator.process() の返り値

ファイル: `src/orderflow/cvd.py`

SnapshotProducerの`observe_cvd(update)`は以下の属性をgetattr経由で要求する:

| 属性 | 型 | 用途 |
|---|---|---|
| `symbol` | str | シンボル一致検証 |
| `event_time` | datetime | 時間窓フィルタ |
| `tick_delta` | Decimal互換 | 窓内delta累計 |
| `tick_cvd` | Decimal互換 | CVD slope計算 |

**確認事項:**
- `CvdCalculator.process(normalized)`の返り値（CvdResult等）に上記4属性が存在するか
- 存在しない場合、CvdCalculatorが公開する他のオブジェクト（プロパティ等）で同等の情報を取得可能か
- 取得不可の場合、どの属性が欠落しているかを報告

### 1.2 FlowResponseSnapshot

ファイル: `src/orderflow/flow_price_response.py`

SnapshotProducerの`observe_flow_response(snapshot)`は以下の属性を要求する:

| 属性 | 型 | 用途 |
|---|---|---|
| `symbol` | str | シンボル一致検証 |
| `window_sec` | int | 対応窓の選別 |
| `event_time` | datetime | price_samples生成 |
| `delta` | Decimal互換 | trade_delta_{label}供給 |
| `last_price` | Decimal互換 | price_samples生成 |

**確認事項:** FlowPriceResponseDetector.process()が返すsnapshotリスト内の各要素に上記5属性が存在するか。

### 1.3 OrderBookStateManager

ファイル: `src/orderflow/orderbook.py`

SnapshotProducerの`observe_book(snapshot)`は以下の属性を要求する:

| 属性 | 型 | 用途 |
|---|---|---|
| `symbol` | str | シンボル一致検証 |
| `bids` | dict[price, quantity] | BookLevel変換 |
| `asks` | dict[price, quantity] | BookLevel変換 |

**確認事項:**
- `OrderBookStateManager`自体がこの3属性を公開しているか
- 公開していない場合、スナップショットオブジェクトを返すメソッド（例: `get_snapshot()`）が存在するか
- dict形式はdict[Decimal, Decimal]か、dict[str, str]か、その他か

### 1.4 AbsorptionDetector.current()

ファイル: `src/orderflow/absorption.py`

SnapshotProducerの`observe_absorption(result)`は以下の属性を要求する:

| 属性 | 型 | 用途 |
|---|---|---|
| `classification` | str | "BUY_ABSORPTION" or "SELL_ABSORPTION"判定 |

**確認事項:** `AbsorptionDetector.current()`の返り値に`classification`属性が存在するか。Noneが返る場合も許容済み（snapshot_producer.py:73-74で処理）。

### 1.5 ImbalanceResult

ファイル: `src/orderflow/imbalance.py`

SnapshotProducerの`observe_imbalance(result)`は以下の属性を要求する:

| 属性 | 型 | 用途 |
|---|---|---|
| `symbol` | str | シンボル一致検証 |

**確認事項:** `ImbalanceDetector.detect(fp_bar)`の返り値`ImbalanceResult`に`symbol`属性が存在するか。

### 1.6 報告フォーマット

```
Pre-flight結果:
1.1 CvdResult: [PASS / FAIL(欠落属性: ...)]
1.2 FlowResponseSnapshot: [PASS / FAIL(欠落属性: ...)]
1.3 OrderBookStateManager: [PASS / FAIL(代替手段: ... / なし)]
1.4 AbsorptionResult: [PASS / FAIL(欠落属性: ...)]
1.5 ImbalanceResult: [PASS / FAIL(欠落属性: ...)]
判定: [全PASS → Stage 2に進む / FAIL有り → 停止・詳細報告]
```

**FAILがある場合、アダプター案を添えて報告し停止せよ。Stage 2に進んではならない。**

---

## 2. Stage 2: 実装

Stage 1が全PASSの場合のみ本節を実行する。

### 2.1 import追加

ファイル: `src/pipeline.py`

既存importブロック末尾（現在の最終import行の直後）に追加:

```python
# --- BEFORE ---
from .orderflow.volume_ref import VolumeRefTracker

# --- AFTER ---
from .orderflow.volume_ref import VolumeRefTracker
from .strategy_engine.ingestion.snapshot_producer import SnapshotProducer
```

datetime/timezoneのimportが既存になければ追加（`from datetime import datetime, timezone`）。
pipeline.py先頭の既存importに`datetime`と`timezone`が含まれているか確認し、不足分のみ追加。

### 2.2 ヘルパー関数追加

ファイル: `src/pipeline.py`

`_evaluate_and_store`関数の直前（`class ReplayPipeline`ブロックの外、モジュールレベル）に追加:

```python
# --- BEFORE ---
@dataclass(frozen=True)
class _BarCloseResult:

# --- AFTER ---
def _to_engine_ns(dt: datetime) -> int:
    """Convert a bar-close datetime to engine nanoseconds (UTC epoch).

    Uses only integer arithmetic on timedelta components (no float()).
    """
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    _epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    td = dt - _epoch
    return (td.days * 86400 + td.seconds) * 1_000_000_000 + td.microseconds * 1000


# BTCUSDT tick size; moves to config in P3.
_BTCUSDT_TICK_SIZE = Decimal("0.1")


@dataclass(frozen=True)
class _BarCloseResult:
```

### 2.3 Replay Pipeline配線

ファイル: `src/pipeline.py`, class `ReplayPipeline`, method `run()`

#### 2.3.1 インスタンス化

`storage = StorageWriter(`の直前にSnapshotProducerを生成する。

```python
# --- BEFORE ---
        storage = StorageWriter(
            self.parquet_path,
            self.duckdb_path,
            batch_size=self.batch_size,
            flush_interval_sec=self.flush_interval_sec,
        )

# --- AFTER ---
        producer = SnapshotProducer(self.symbol)
        storage = StorageWriter(
            self.parquet_path,
            self.duckdb_path,
            batch_size=self.batch_size,
            flush_interval_sec=self.flush_interval_sec,
        )
```

#### 2.3.2 handle関数内: CVD観測

`cvd_result = cvd.process(normalized)`の直後に挿入。

```python
# --- BEFORE ---
            cvd_result = cvd.process(normalized)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)

# --- AFTER ---
            cvd_result = cvd.process(normalized)
            producer.observe_cvd(cvd_result)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)
```

**注意:** Stage 1で`CvdResult`にSnapshotProducerの要求属性がないと判明した場合、
この行は別のオブジェクトの供給に変わる。Stage 1結果に従うこと。

#### 2.3.3 handle関数内: FlowResponse観測

`self.flow_response = snapshots`の直後に挿入。

```python
# --- BEFORE ---
                if snapshots:
                    self.flow_response = snapshots
                    events = flow_response_tracker.register(snapshots)

# --- AFTER ---
                if snapshots:
                    self.flow_response = snapshots
                    for _snap in snapshots:
                        producer.observe_flow_response(_snap)
                    events = flow_response_tracker.register(snapshots)
```

#### 2.3.4 メインループ: Book観測

`book_state.apply(update)`の直後に挿入。

```python
# --- BEFORE ---
            if kind == "depth":
                update = normalizer.process_depth(raw)
                if update is not None:
                    book_state.apply(update)
            else:

# --- AFTER ---
            if kind == "depth":
                update = normalizer.process_depth(raw)
                if update is not None:
                    book_state.apply(update)
                    producer.observe_book(book_state)
            else:
```

**注意:** Stage 1で`OrderBookStateManager`が直接`symbol`/`bids`/`asks`を持たない場合、
`book_state`の代わりにスナップショット取得メソッドの返り値を渡す。Stage 1結果に従うこと。

#### 2.3.5 handle関数内: バー確定時の吸収・imbalance観測 + snapshot構築

`_evaluate_and_store`呼び出しとその直後の`analysis_count += 1`を修正。
返り値を捕捉し、absorption/imbalance観測 → build_market_stateを実行する。

```python
# --- BEFORE ---
                else:
                    _evaluate_and_store(
                        cvd_result.closed_candle, fp_closed,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                    )  # return value unused in replay
                    analysis_count += 1

# --- AFTER ---
                else:
                    _bar_result = _evaluate_and_store(
                        cvd_result.closed_candle, fp_closed,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                    )
                    producer.observe_absorption(_bar_result.absorption_result)
                    producer.observe_imbalance(_bar_result.imbalance_result)
                    self._last_market_state = producer.build_market_state(
                        engine_time_ns=_to_engine_ns(cvd_result.closed_candle.bar_time),
                        tick_size=_BTCUSDT_TICK_SIZE,
                    )
                    analysis_count += 1
```

#### 2.3.6 finalize区間: 最終バーの吸収・imbalance観測 + snapshot構築

Replay run()のfinalize区間（`final_candle = cvd.finalize()`以降）にも同様の配線を追加。

```python
# --- BEFORE ---
            else:
                _evaluate_and_store(
                    final_candle, final_fp,
                    imbalance_detector, signal_engine, storage,
                    self.cvd_slope_ref, self.signal_stack_ref,
                    volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                )  # return value unused in replay
                analysis_count += 1
        storage.close()

# --- AFTER ---
            else:
                _bar_result = _evaluate_and_store(
                    final_candle, final_fp,
                    imbalance_detector, signal_engine, storage,
                    self.cvd_slope_ref, self.signal_stack_ref,
                    volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                )
                producer.observe_absorption(_bar_result.absorption_result)
                producer.observe_imbalance(_bar_result.imbalance_result)
                self._last_market_state = producer.build_market_state(
                    engine_time_ns=_to_engine_ns(final_candle.bar_time),
                    tick_size=_BTCUSDT_TICK_SIZE,
                )
                analysis_count += 1
        storage.close()
```

#### 2.3.7 _last_market_state初期化

ReplayPipeline.run()の冒頭（`producer = SnapshotProducer(self.symbol)`の直後）に追加:

```python
        producer = SnapshotProducer(self.symbol)
        self._last_market_state = None
```

### 2.4 Live Pipeline配線

ファイル: `src/pipeline.py`, class `LivePipeline`, method `run_async()`

#### 2.4.1 インスタンス化

`self.flow_response_outcomes = deque(maxlen=5000)`の直後に追加。

```python
# --- BEFORE ---
        self.flow_response = ()
        self.flow_response_events = deque(maxlen=5000)
        self.flow_response_outcomes = deque(maxlen=5000)
        # Per-direction cooldown state for webapp IMBALANCE flow events (Task-A).
        self._imbalance_fire_state: dict = {}

# --- AFTER ---
        self.flow_response = ()
        self.flow_response_events = deque(maxlen=5000)
        self.flow_response_outcomes = deque(maxlen=5000)
        producer = SnapshotProducer(self.symbol)
        self._last_market_state = None
        self._snapshot_producer = producer
        # Per-direction cooldown state for webapp IMBALANCE flow events (Task-A).
        self._imbalance_fire_state: dict = {}
```

`self._snapshot_producer`はwebapp層からのアクセス用に公開する。

#### 2.4.2 handle関数内: CVD観測

Replayと同一パターン。`cvd_result = cvd.process(normalized)`の直後。

```python
# --- BEFORE ---
            cvd_result = cvd.process(normalized)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)

# --- AFTER ---
            cvd_result = cvd.process(normalized)
            producer.observe_cvd(cvd_result)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)
```

#### 2.4.3 handle関数内: FlowResponse観測

```python
# --- BEFORE ---
                if snapshots:
                    self.flow_response = snapshots
                    events = flow_response_tracker.register(snapshots)

# --- AFTER ---
                if snapshots:
                    self.flow_response = snapshots
                    for _snap in snapshots:
                        producer.observe_flow_response(_snap)
                    events = flow_response_tracker.register(snapshots)
```

#### 2.4.4 メインループ: Book観測

メインループ内のdepthハンドリング。

```python
# --- BEFORE ---
                elif kind == "depth":
                    update = normalizer.process_depth(raw)
                    if update is not None:
                        book_state.apply(update)
                else:

# --- AFTER ---
                elif kind == "depth":
                    update = normalizer.process_depth(raw)
                    if update is not None:
                        book_state.apply(update)
                        producer.observe_book(book_state)
                else:
```

#### 2.4.5 ドレインパス: Book観測

finally block内のドレインパス（`while not norm_q.empty():`ループ内のdepth処理）にも同様に追加。

```python
# --- BEFORE ---
                elif kind == "depth":
                    update = normalizer.process_depth(pending)
                    if update is not None:
                        book_state.apply(update)
                else:

# --- AFTER ---
                elif kind == "depth":
                    update = normalizer.process_depth(pending)
                    if update is not None:
                        book_state.apply(update)
                        producer.observe_book(book_state)
                else:
```

#### 2.4.6 handle関数内: バー確定時の吸収・imbalance観測 + snapshot構築

`bar_close = _evaluate_and_store(...)`と`self._last_bar_close = bar_close`の間に追加。

```python
# --- BEFORE ---
                    bar_close = _evaluate_and_store(
                        cvd_result.closed_candle, fp_closed,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                        flow_events=list(flow_event_buffer),
                        on_webapp_flow_event=self.on_webapp_flow_event,
                        imbalance_fire_state=self._imbalance_fire_state,
                    )
                    self._last_bar_close = bar_close
                    self._last_fp_bar = fp_closed

# --- AFTER ---
                    bar_close = _evaluate_and_store(
                        cvd_result.closed_candle, fp_closed,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                        flow_events=list(flow_event_buffer),
                        on_webapp_flow_event=self.on_webapp_flow_event,
                        imbalance_fire_state=self._imbalance_fire_state,
                    )
                    producer.observe_absorption(bar_close.absorption_result)
                    producer.observe_imbalance(bar_close.imbalance_result)
                    self._last_market_state = producer.build_market_state(
                        engine_time_ns=_to_engine_ns(cvd_result.closed_candle.bar_time),
                        tick_size=_BTCUSDT_TICK_SIZE,
                    )
                    self._last_bar_close = bar_close
                    self._last_fp_bar = fp_closed
```

#### 2.4.7 finalize区間: 最終バーの吸収・imbalance観測 + snapshot構築

finally block内のfinalize（`bar_close = _evaluate_and_store(final_candle, final_fp, ...)`の直後）。

```python
# --- BEFORE ---
                    bar_close = _evaluate_and_store(
                        final_candle, final_fp,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                        flow_events=list(flow_event_buffer),
                        on_webapp_flow_event=self.on_webapp_flow_event,
                        imbalance_fire_state=self._imbalance_fire_state,
                    )
                    if mt5_server is not None and bar_close.analysis_result is not None:

# --- AFTER ---
                    bar_close = _evaluate_and_store(
                        final_candle, final_fp,
                        imbalance_detector, signal_engine, storage,
                        self.cvd_slope_ref, self.signal_stack_ref,
                        volume_ref, absorption, analysis_engine, trend_state=self.trend_state,
                        flow_events=list(flow_event_buffer),
                        on_webapp_flow_event=self.on_webapp_flow_event,
                        imbalance_fire_state=self._imbalance_fire_state,
                    )
                    producer.observe_absorption(bar_close.absorption_result)
                    producer.observe_imbalance(bar_close.imbalance_result)
                    self._last_market_state = producer.build_market_state(
                        engine_time_ns=_to_engine_ns(final_candle.bar_time),
                        tick_size=_BTCUSDT_TICK_SIZE,
                    )
                    if mt5_server is not None and bar_close.analysis_result is not None:
```

### 2.5 テスト

ファイル: `tests/test_pipeline_snapshot_wiring.py`（新規作成）

以下の観点をカバーするテストを追加する。テスト数・構成はCodexの判断に任せるが、
少なくとも以下2点を網羅すること:

1. **Replay配線テスト:** 最小のリプレイデータ（trade数本 + depth 1件以上、バー確定が1回以上発生するデータ量）でReplayPipelineを実行し、実行後に`pipeline._last_market_state`がNoneでないことを検証する。MarketStateSnapshotの型チェックも含める。

2. **Live配線テスト:** 既存のLivePipelineテストパターン（injected source + `fetch_snapshot=None`）で同様に`pipeline._last_market_state`がNoneでないことを検証する。LivePipelineに`self._snapshot_producer`が公開されていることも検証する。

**テスト作成時の制約:**
- 既存テストファイルを変更しない
- 既存のテストヘルパー・フィクスチャを活用すること（新規フィクスチャは最小限）
- テストデータは既存のテスト用データを流用するか、最小限の手作りデータで構成

---

## 3. 完了基準

- [ ] Stage 1 Pre-flight全5件PASS
- [ ] pipeline.pyへのSnapshotProducer import追加
- [ ] `_to_engine_ns`ヘルパーと`_BTCUSDT_TICK_SIZE`定数の追加
- [ ] Replay Pipeline: 5種observe + build_market_state配線（handle内 + finalize）
- [ ] Live Pipeline: 5種observe + build_market_state配線（handle内 + ドレインパス + finalize）
- [ ] `self._last_market_state`がLive/Replay両方で公開
- [ ] Liveで`self._snapshot_producer`が公開
- [ ] 新規テスト全件pass
- [ ] 全回帰: 578 + 新規テスト数 passed, 1 skipped
- [ ] 既存ファイルの変更はpipeline.pyのみ（検出器コード・config・正本は不変）
- [ ] commit/pushなし

---

## 4. 禁止事項

- 既存検出器（cvd.py, absorption.py, imbalance.py, orderbook.py, flow_price_response.py）の変更
- _evaluate_and_storeのシグネチャ変更
- configファイルへのtick_size追加
- float()の使用（Decimal→str変換のみ）
- SnapshotProducer自体の変更（snapshot_producer.pyは不変）
- runtime有効化・発注権限の変更
- Strategy Engineへの接続（P3以降）
- 収録基盤・raw dataの変更

---

## 5. Stage 1 FAILの場合のエスカレーション

いずれかのインターフェースが不一致の場合、以下を報告して停止:

1. 不一致の検出器名・ファイル・行番号
2. SnapshotProducerの期待属性 vs 実際のオブジェクト構造
3. 最小侵襲のアダプター案（pipeline.py内に薄いdataclass/namedtupleを追加して属性を橋渡しする方式を推奨）
4. アダプター案がSnapshotProducerの変更なしで実現可能かの判定

アダプター案の採否はお館様が決定する。Codex判断で実装に進んではならない。
