この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_B2_M9Absorption_Pipeline配線_v1

**対象**: M9 Absorption 実装 + `volume_ref` 共有機構 + pipeline 配線(B-1 完了後の残作業)

**前提**: 指示書 B-1 完了済み。以下は B-1 で実装済み、本指示書では **再実装せず参照して使う**:
- `src/orderflow/orderbook.py`: `BookLevel` / `OrderBookUpdate` / `OrderBookSnapshot` / `OrderBookStateManager`
- `src/normalization/normalizer.py`: `process_depth` / `classify_raw` / `normalize_raw_depth` / `ExchangeProfile.order_book_mapping`
- `src/acquisition/binance_ws.py`: `is_agg_trade_or_depth`
- `config/profiles/binance.yaml`: `order_book_mapping` ブロック
- テスト: `test_orderbook.py` / `test_normalizer_depth.py` / `test_binance_ws.py` 追記分

**参照正本**:
- ArchitectureRepository/30_Modules/Absorption_v3.1.md
- ArchitectureRepository/30_Modules/SignalEngine_v3.1.md
- ArchitectureRepository/50_Test/TestSpecification_v3.2.md §4.4 (TV-ABS-01〜05)
- ArchitectureRepository/40_Reference/ErrorCodes_v3.1.md

---

## 0. スコープ

**含む**
1. `src/orderflow/volume_ref.py` 新規(Imbalance / Absorption 共有機構)
2. `src/orderflow/absorption.py` の stub を実装で置換(`AbsorptionResult` 型シグネチャは維持)
3. `src/orderflow/imbalance.py` に `volume_ref` 後方互換オプション追加
4. `src/pipeline.py` に depth 経路と Absorption を配線、SignalEngine の `absorption_result=None` を実接続に置換
5. 上記のユニットテスト + pipeline 統合テスト

**含まない**(将来別課題)
- REST snapshot 取得(初期化用)— fixture 駆動でテスト完結
- depth の永続化(容量問題、Signal のみ永続化する M11 方針を継続)
- ライブ Binance depth 検証

**docs 無変更**。CVD / Footprint / SignalEngine / storage / schema は無変更。

---

## 1. 成果物

**新規**
- `src/orderflow/volume_ref.py`
- `tests/orderflow/test_volume_ref.py`
- `tests/orderflow/test_absorption.py`
- `tests/test_pipeline_absorption.py`

**編集**
- `src/orderflow/absorption.py`(stub を実装で置換、`AbsorptionResult` は不変)
- `src/orderflow/imbalance.py`(`volume_ref` keyword 引数追加、既存挙動は default で無変更)
- `src/pipeline.py`(depth 経路配線 + Absorption 配線)

**編集不要**
- `src/orderflow/orderbook.py` / `cvd.py` / `footprint.py` / `signal.py`
- `src/normalization/normalizer.py` / `src/acquisition/binance_ws.py`
- `src/database/schema.py` / `storage.py`
- `config/profiles/binance.yaml`
- `ArchitectureRepository/` 配下

---

## 2. `src/orderflow/volume_ref.py` 新規

Absorption_v3.1 §6 の「`volume_ref` is the moving average of per-level volume over the most recent `volume_ref_bars` bars, shared with the Imbalance module」を実装。全 Decimal、float 禁止。

### 2.1 API

```python
class VolumeRefTracker:
    def __init__(self, bars: int) -> None:
        """bars >= 1. Moving average window in confirmed bars."""

    def observe_bar(self, per_level_volumes: Iterable[Decimal]) -> None:
        """バー確定時に per-level volume 群を投入。
        当該バーの全 price level の (buy_volume + sell_volume) を渡す。"""

    def current(self) -> Optional[Decimal]:
        """直近 `bars` バーの per-level volume 移動平均。
        1 バーも観測されていなければ None。"""

    bars: int
    observations: int  # これまでに投入されたバー数
```

内部は直近 `bars` 本のリスト群を deque で保持。`current()` はレベル重み平均 = Σ(全レベル全 volume) / Σ(全レベル数)。バーごとに level 数が異なるための単純平均ではない点に注意。

`bars < 1` → `ValueError`。

---

## 3. `src/orderflow/absorption.py` 実装(stub 置換)

### 3.1 型(stub からの維持)

`AbsorptionResult` の型シグネチャは B-1 完了時点と **完全に一致** させること。SignalEngine が参照しているため:

```python
@dataclass(frozen=True)
class AbsorptionResult:
    classification: str    # "BUY_ABSORPTION" | "SELL_ABSORPTION"
    strength: Decimal      # 0.0..1.0
```

### 3.2 検出器

```python
class AbsorptionDetector:
    def __init__(
        self,
        *,
        window_sec: int,
        price_stall_ticks: int,
        volume_multiplier: Decimal,
        volume_ref: VolumeRefTracker,
        book_state: OrderBookStateManager,
    ) -> None: ...

    def observe_trade(self, trade: FootprintTrade) -> None: ...
    def current(self) -> Optional[AbsorptionResult]: ...

    # カウンタ(no silent loss)
    events_detected: int
    aggression_condition_fails: int
    stall_condition_fails: int
    replenish_condition_fails: int
```

### 3.3 検出ロジック(Absorption_v3.1 §5.2 逐語)

sliding window `window_sec` 秒。tick 到着ごとに以下を評価。

**Step 1. Window 内 trade 整理**
- 現 tick の `event_time` から `window_sec` 秒より古い trade を deque 先頭から削除
- window の先頭が変わった瞬間(古い trade が抜けた瞬間)に `book_state.snapshot()` を捕捉して `window_start_snapshot` に保存
- window が空の状態から最初の trade が入った瞬間もその時点の snapshot を保存
- `book_state.snapshot()` が None(未初期化)なら評価不可、`current()` は None

**Step 2. Directional aggression 集計**
- window 内 BUY side volume 合計 = `agg_buy`
- window 内 SELL side volume 合計 = `agg_sell`

**Step 3. Stall condition(§7 決定 1)**
- window 内 trade の distinct price 数 ≤ `price_stall_ticks` → 通過
- 超過 → `stall_condition_fails++`、両方向 no event

**Step 4. Aggression condition**
- `threshold = volume_ref.current() × volume_multiplier`
- `volume_ref.current()` が None → threshold 未確定、no event(カウンタ非増加、sink 動作)
- SELL 側評価: `agg_sell >= threshold` → Buy Absorption 候補
- BUY 側評価: `agg_buy >= threshold` → Sell Absorption 候補
- 両方向未満 → `aggression_condition_fails++`、no event

**Step 5. Replenish condition(§5.2 条件 3)**
- 対象価格レベル群 = window 内で発生した distinct price のセット
- 現在の `book_state.snapshot()` を取得
- Buy Absorption 候補: 対象各 price で `current.bid_quantity_at(p) >= window_start_snapshot.bid_quantity_at(p)`。全レベルで満たすこと
- Sell Absorption 候補: 対象各 price で ask 側で同様
- 満たさない → `replenish_condition_fails++`、no event

**Step 6. 判定と strength**
- 全 3 条件通過 → `AbsorptionResult` 生成、`events_detected++`
- `strength = min(aggressive_volume / (volume_ref.current() × volume_multiplier), Decimal("1.0"))`(§5.4 逐語)
- classification: SELL aggression 吸収 → `"BUY_ABSORPTION"`、BUY aggression 吸収 → `"SELL_ABSORPTION"`

### 3.4 `current()` 意味論

Absorption 検出時、その AbsorptionResult は window_sec 秒間 `current()` から返り続ける。window 外れで None 復帰。SignalEngine は bar 確定時に `current()` を問い合わせる(M10 TV-SIG-04 と整合)。

---

## 4. 設計判断(B-1 から追加分のみ)

### 決定 1: `price_stall_ticks` の解釈

正本に tick_size 定義なし。M8 (Imbalance) 先例と一致させ、**「window 内 distinct executed price 数の許容数」** と解釈する。value=1 なら「1 価格レベルに張り付き」。

- TV-ABS-01(price range=1 tick): 全 trade が price=100 → distinct=1 ≤ 1 → OK
- TV-ABS-03(price range=2 ticks): 2 価格 → distinct=2 > 1 → fail

### 決定 2: `volume_ref` 未較正時の動作

`VolumeRefTracker.current()` が None(バー観測 0)の間:
- Absorption: threshold 未確定 → no event(sink)
- Imbalance: 既存 `min_volume` パラメータにフォールバック
- pipeline はエラーなく継続(M11 の cvd_slope_ref 思想と同じ)

### 決定 3: `window_start_snapshot` 捕捉タイミング

sliding window の左端が動いた瞬間、その時点の `book_state.snapshot()` を保存。window が空の状態から最初の trade 到着時も、その時点の snapshot を初期 window_start とする。

### 決定 4: Absorption は tick 駆動、SignalEngine 問い合わせは bar 駆動

Absorption は sliding window で常時評価。SignalEngine は bar 確定時に `AbsorptionDetector.current()` を呼ぶ。

### 決定 5: 両方向同時発火の扱い

両方向候補が同時に条件通過する状況は理論上想定外だが、防御として BUY_ABSORPTION 優先で採用、`double_direction_events` カウンタを増やす。実務ベクタでは発火しない前提。

---

## 5. `src/orderflow/imbalance.py` 編集

`ImbalanceDetector.__init__` に **keyword 引数** で `volume_ref: Optional[VolumeRefTracker] = None` を追加。既存呼び出しは無影響。

評価時の挙動:
- `volume_ref is None` → 既存の `min_volume` を使う(既存挙動そのまま)
- `volume_ref is not None` かつ `volume_ref.current() is not None` → `min_volume` の代わりに `volume_ref.current()` を評価しきい値として使う
- `volume_ref is not None` かつ `volume_ref.current() is None` → 既存 `min_volume` にフォールバック

既存 `tests/orderflow/test_imbalance.py` は無変更で全 pass すること。

---

## 6. `src/pipeline.py` 配線

### 6.1 変更点

Replay / Live 両パイプラインで以下を実施:

1. `DataReceiver` の `validate` を `is_agg_trade` から **`is_agg_trade_or_depth`** に差し替え
2. Normalizer 呼び出し前に `normalizer.classify_raw(raw)` で trade / depth 振り分け:
   - `"trade"` → 既存の `normalizer.process(raw)` 経路(CVD / Footprint / Imbalance)
   - `"depth"` → `normalizer.process_depth(raw)` → `book_state.apply(update)`
3. コンストラクタで以下を生成し pipeline に保持:
   - `book_state = OrderBookStateManager(symbol=config.market.symbol)`
   - `volume_ref = VolumeRefTracker(bars=config.absorption.volume_ref_bars)`
   - `absorption = AbsorptionDetector(window_sec=config.absorption.window, price_stall_ticks=config.absorption.price_stall_ticks, volume_multiplier=Decimal(str(config.absorption.volume_multiplier)), volume_ref=volume_ref, book_state=book_state)`
   - `imbalance = ImbalanceDetector(..., volume_ref=volume_ref)` (既存インスタンス化に keyword 引数追加のみ)
4. tick 到着時(既存の CVD/Footprint/Imbalance の並列位置)に `absorption.observe_trade(trade)` を追加
5. バー確定時に `volume_ref.observe_bar([...])` を呼ぶ。投入する per-level volume は当該バーの `FootprintBar.levels` の各 `PriceLevel` の `buy_volume + sell_volume`
6. SignalEngine 評価時に `absorption_result=absorption.current()` を渡す(現行の `None` 固定を置換)

### 6.2 触らない

- CVD / Footprint / SignalEngine の入出力型
- Storage 経路(depth と Absorption result は永続化しない、Signal のみ既存通り)
- pipeline.py の Replay / Live wrapper の関数分割構造

### 6.3 config 参照

`config.absorption` 配下(`window`、`price_stall_ticks`、`volume_multiplier`、`volume_ref_bars`)が既存 config スキーマにあることを確認して使う。存在しないキーがあれば `config.py` に追加(既存パターンに合わせて default 値を設定)。

---

## 7. テスト

### 7.1 `tests/orderflow/test_volume_ref.py`(6 本)

| 名前 | 内容 |
|---|---|
| `test_volume_ref_empty_returns_none` | observe なしで `current()` は None |
| `test_volume_ref_single_bar` | 1 バー投入でレベル重み平均 |
| `test_volume_ref_window_slide` | `bars` 超過で古いバーが落ちる |
| `test_volume_ref_all_decimal` | float 混入なし |
| `test_volume_ref_deterministic` | 同一入力で同一値 |
| `test_volume_ref_invalid_bars_raises` | `bars < 1` → ValueError |

### 7.2 `tests/orderflow/test_absorption.py`(TV-ABS-01〜05 逐語 + 追加 4 本、計 9 本)

Fixture: `window=10s`, `price_stall_ticks=1`, `volume_multiplier=Decimal("2.0")`, `volume_ref=Decimal("50")` → aggression threshold = 100(TestSpecification §4.4 逐語)。

`volume_ref` は事前に `observe_bar` で current が Decimal("50") を返すよう較正した状態からテスト開始。book_state も SNAPSHOT で初期化した状態から開始。

| 名前 | 内容 |
|---|---|
| `test_tv_abs_01_buy_absorption_qualifies` | SELL 120 @ 100、distinct=1、bid replenished → `BUY_ABSORPTION`、strength=Decimal("1.0") |
| `test_tv_abs_02_aggression_fails` | SELL 80 → no event、`aggression_condition_fails==1` |
| `test_tv_abs_03_stall_fails` | 2 distinct prices → no event、`stall_condition_fails==1` |
| `test_tv_abs_04_replenish_fails` | bid が window_start より減少 → no event、`replenish_condition_fails==1` |
| `test_tv_abs_05_sell_absorption_qualifies` | BUY 150 @ 200、ask replenished → `SELL_ABSORPTION`、strength=Decimal("1.0") |
| `test_absorption_window_expiry` | 検出後 window_sec 超過で `current()` が None |
| `test_absorption_volume_ref_not_calibrated` | `volume_ref.current()` が None → no event、カウンタ非増加 |
| `test_absorption_book_state_uninitialized` | book_state 未初期化 → no event |
| `test_absorption_deterministic_replay` | 同一入力 2 回で `events_detected` と `current()` 完全一致 |

### 7.3 `tests/test_pipeline_absorption.py`(統合、2 本)

| 名前 | 内容 |
|---|---|
| `test_pipeline_depth_flows_to_book_state` | replay で aggTrade + depthUpdate 混在 JSONL(depth は fixture リテラル) → `book_state.snapshot()` が期待通り、CVD/Footprint も期待通り、カウンタ整合 |
| `test_pipeline_absorption_veto_reaches_signal` | Absorption 発生 fixture で pipeline を回し、`signals` テーブルに ABSORPTION_VETO 由来の WAIT signal が書かれる(TV-SIG-04 の pipeline 全経路版) |

### 7.4 既存テストの不変性

- 既存 168 tests が **1 本も落ちないこと** を最上位の完了条件とする
- `test_imbalance.py` は `volume_ref` 引数を渡さない既存 API で全 pass
- `test_signal.py` の `absorption_result` を明示指定するテストは既存通り green

---

## 8. 完了条件

- [ ] **既存 168 tests が 1 本も落ちない**(最上位)
- [ ] §7 の新規テスト全 green(6 + 9 + 2 = 17 本、合計 168 + 17 = 185 見込み、実測は要報告)
- [ ] **Decimal 禁則スキャン**: `grep -rn "float(" src/orderflow/` の実装コードでの float 呼び出しが 0 件
- [ ] `AbsorptionResult` 型シグネチャは stub 時代から不変
- [ ] `ImbalanceDetector` の `volume_ref` はキーワード引数 default None、既存呼び出し無影響
- [ ] pipeline.py で SignalEngine に `absorption_result=None` を渡す箇所が残っていないこと(実接続に完全置換)
- [ ] `is_agg_trade_or_depth` が pipeline の validate に差し替わっていること
- [ ] docs(`ArchitectureRepository/`)は無変更
- [ ] B-1 で作成された `orderbook.py` / `normalizer.py` の depth 部 / `binance_ws.py` の新 predicate / `binance.yaml` の `order_book_mapping` は無変更(参照のみ)
- [ ] TV-ABS-01〜05 の実測結果を §9 で報告

---

## 9. 報告フォーマット + master 追記 + ZIP 提出

### 9.1 チャット完了報告

- 新規テスト件数(旧 168 + 新規 n)
- TV-ABS-01〜05 の実測結果(5 件全て pass 必須)
- §4 設計判断 5 点について実装上の逸脱の有無
- Absorption / VolumeRef の主要統計カウンタ実測値(統合テスト実行時)
- Decimal 禁則スキャン結果
- 次フェーズ(引継ぎ書 §3 課題 2 の aggTrade + depth ライブ検証)着手可否

### 9.2 master 追記(恒久ルール)

`ArchitectureRepository/00_Master/CompletionLog.md` を新規作成 or 追記。末尾に本指示書の完了エントリを時系列で追加。内容はチャット完了報告と同一項目 + 実施日時 + 成果物ファイル一覧 + 逸脱の有無。

B-1 の完了エントリが未追記であれば **併せて後追い追記** すること(B-1 → B-2 の時系列順)。

### 9.3 ZIP 提出

`ArchitectureRepository/` と `project/` を含むプロジェクト全体を `DeltaEngine_B2_完了.zip` として提出。`__pycache__/`、`.pytest_cache/`、`data/parquet/`、`data/duckdb/` のバイナリ生成物は除外可、それ以外は全て含めること。
