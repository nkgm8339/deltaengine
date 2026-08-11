# 指示書: Phase 2-3 Stage 2 Task 1 frame_source 実装
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3 Stage 2
前提: HEAD bf95126。設計確定済み(build_book_projection依存・SYNCED条件・payload型を検証済み)。保護ファイル非接触の新規追加。
統括の設計: recording(DepthHistoryReader/sample_states)のOrderBookSnapshotを、SnapshotBookStateAdapterで包み、既存build_book_projectionでBookProjection列に変換する。payload化(stream_id/sequence)はTask 2でbroker.on_book_updateが担う。ADR「Replay/Live同一applyコア共有」準拠。

---

## 1. 絶対規律
- 新規2ファイルのみを追加。既存ファイルを一切変更しない(保護ファイル含む)。
- float()禁止(例外transform.pyのみ、本タスクは対象外)。時刻・数量はdatetime/Decimalで扱う。
- 配置はwebapp配下(依存方向を webapp→src.heatmap+webapp.book_projection の正方向に保つため)。src/heatmapには置かない。

## 2. 新規ファイル

### 2A. webapp/heatmap_frame_source.py(新規)

要件(この仕様を満たす実装をせよ。関数・クラス名は下記に固定):

import(必要なもの):
- `from __future__ import annotations`
- `from collections.abc import Iterator`
- `from datetime import datetime, timezone`
- `from pathlib import Path`
- `from src.heatmap.reconstruct import DepthHistoryReader, DepthReconstructor`
- `from src.orderflow.orderbook import OrderBookSnapshot`
- `from webapp.book_projection import BookProjection, build_book_projection`

#### クラス `SnapshotBookStateAdapter`
録画で再構築したOrderBookSnapshotを、build_book_projectionが読む read-only book_state として提供する。録画sampleは同期済み・新鮮な状態として扱う。
- `__init__(self, snapshot: OrderBookSnapshot) -> None`: snapshotを保持。`self.gaps_detected: int = 0` を属性として持つ。
- `is_synchronized` (property) -> bool: 常に `True`。
- `last_event_time` (property) -> `datetime | None`: 保持snapshotの `event_time` をそのまま返す。
- `age_ms(self, now_monotonic: float | None = None) -> int`: 常に `0`(録画sampleは新鮮扱い、stale_after_ms以下を保証)。
- `snapshot(self) -> OrderBookSnapshot`: 保持snapshotを返す。

#### ヘルパ `_epoch_ms_to_utc(event_time_ms: int) -> datetime`
epoch millisecondをtz-aware UTC datetimeへ変換する。`datetime.fromtimestamp(event_time_ms / 1000, tz=timezone.utc)` は割り算がfloatになるため使用禁止。`divmod(event_time_ms, 1000)` で秒・ミリ秒に分け、`datetime.fromtimestamp(seconds, tz=timezone.utc)` + `timedelta(milliseconds=millis)` で構成せよ(reconstruct.py:489-497の既存パターンに倣う)。floatを介さないこと。

#### 関数 `iter_book_projections`
```
def iter_book_projections(
    recording_dir: Path,
    *,
    interval_ms: int,
    depth_levels: int = 50,
    symbol: str = "BTCUSDT",
) -> Iterator[BookProjection]:
```
フロー:
1. `recording_dir` がdirでなければ `FileNotFoundError`。
2. `reader = DepthHistoryReader(recording_dir)`。
3. `reconstructor = DepthReconstructor(symbol=symbol, max_attempts=1)`。
4. `for event_time_ms, snapshot in reconstructor.sample_states(reader.iter_records(), interval_ms=interval_ms):`
   - `adapter = SnapshotBookStateAdapter(snapshot)`
   - `projection_time = _epoch_ms_to_utc(event_time_ms)`
   - `yield build_book_projection(adapter, depth_levels=depth_levels, projection_time=projection_time)`

注: stream_id/sequenceの付与、WebSocket送信、gate有効化は本タスクの範囲外(Task 2)。本タスクはBookProjection列の生成までとする。

### 2B. tests/heatmap/test_frame_source.py(新規)
注: テストは src.heatmap には依存を足さず、webapp.heatmap_frame_source を対象とする。配置は tests/webapp/ が依存的に自然(webapp対象のため)。**tests/webapp/test_heatmap_frame_source.py として作成せよ。**

テストケース(SnapshotBookStateAdapter + build_book_projection の組合せを、実OrderBookSnapshotを組んで検証):
- T1: healthy snapshot(bids/asks各複数level、best_bid<best_ask、event_time tz-aware)→ sync_state==SYNCED、bids降順・asks昇順、best_bid/best_ask/spread正しい、depth_levelsで切られる。
- T2: crossed snapshot(best_bid>best_ask)→ sync_state==CROSSED、bids/asks空。
- T3: locked snapshot(best_bid==best_ask)→ LOCKED。
- T4: 片側空(asks空)→ EMPTY。
- T5: event_time=None のsnapshot → INVALID。
- T6: adapter単体: is_synchronized is True、age_ms(None)==0、snapshot()が同一オブジェクト、last_event_timeがsnapshot.event_time。
- T7: iter_book_projections: 小さなrecording fixture または sample_statesをmonkeypatchして、BookProjection列がyieldされ、各projection_timeがtz-aware UTCであること。fixtureが用意困難なら、iter_book_projectionsの内部(adapter生成→build_book_projection)を、sample_statesをstub化して検証してよい。
- 全テストでfloat()を使わない(Decimal/datetimeで組む)。

## 3. 手順
1. 2A, 2B を作成(既存ファイル不変更)。
2. float走査: `grep -n "float(" webapp/heatmap_frame_source.py tests/webapp/test_heatmap_frame_source.py` → 0件。
3. 新規テスト単体実行: `python -m pytest -q tests/webapp/test_heatmap_frame_source.py`。
4. 全pytest: `python -m pytest -q -p no:cacheprovider` → 既知failure以外の新規failなし、passed数が773+新規テスト数。
5. git add はまだしない(統括検証後に別途コミット指示)。

## 4. 提出物
- webapp/heatmap_frame_source.py と tests/webapp/test_heatmap_frame_source.py の全文
- 両ファイルのSHA-256・byte・LF・CR
- float走査結果(0件)
- 新規テスト単体実行結果、全pytestサマリ・FAILED行
- `git status --porcelain -- Delta_Engine_Pro4web/`(新規2ファイルが??で出る、既存coreにM追加なし)
- `git rev-parse HEAD`(bf95126)

## 5. 禁止事項
- 既存ファイルの変更(保護ファイル含む)。
- src/heatmapへの配置(逆依存回避)。
- float()の使用。
- git add / commit(検証後に別指示)。

以上。提出後、統括が実物2ファイルを独立検証(SHA・float・テスト・内容)し、合格なら第六コミット(frame_source)指示書を発行、続いてTask 2(供給経路+gate有効化、保護接触)の調査へ進む。
