この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_B_OrderBook基盤_M9Absorption_統合実装_v1

**対象**: Order Flow Analysis Platform — Order Book 正規化基盤 + M9 Absorption 実装 + pipeline 配線(統合)
**参照正本**:
- ArchitectureRepository/40_Reference/MarketDataSchema_v3.2.md (指示書 A で追加)
- ArchitectureRepository/40_Reference/JSONSchema_v3.2.md §7 (指示書 A で追加)
- ArchitectureRepository/40_Reference/YAMLReference_v3.2.md §4.1 (指示書 A で追加)
- ArchitectureRepository/30_Modules/Absorption_v3.1.md
- ArchitectureRepository/30_Modules/SignalEngine_v3.1.md
- ArchitectureRepository/30_Modules/DataNormalizer_v3.2.md
- ArchitectureRepository/50_Test/TestSpecification_v3.2.md §4.4 (TV-ABS-01〜05)
- ArchitectureRepository/40_Reference/ErrorCodes_v3.1.md

---

## 0. スコープ

M9 Absorption を閉じるまでを **1 本の指示書で完結** させる。以下を全て含む。

1. Order Book 正規化基盤(profile 拡張、DataNormalizer 拡張、acquisition filter 拡張)
2. `src/orderflow/orderbook.py`(Order Book Update 型 + State Manager)
3. `src/orderflow/absorption.py` stub を実体実装で置換(TV-ABS-01〜05)
4. `volume_ref` 共有機構(Imbalance / Absorption 双方が参照)
5. `pipeline.py` への depth 経路 + Absorption 配線(SignalEngine の `absorption_result=None` を実接続に置換)
6. 上記全てのユニットテスト + pipeline 統合テスト 1 本

**スコープ外**(将来の別課題)
- REST snapshot 取得(初期化用) — fixture 駆動でテスト完結、ライブ検証は別課題
- depth の永続化 — 容量問題、Signal のみ永続化する M11 方針を継続
- ライブ Binance depth 検証

**docs は無変更**。指示書 A で必要な正本追加は完了済み。

**既存パス無変更**: CVD / Footprint / Imbalance / SignalEngine のロジックは無変更。ただし `volume_ref` 共有機構の導入に伴い、Imbalance の `min_volume` に共有機構の参照ができるよう **後方互換オプション** を追加する(既存テストは無影響、下記 §5)。

---

## 1. 成果物

**新規**
- `src/orderflow/orderbook.py`
- `src/orderflow/absorption.py` (現行 stub を上書き置換、`AbsorptionResult` 型シグネチャは維持)
- `src/orderflow/volume_ref.py` (共有機構)
- `tests/orderflow/test_orderbook.py`
- `tests/orderflow/test_absorption.py`
- `tests/orderflow/test_volume_ref.py`
- `tests/normalization/test_normalizer_depth.py`
- `tests/test_pipeline_absorption.py` (統合テスト)

**編集**
- `config/profiles/binance.yaml` — `order_book_mapping` ブロック追加
- `src/normalization/normalizer.py` — depth 正規化パス追加(既存 trade パスは 1 行も変更しない)
- `src/acquisition/binance_ws.py` — `is_agg_trade_or_depth` 追加(既存 `is_agg_trade` は残置)
- `src/orderflow/imbalance.py` — `volume_ref` 参照オプション追加(既存挙動は default で無変更)
- `src/pipeline.py` — depth 経路と Absorption を配線
- `tests/acquisition/test_binance_ws.py` — 新 predicate のテスト追加

**編集不要**
- `src/orderflow/cvd.py` / `footprint.py` / `signal.py` — 触らない
- `src/database/schema.py` / `storage.py` — 触らない
- `ArchitectureRepository/` 配下 — 触らない

---

## 2. `config/profiles/binance.yaml` の編集

現行の trade マッピングは無変更、末尾にブロック追加。

```yaml
order_book_mapping:
  event_type_field: e
  event_type_snapshot: depthSnapshot
  event_type_diff: depthUpdate
  symbol_field: s
  event_time_field: E
  first_update_id_field: U
  final_update_id_field: u
  bids_field: b
  asks_field: a
  level_price_index: 0
  level_quantity_index: 1
```

コメント: Binance Futures @depth は `e = "depthUpdate"` を送出、`depthSnapshot` は REST 経由の初期化で acquisition 層が付与する想定(本指示書スコープ外)。

---

## 3. `src/orderflow/orderbook.py` 新規

Decimal オンリー、float 禁止。CVD スタイル。

### 3.1 型

```python
@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    quantity: Decimal

@dataclass(frozen=True)
class OrderBookUpdate:
    """MarketDataSchema_v3.2 Order Book Update Record."""
    event_time: datetime
    symbol: str
    update_type: str          # "SNAPSHOT" | "DIFF"
    first_update_id: int | None
    final_update_id: int
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    last_update_id: int
    bids: dict[Decimal, Decimal]  # price → quantity, quantity > 0 のみ
    asks: dict[Decimal, Decimal]
    def bid_quantity_at(self, price: Decimal) -> Decimal: ...
    def ask_quantity_at(self, price: Decimal) -> Decimal: ...

@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    reinitialized: bool
    gap_detected: bool
```

`__post_init__` で必要な Decimal 化(CVD の `_to_decimal` パターンを再利用)。

### 3.2 State Manager

```python
class OrderBookStateManager:
    def __init__(self, symbol: str) -> None: ...
    def apply(self, update: OrderBookUpdate) -> ApplyResult: ...
    def snapshot(self) -> OrderBookSnapshot | None
    def bid_quantity_at(self, price: Decimal) -> Decimal
    def ask_quantity_at(self, price: Decimal) -> Decimal
    # カウンタ(no silent loss)
    snapshots_applied: int
    diffs_applied: int
    diffs_rejected_before_snapshot: int
    diffs_stale: int
    gaps_detected: int
```

**適用ルール**(MarketDataSchema_v3.2 §Order Book Update Record 逐語準拠)

| 入力 | 現在状態 | 挙動 |
|---|---|---|
| SNAPSHOT | 任意 | bids/asks を全消去して update の levels を設定、`last_update_id` 更新、`applied=True, reinitialized=(既存があれば True)` |
| DIFF | 未初期化(SNAPSHOT 未受領 or ギャップ直後) | 棄却、`diffs_rejected_before_snapshot++`、E3004 ログ、`applied=False` |
| DIFF | 初期化済、`final_update_id ≤ last_update_id` | 重複/古い、棄却、`diffs_stale++`、`applied=False` |
| DIFF | 初期化済、`first_update_id == last_update_id + 1` | 各 level を「quantity=0 なら削除、そうでなければ set-to-value」で適用、`last_update_id = final_update_id`、`applied=True` |
| DIFF | 初期化済、`first_update_id != last_update_id + 1` | ギャップ、bids/asks クリア、`last_update_id` を None にリセット、`gaps_detected++`、`applied=False, gap_detected=True`、次の SNAPSHOT を待つ |

`update.symbol != self.symbol` → `ValueError`。

---

## 4. `src/normalization/normalizer.py` 編集

### 4.1 `ExchangeProfile`

`order_book_mapping: dict[str, Any] | None = None` を追加。`from_dict` は `order_book_mapping` を optional 受け入れ。存在時は以下の 11 キー全てを検証(欠けたら `ProfileError` E1002):

```
event_type_field, event_type_snapshot, event_type_diff,
symbol_field, event_time_field,
first_update_id_field, final_update_id_field,
bids_field, asks_field,
level_price_index, level_quantity_index
```

`level_price_index` と `level_quantity_index` は int 型検証。

### 4.2 追加関数

```python
def normalize_raw_depth(raw: dict, profile: ExchangeProfile) -> OrderBookUpdate:
    """Map one raw depth event to canonical Order Book Update.
    Raises NormalizationError on unmappable input."""
```

処理: `event_type_field` の値で SNAPSHOT/DIFF 判別、`symbol` / `event_time`(profile の `timestamp_format` で変換) / `final_update_id` 抽出、DIFF は `first_update_id` 必須、bids/asks 配列の各要素から `level_price_index`/`level_quantity_index` で `BookLevel(Decimal, Decimal)` を組み、入力順で `tuple` 化。

### 4.3 `DataNormalizer` への追加(既存メソッドは 1 行も変更しない)

```python
class DataNormalizer:
    # 追加カウンタ
    depth_processed: int = 0
    depth_rejected: int = 0
    depth_filtered: int = 0  # order_book_mapping なしで素通り

    def process_depth(self, raw: dict) -> OrderBookUpdate | None:
        if self.profile.order_book_mapping is None:
            self.depth_filtered += 1
            return None
        try:
            update = normalize_raw_depth(raw, self.profile)
        except NormalizationError as exc:
            self.depth_rejected += 1
            logger.warning("%s depth normalization rejected: %s", exc.code, exc.reason)
            return None
        self.depth_processed += 1
        return update

    def classify_raw(self, raw: dict) -> str:
        """Return 'trade' | 'depth'."""
        ob = self.profile.order_book_mapping
        if ob is not None and raw.get(ob["event_type_field"]) in (
            ob["event_type_snapshot"], ob["event_type_diff"]
        ):
            return "depth"
        return "trade"
```

---

## 5. `src/orderflow/volume_ref.py` 新規

Absorption_v3.1 §6 の「`volume_ref` is the moving average of per-level volume over the most recent `volume_ref_bars` bars, shared with the Imbalance module」を実装。

### 5.1 型と API

```python
class VolumeRefTracker:
    def __init__(self, bars: int) -> None:
        """bars >= 1. Moving average window in confirmed bars."""
    def observe_bar(self, per_level_volumes: Iterable[Decimal]) -> None:
        """バー確定時に per-level volume を投入。
        per_level_volumes は当該バーの全 price level の (buy+sell) volume 群。"""
    def current(self) -> Decimal | None:
        """直近 `bars` バーの per-level volume 移動平均。
        バーが 1 本も観測されていなければ None。"""
    bars: int
    observations: int  # これまでに投入されたバー数
```

内部実装: 直近 `bars` 本の per-level volume 群を deque で保持し、`current()` で平均を返す。deque の各要素は Decimal のリスト(そのバーの全レベル)。平均は Σ(全レベルの全 volume) / Σ(全レベルの数)で計算する。バーごとに level 数が異なるため単純平均ではなくレベル重み平均。全 Decimal 演算。

### 5.2 Imbalance 側の後方互換オプション

`src/orderflow/imbalance.py` の `ImbalanceDetector.__init__` に `volume_ref: VolumeRefTracker | None = None` を追加。既存 `min_volume` パラメータは default 挙動を維持しつつ、`volume_ref` が渡された場合は `min_volume` の代わりに `volume_ref.current()` を評価時に参照する(current が None のバーでは既存の `min_volume` にフォールバック)。

**既存テストへの影響**: `volume_ref` を渡さない既存呼び出しは完全に元の挙動。既存 tests/orderflow/test_imbalance.py は無変更で green。

---

## 6. `src/orderflow/absorption.py` 実装(stub 置換)

現行 stub は `AbsorptionResult` 型のみを定義。この型は **シグネチャを保つ**(SignalEngine が既に参照している)。実装本体を追加する。

### 6.1 型(既存 + 追加)

```python
@dataclass(frozen=True)
class AbsorptionResult:
    """既存維持。classification: 'BUY_ABSORPTION'|'SELL_ABSORPTION', strength: Decimal (0..1)"""
    classification: str
    strength: Decimal
```

### 6.2 検出器

```python
class AbsorptionDetector:
    def __init__(
        self,
        *,
        window_sec: int = 10,
        price_stall_ticks: int = 1,
        volume_multiplier: Decimal = Decimal("2.0"),
        volume_ref: VolumeRefTracker,
        book_state: OrderBookStateManager,
    ) -> None: ...

    def observe_trade(self, trade: FootprintTrade) -> None:
        """約定を投入。sliding window で状態更新。"""

    def current(self) -> AbsorptionResult | None:
        """直近 window 内で検出中の Absorption を返す。無ければ None。"""

    # カウンタ
    events_detected: int
    aggression_condition_fails: int
    stall_condition_fails: int
    replenish_condition_fails: int
```

### 6.3 検出ロジック(Absorption_v3.1 §5.2 逐語)

sliding window `window_sec` 秒。BUY 側 aggression と SELL 側 aggression を並行評価。各 tick 到着時に:

**Step 1. Window 内 trade を整理**
- 現 tick の `event_time` から `window_sec` 秒より古い trade を削除
- 現 window の window_start_time が変わったタイミング(古い trade が削除されて新しい先頭が確定した瞬間)で、**window_start_book_snapshot** を `book_state.snapshot()` で捕捉して保持
- book_state が未初期化なら Absorption 評価不可、`current()` は None

**Step 2. Directional aggression volume を集計**
- window 内の BUY side aggression volume 合計 = `agg_buy`
- window 内の SELL side aggression volume 合計 = `agg_sell`

**Step 3. Price range を評価(stall condition)**
- window 内の全 trade の price から min/max を取得
- distinct price count を計算
- **設計判断**(下記 §7 決定 1): 「price range ≤ price_stall_ticks」は「distinct executed price の数 ≤ price_stall_ticks」と解釈
- distinct count > `price_stall_ticks` → stall fail、両方向 no event、`stall_condition_fails++`

**Step 4. Aggression condition**
- `threshold = volume_ref.current() × volume_multiplier`。`volume_ref.current()` が None なら threshold 未確定 → no event(カウンタは増やさない)
- SELL 側評価: `agg_sell >= threshold` → Buy Absorption の候補
- BUY 側評価: `agg_buy >= threshold` → Sell Absorption の候補
- 両方向とも threshold 未満 → `aggression_condition_fails++`、no event

**Step 5. Replenish condition(§5.2 条件 3)**
- 対象価格レベル群 = window 内で発生した distinct price のセット
- 現在 book の bid/ask liquidity を `book_state.snapshot()` で取得
- **Buy Absorption 候補**(SELL aggression が吸収された場合): 対象価格レベル群の各 price に対し、現在の bid_quantity ≥ window_start_book_snapshot の bid_quantity。全ての対象レベルで満たされること
- **Sell Absorption 候補**(BUY aggression): 対象価格レベル群の各 price で、現在の ask_quantity ≥ window_start_book_snapshot の ask_quantity
- 満たさない → `replenish_condition_fails++`、no event

**Step 6. 判定と strength**
- 全 3 条件通過 → AbsorptionResult 生成、`events_detected++`
- `strength = min(aggressive_volume / (volume_ref × volume_multiplier), Decimal("1.0"))`(Absorption_v3.1 §5.4 逐語)
- classification: SELL aggression 吸収 → `"BUY_ABSORPTION"`、BUY aggression 吸収 → `"SELL_ABSORPTION"`(Absorption_v3.1 §5.3 逐語)
- 両方向同時発火は想定外だが、発生時は先に条件を満たした側を採用(BUY absorption 優先など任意)し、`double_direction_events` カウンタを増やす

### 6.4 `current()` の意味論

Absorption event が検出された tick から `window_sec` 秒間、`current()` は同じ AbsorptionResult を返し続ける。window から外れたら None に戻る。SignalEngine は bar 確定時に `current()` を問い合わせる。

---

## 7. 設計判断

### 決定 1: `price_stall_ticks` の解釈(tick_size 不在への対処)

正本に tick_size 定義が無い。M8 (Imbalance) では「隣接=配列インデックス隣接」で対処した先例あり。ここでも同じ思想で:

**`absorption.price_stall_ticks` = 「window 内の distinct executed price の許容数」** と解釈する。value=1 なら「全 trade が 1 つの価格レベルに張り付いていること」の意味。

TV-ABS-01(price range=1 tick)→ 全 trade が price=100 で発生 → distinct count = 1 ≤ 1 → OK。TV-ABS-03(price range=2 ticks)→ 2 つの価格で発生 → distinct count = 2 > 1 → fail。ベクタと整合する。

### 決定 2: ギャップ検知エラーコード

Order Book State Manager のギャップ棄却と DIFF-before-snapshot 棄却は E3004(Out-of-order event rejected)を流用。新規 error code を発番しない。

### 決定 3: depth の重複・順序

- 重複: `final_update_id ≤ last_update_id` で棄却(state manager 側、`diffs_stale`)
- 順序: 同一 WebSocket ストリーム内で depth の順序は exchange 保証を前提。trade 側の `reorder_tolerance` は depth に適用しない

### 決定 4: 決定的リプレイ

- trade は既存 JSONL 記録で継続
- depth は JSONL に記録しない(容量問題)。fixture 駆動で TV-ABS-01〜05 と統合テストを全て担保
- ライブから depth 完全再現の需要は別課題

### 決定 5: `order_book_mapping` 未定義プロファイル

`ExchangeProfile.order_book_mapping = None` を許容。`process_depth` は即座に None 返却、`depth_filtered++`。既存トレード専用の後方互換性維持。

### 決定 6: `volume_ref` 未較正時の動作

`VolumeRefTracker.current()` が None(バー観測 0 or `bars` 未達も含めない、初回 observe から利用可能)を返す間:
- Absorption: threshold 未確定 → no event(sink 状態)
- Imbalance: 既存の `min_volume` パラメータにフォールバック
- pipeline はエラーなく動作継続(M11 の "cvd_slope_ref 未較正でもエラーなく動作" の思想と同じ)

### 決定 7: window_start_book_snapshot の捕捉タイミング

sliding window の左端が動いた瞬間(古い trade が window から抜けた瞬間)に、その時点の book snapshot を保存し、以後 replenish 評価の基準とする。window が空の状態から最初の trade が入った時は、その trade 到着時点の book snapshot を window_start とする。

### 決定 8: Absorption 検出は tick 駆動、SignalEngine 問い合わせは bar 駆動

Absorption は sliding window で常時評価、内部状態を更新。SignalEngine は bar 確定時に `AbsorptionDetector.current()` を呼び、その時点の最新 result(または None)を veto 評価に使う。M10 の TV-SIG-04 と整合。

---

## 8. `src/acquisition/binance_ws.py` 編集

`is_agg_trade` 残置、`is_agg_trade_or_depth` を追加。

```python
def is_agg_trade_or_depth(message: Any) -> bool:
    if not isinstance(message, dict):
        return False
    return message.get("e") in ("aggTrade", "depthUpdate")
```

---

## 9. `src/pipeline.py` 配線

### 9.1 変更点

Replay / Live 両パイプラインで以下を実施:

1. `DataReceiver` の `validate` 引数を `is_agg_trade` から `is_agg_trade_or_depth` に差し替え
2. Normalizer 出力後に `normalizer.classify_raw(raw)` で trade / depth 分岐(pipeline 側で `classify_raw` を使うため、raw を normalizer に渡す前に判別する形にする。実装上は、raw を受けたら pipeline が `classify_raw` を呼び、`"trade"` なら既存の `normalizer.process()` 経路、`"depth"` なら `normalizer.process_depth()` → `book_state.apply()` に振り分ける)
3. コンストラクタで以下を生成:
   - `book_state = OrderBookStateManager(symbol=config.market.symbol)`
   - `volume_ref = VolumeRefTracker(bars=config.absorption.volume_ref_bars)`
   - `absorption = AbsorptionDetector(window_sec=..., price_stall_ticks=..., volume_multiplier=..., volume_ref=volume_ref, book_state=book_state)`
   - `imbalance = ImbalanceDetector(..., volume_ref=volume_ref)` (追加引数)
4. tick 到着時に `absorption.observe_trade(trade)` を呼ぶ(既存 CVD/Footprint に並列)
5. バー確定時に `volume_ref.observe_bar([...])` を呼ぶ。投入する per-level volume は当該バーの Footprint から取得(`FootprintBar.levels` の各 `PriceLevel` の `buy_volume + sell_volume`)
6. SignalEngine 評価時に `absorption_result=absorption.current()` を渡す(現行の `None` 固定を置換)

### 9.2 触らないこと

- CVD / Footprint / SignalEngine の入出力型
- Storage 経路(depth と Absorption result は永続化しない、Signal のみ既存通り)
- `pipeline.py` の関数分割構造(既存の Replay / Live wrapper 構造は維持)

---

## 10. テスト

### 10.1 `tests/orderflow/test_orderbook.py`(必須 11 本)

| 名前 | 内容 |
|---|---|
| `test_ob_snapshot_establishes_state` | SNAPSHOT 適用後、`snapshot()` が None でなくなる |
| `test_ob_diff_overwrites_quantity` | 同一 price の DIFF が上書き |
| `test_ob_diff_zero_quantity_removes_level` | quantity=0 で level 削除 |
| `test_ob_diff_adds_new_level` | 新規 price 追加 |
| `test_ob_diff_before_snapshot_rejected` | SNAPSHOT 未受領で DIFF → 棄却 |
| `test_ob_gap_detection_triggers_reinit` | update_id 不連続 → state クリア |
| `test_ob_after_gap_snapshot_recovers` | ギャップ後、次の SNAPSHOT で復旧 |
| `test_ob_stale_diff_rejected` | `final_update_id ≤ last_update_id` で棄却 |
| `test_ob_symbol_mismatch_raises` | 別 symbol → `ValueError` |
| `test_ob_deterministic_replay` | 同一入力 2 回で `snapshot()` 完全一致 |
| `test_ob_query_missing_price_returns_zero` | 存在しない価格 → `Decimal("0")` |

### 10.2 `tests/normalization/test_normalizer_depth.py`(必須 13 本)

| 名前 | 内容 |
|---|---|
| `test_depth_snapshot_normalization` | Binance snapshot 形式 → OrderBookUpdate |
| `test_depth_diff_normalization` | Binance depthUpdate 形式 → OrderBookUpdate |
| `test_depth_bids_asks_preserve_input_order` | tuple の順序保持 |
| `test_depth_decimal_values_exact` | Decimal 保持、float 混入なし |
| `test_depth_unknown_event_type_rejected` | 不明 `e` → NormalizationError |
| `test_depth_missing_final_update_id_rejected` | 必須欠落 |
| `test_depth_diff_missing_first_update_id_rejected` | DIFF の U 欠落 |
| `test_depth_filtered_when_no_mapping` | mapping None → `depth_filtered++` |
| `test_classify_raw_trade` | e=aggTrade → "trade" |
| `test_classify_raw_depth` | e=depthUpdate → "depth" |
| `test_classify_raw_no_mapping` | mapping なし → 常に "trade" |
| `test_profile_order_book_mapping_optional` | binance.yaml をロード成功 |
| `test_profile_order_book_mapping_missing_field_rejected` | 必須キー欠落 → ProfileError |

### 10.3 `tests/orderflow/test_volume_ref.py`(必須 6 本)

| 名前 | 内容 |
|---|---|
| `test_volume_ref_empty_returns_none` | observe なしで `current()` は None |
| `test_volume_ref_single_bar` | 1 バー投入で level 重み平均 |
| `test_volume_ref_window_slide` | `bars` 超過で古いバーが落ちる |
| `test_volume_ref_all_decimal` | float 混入なし |
| `test_volume_ref_deterministic` | 同一入力で同一値 |
| `test_volume_ref_invalid_bars_raises` | `bars < 1` → ValueError |

### 10.4 `tests/orderflow/test_absorption.py`(TV-ABS-01〜05 逐語 + 追加 4 本、計 9 本)

Fixture: `window=10s`, `price_stall_ticks=1`, `volume_multiplier=2.0`, `volume_ref=Decimal("50")` → aggression threshold = 100(TestSpecification §4.4 fixture 逐語)。

| 名前 | 内容 |
|---|---|
| `test_tv_abs_01_buy_absorption_qualifies` | 逐語: SELL 120 @ 100、price range=1 tick、bid replenished → BUY_ABSORPTION、strength=Decimal("1.0") |
| `test_tv_abs_02_aggression_fails` | SELL 80(<100)→ no event、`aggression_condition_fails==1` |
| `test_tv_abs_03_stall_fails` | 2 つの distinct price → no event、`stall_condition_fails==1` |
| `test_tv_abs_04_replenish_fails` | bid 減少、未 replenish → no event、`replenish_condition_fails==1` |
| `test_tv_abs_05_sell_absorption_qualifies` | BUY 150 @ 200、ask replenished → SELL_ABSORPTION、strength=Decimal("1.0") |
| `test_absorption_window_expiry` | 検出後 window_sec 超過で `current()` が None に戻る |
| `test_absorption_volume_ref_not_calibrated` | `volume_ref.current()` が None → no event、カウンタ非増加 |
| `test_absorption_book_state_uninitialized` | book_state 未初期化 → no event |
| `test_absorption_deterministic_replay` | 同一入力 2 回で `events_detected` と `current()` 完全一致 |

### 10.5 `tests/acquisition/test_binance_ws.py` 追記(4 本)

| 名前 | 内容 |
|---|---|
| `test_is_agg_trade_still_filters_depth` | 既存互換 |
| `test_is_agg_trade_or_depth_accepts_aggtrade` | aggTrade true |
| `test_is_agg_trade_or_depth_accepts_depth` | depthUpdate true |
| `test_is_agg_trade_or_depth_rejects_subscription_ack` | ack を弾く |

### 10.6 `tests/test_pipeline_absorption.py`(統合、必須 2 本)

| 名前 | 内容 |
|---|---|
| `test_pipeline_depth_flows_to_book_state` | replay で aggTrade + depthUpdate 混在 JSONL → book_state.snapshot() が期待通り、CVD/Footprint も期待通り、統計カウンタ整合 |
| `test_pipeline_absorption_veto_reaches_signal` | Absorption 発生する fixture で pipeline を回し、signals テーブルに ABSORPTION_VETO reason を含む WAIT signal が書かれる(TV-SIG-04 の pipeline 全経路版) |

### 10.7 既存テストの不変性

- 既存 135 tests が **1 本も落ちないこと** を最上位の完了条件とする
- `tests/orderflow/test_imbalance.py` は `volume_ref` 引数を渡さない既存 API で全 pass すること
- `tests/orderflow/test_signal.py` の `absorption_result` を明示指定するテストは既存通り green

---

## 11. 完了条件

- [ ] **既存 135 tests が 1 本も落ちない**(最上位、失敗時は他条件を検証しない)
- [ ] §10 の新規テスト全て green(合計 135 + 45 = 180 相当、実測件数は要報告)
- [ ] **Decimal オンリー禁則スキャン**: `grep -rn "float(" src/orderflow/ src/normalization/` の結果に、実装コードでの float 呼び出しが 0 件(コメントや docstring は除外)
- [ ] `binance.yaml` に `order_book_mapping` 追加、既存 trade マッピングは無変更
- [ ] `DataNormalizer.process`(trade 側)は 1 行も変更されていない
- [ ] `is_agg_trade` は残置、`is_agg_trade_or_depth` 追加
- [ ] `AbsorptionResult` 型シグネチャは stub 時代から不変
- [ ] `ImbalanceDetector` の `volume_ref` 引数はキーワード引数、default None、既存呼び出し全て無影響
- [ ] pipeline.py の Absorption 配線後、SignalEngine に `absorption_result=None` を渡す箇所が残っていないこと(実接続に完全置換)
- [ ] docs(`ArchitectureRepository/`)は無変更
- [ ] TV-ABS-01〜05 の実測結果を §12 で報告

---

## 12. 報告フォーマット + master 追記

### 12.1 チャット完了報告

- 新規テスト件数(旧 135 + 新規 n)
- TV-ABS-01〜05 の実測結果(pass/fail、5 件全て pass 必須)
- §7 設計判断 8 点について実装上の逸脱の有無
- Absorption / VolumeRef / OrderBook の主要統計カウンタ実測値(統合テスト実行時)
- Decimal 禁則スキャン結果
- 次フェーズ(引継ぎ書 §3 課題 2 の aggTrade + depth ライブ検証)着手可否

### 12.2 master 追記(恒久ルール)

`ArchitectureRepository/00_Master/CompletionLog.md` を新規作成 or 追記。末尾に本指示書の完了エントリを時系列で追加。内容はチャット完了報告と同一項目 + 実施日時 + 成果物ファイル一覧。

### 12.3 ZIP 提出

`ArchitectureRepository/` と `project/` を含むプロジェクト全体を `DeltaEngine_B_完了.zip` として提出。`__pycache__/`、`.pytest_cache/`、`data/parquet/`、`data/duckdb/` のバイナリ生成物は除外可、それ以外は全て含めること。
