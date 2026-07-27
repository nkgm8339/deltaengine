# 指示書: P2 Pipeline配線 v1.1

作成日: 2026-07-27
作成者: Claude web
改訂: v1.1 = Pre-flight結果(P2_PIPELINE_WIRING_PREFLIGHT_20260727.md)反映版。Stage 1は完了済みのため削除し、Stage 2のみ実行する。
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

## 1. Pre-flight結果（完了済み・参照用）

Stage 1はCodexにより実施済み。結果は
`ArchitectureRepository/00_Master/トリガー作成指示書群/P2_PIPELINE_WIRING_PREFLIGHT_20260727.md`。

| 検証項目 | 結果 | 配線方式（本指示書で採用） |
|---|---|---|
| 1.1 CvdResult | FAIL → 解決 | CvdResult直下に要求属性なし。`cvd_result.update`（CvdUpdate）に実データが存在。`cvd_result.update is not None`の場合のみ`observe_cvd(cvd_result.update)`を呼ぶ |
| 1.2 FlowResponseSnapshot | PASS | snapshotをそのまま`observe_flow_response`へ |
| 1.3 OrderBook | PASS | `book_state.snapshot()`の返り値を`observe_book`へ |
| 1.4 AbsorptionResult | PASS | `_BarCloseResult.absorption_result`をそのまま`observe_absorption`へ |
| 1.5 ImbalanceResult | PASS | `_BarCloseResult.imbalance_result`をそのまま`observe_imbalance`へ |

CVDの解決方式はsnapshot_producer.pyの元設計と一致する（`observe_cvd`のdocstringは「Observe a public ``CvdUpdate``」であり、CvdUpdateが本来の想定型）。アダプター追加は不要。

---

## 2. 実装

Pre-flightは完了済み。本節を直ちに実行する。

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
            if cvd_result.update is not None:
                producer.observe_cvd(cvd_result.update)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)
```

Pre-flight 1.1に従い、CvdResult本体ではなく`cvd_result.update`（CvdUpdate）を供給する。

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
                    producer.observe_book(book_state.snapshot())
            else:
```

Pre-flight 1.3に従い、`book_state.snapshot()`の返り値を供給する。

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
            if cvd_result.update is not None:
                producer.observe_cvd(cvd_result.update)
            if cvd_result.accepted:
                closed_higher = higher_timeframes.process(normalized)
```

Pre-flight 1.1に従い、CvdResult本体ではなく`cvd_result.update`（CvdUpdate）を供給する。

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
                        producer.observe_book(book_state.snapshot())
                else:
```

Pre-flight 1.3に従い、`book_state.snapshot()`の返り値を供給する。

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
                        producer.observe_book(book_state.snapshot())
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

## 5. 実装中の齟齬時のエスカレーション

本指示書のアンカーが実物と一致しない場合、または`book_state.snapshot()`/`cvd_result.update`の
実際の構造がPre-flight報告と異なる場合は、実装せず以下を報告して停止:

1. 齟齬のファイル・行番号・実際のコード
2. 本指示書のどの節が影響を受けるか

fail-closed原則に従い、Codex判断での回避実装は禁止。
