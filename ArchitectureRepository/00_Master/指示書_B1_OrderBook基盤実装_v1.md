この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_B1_OrderBook基盤実装_v1

**対象**: Order Flow Analysis Platform — Order Book 正規化基盤の実装(M9 Absorption 実装の前提)
**参照正本**:
- ArchitectureRepository/40_Reference/MarketDataSchema_v3.2.md (指示書 A で追加)
- ArchitectureRepository/40_Reference/JSONSchema_v3.2.md §7 (指示書 A で追加)
- ArchitectureRepository/40_Reference/YAMLReference_v3.2.md §4.1 (指示書 A で追加)
- ArchitectureRepository/30_Modules/DataNormalizer_v3.2.md §2〜§4
- ArchitectureRepository/30_Modules/DataReceiver_v3.1.md §4
- ArchitectureRepository/40_Reference/ErrorCodes_v3.1.md
- ArchitectureRepository/40_Reference/DOMReference_v3.0.md (用語のみ)
- ArchitectureRepository/40_Reference/LiquidityReference_v3.0.md (用語のみ)

---

## 0. 前提・スコープ

M7〜M11 と同じ粒度。**Order Book 正規化パスと Order Book State Manager までを実装する** 指示書。

### 0.1 スコープ内

1. Binance exchange profile への `order_book_mapping` 追加
2. `DataNormalizer` の depth 正規化パス追加(既存 trade パスと並列に共存)
3. Acquisition 層(`binance_ws.py`)の depth フレーム透過(現行は意図的に filter out されている)
4. **新規モジュール** `src/orderflow/orderbook.py`: Order Book Update 型と Order Book State Manager
5. 上記に対応するユニットテスト

### 0.2 スコープ外(後続の指示書 B-2 で扱う)

- Absorption 検出ロジックの実装(`src/orderflow/absorption.py` の stub 置換)
- pipeline.py への depth 経路・Absorption 配線
- `volume_ref` の Imbalance / Absorption 共有機構
- REST snapshot 取得(初期化用)
- depth の永続化(fixture 駆動で決定的リプレイを担保する方針、下記 §4 決定 4 参照)
- ライブ Binance 接続での depth 検証

### 0.3 既存パスの不変性

- CVD / Footprint / Imbalance / SignalEngine の実装は無変更
- 既存 135 tests は無影響で green のまま
- pipeline.py への配線変更は行わない(B-2 で一括配線)
- Repository(docs)は無変更(必要な追加は指示書 A で完了済み)

---

## 1. 成果物

**新規ファイル**

- `src/orderflow/orderbook.py` (Order Book 型 + State Manager)
- `tests/orderflow/test_orderbook.py`
- `tests/normalization/test_normalizer_depth.py`

**既存ファイル編集**

- `config/profiles/binance.yaml` (`order_book_mapping` ブロック追加)
- `src/normalization/normalizer.py` (depth 正規化パス追加、既存 trade パスは無変更)
- `src/acquisition/binance_ws.py` (`is_agg_trade` predicate を depth 併存版に置換)

**編集不要(ただし影響確認)**

- `src/pipeline.py` — 触らない
- `src/acquisition/receiver.py` — 触らない(既存 `validate` 差し替えのみで対応)
- `src/orderflow/absorption.py` — 触らない(stub のまま)

---

## 2. `config/profiles/binance.yaml` の編集

現行ファイルの末尾に以下ブロックを追加する(既存トレード側マッピングは 1 行も変更しない)。

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

コメントで「Binance Futures @depth stream は `e = "depthUpdate"` を送出する。`depthSnapshot` は REST 経由で取得した初期スナップショットに acquisition 層で付与される想定(B-1 スコープ外)」と 1 行注記すること。

---

## 3. 新規モジュール `src/orderflow/orderbook.py`

CVD_v3.2 / Footprint / Imbalance 実装と同じスタイルで書く。全て Decimal 演算、float 禁止。

### 3.1 型定義

```python
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

@dataclass(frozen=True)
class BookLevel:
    price: Decimal
    quantity: Decimal

@dataclass(frozen=True)
class OrderBookUpdate:
    """Canonical Order Book Update Record (MarketDataSchema_v3.2)."""
    event_time: datetime
    symbol: str
    update_type: str          # "SNAPSHOT" | "DIFF"
    first_update_id: int | None   # DIFF のみ、SNAPSHOT では None 可
    final_update_id: int
    bids: tuple[BookLevel, ...]   # 順序は入力順のまま保持
    asks: tuple[BookLevel, ...]

@dataclass(frozen=True)
class OrderBookSnapshot:
    """Immutable point-in-time state (state manager から取り出す)."""
    symbol: str
    last_update_id: int
    bids: dict[Decimal, Decimal]  # price → quantity, quantity > 0 のみ
    asks: dict[Decimal, Decimal]

    def bid_quantity_at(self, price: Decimal) -> Decimal:
        return self.bids.get(price, Decimal("0"))

    def ask_quantity_at(self, price: Decimal) -> Decimal:
        return self.asks.get(price, Decimal("0"))

@dataclass(frozen=True)
class ApplyResult:
    applied: bool
    reinitialized: bool
    gap_detected: bool
```

`__post_init__` で必要な Decimal 化を行う(CVD の `_to_decimal` パターンを再利用可能)。

### 3.2 `OrderBookStateManager`

内部状態は mutable(パフォーマンス上、都度 immutable 化は避ける)。`snapshot()` で immutable コピーを返す。

```python
class OrderBookStateManager:
    def __init__(self, symbol: str) -> None: ...
    def apply(self, update: OrderBookUpdate) -> ApplyResult: ...
    def snapshot(self) -> OrderBookSnapshot | None:
        """State 未初期化(SNAPSHOT 未受領 or ギャップ後 reinitializing)なら None。"""
    def bid_quantity_at(self, price: Decimal) -> Decimal: ...
    def ask_quantity_at(self, price: Decimal) -> Decimal: ...
    # 統計カウンタ(no silent loss、DataNormalizer §7 準拠)
    snapshots_applied: int
    diffs_applied: int
    diffs_rejected_before_snapshot: int
    gaps_detected: int
```

### 3.3 apply の処理ルール

MarketDataSchema_v3.2 の §Order Book Update Record 意味論をそのまま実装する。

| 入力 | 現在状態 | 挙動 |
|---|---|---|
| SNAPSHOT | 任意 | 既存 bids/asks を全消去、update の levels をそのまま設定。`last_update_id` 更新。`applied=True, reinitialized=(既存があった場合 True)` |
| DIFF | State 未初期化(SNAPSHOT 未受領 or 直前ギャップ検知後) | 棄却、`diffs_rejected_before_snapshot++`、`applied=False`。ErrorCode E3005(下記 §4 決定 1) |
| DIFF | 初期化済、`first_update_id == last_update_id + 1` | 各 level を「quantity=0 なら削除、そうでなければ set-to-value」で適用。`last_update_id = final_update_id`。`applied=True` |
| DIFF | 初期化済、`first_update_id != last_update_id + 1` | ギャップ検知。State を破棄(bids/asks クリア、`last_update_id` を None にリセット)、`gaps_detected++`、`applied=False, gap_detected=True`。次の SNAPSHOT を待つ |

`symbol` は state manager 生成時に指定した値と一致すること。不一致なら `ValueError`。

### 3.4 決定論

- 内部 dict の反復順は Python の挿入順に依存するため、`snapshot()` が返す dict はコピーで返し、呼び出し側での順序依存を避ける
- 同一入力シーケンスに対し `snapshot()` の内容は完全一致(CVD と同じ性質)

---

## 4. 設計判断(正本に明記がないため、本指示書で確定)

### 決定 1: ギャップ検知時のエラーコード

DIFF の `first_update_id` が期待値と一致しない場合、および SNAPSHOT 未受領での DIFF 到着時に、ErrorCodes_v3.1 のどれを流用するか。

- E3003(Processing pipeline failure)は「パイプライン破綻」寄りで重い
- E3004(Out-of-order event rejected)は「同一ストリーム内の並べ替え不可」の意味で近い
- E3001(Invalid trade data)は不適

**決定: E3004 を流用する**。「順序破綻による棄却」というセマンティクスが最も近く、既存の `ERROR_OUT_OF_ORDER` 記号を再利用する(新規 error code を勝手に発番しない)。ログメッセージで `order book gap detected` / `diff before snapshot` を明記する。

### 決定 2: DataNormalizer の depth 経路の返り値

CVD 側の `process()` は `list[NormalizedTrade]` を返す(reorder buffer 由来)。Order Book 側は reorder しない(§4 決定 3 参照)ため、`process_depth(raw) -> OrderBookUpdate | None` として単発返却する。Normalization 失敗時は `None`、統計カウンタ増加。

### 決定 3: depth の重複・順序ハンドリング

- **重複**: DIFF の `final_update_id` が既に適用済みの `last_update_id` 以下なら重複と見なして棄却(state manager 側で処理、`diffs_rejected_before_snapshot` とは別カウンタ `diffs_stale` を追加)
- **順序**: 同一 WebSocket ストリーム内で depth フレームが exchange 側で順序保証されている前提。trade 側で使っている `reorder_tolerance` は depth には適用しない(update_id ベースで判定するため)。

### 決定 4: 決定的リプレイの範囲

- **trade**: 現行の JSONL 記録で確保(既存の `JsonlRecorder`、変更なし)
- **depth**: JSONL には記録しない(容量が桁違いに膨らむため)。決定的リプレイはテストフィクスチャ(JSON リテラル)経由で担保する。TV-OB-XX テストは全てフィクスチャ駆動とする。ライブから完全再現する需要が出た時点で別課題

### 決定 5: `order_book_mapping` がない profile の扱い

現行トレード専用の後方互換性を確保する。`ExchangeProfile.from_dict` は `order_book_mapping` を optional として受け入れ、キーが存在しなければ `order_book_mapping = None` を設定する。`DataNormalizer.process_depth` は `profile.order_book_mapping is None` の場合、即座に `None` を返し、統計カウンタ `depth_filtered` を増加させる(棄却ではないので `rejected` ではなく `filtered`)。

### 決定 6: symbol の canonical 化

trade 側は既存の profile mapping で `symbol` フィールドが小文字("btcusdt")のまま入る場合と大文字("BTCUSDT")の場合があるが、現行 CVD テストは大文字を前提としている(TV-CVD 等)。Order Book 側も **入力値をそのまま canonical symbol として扱う**(上位で正規化する責務は本指示書スコープ外、既存 CVD と同じ扱い)。ただし、`OrderBookStateManager` を生成する側で symbol の統一を担保するのは呼び出し側の責務(pipeline 配線の B-2 で扱う)。

---

## 5. `src/normalization/normalizer.py` の編集

### 5.1 `ExchangeProfile` の拡張

```python
@dataclass(frozen=True)
class ExchangeProfile:
    profile_name: str
    field_mapping: dict[str, str]
    timestamp_format: str
    order_book_mapping: dict[str, Any] | None = None  # 新規、default None

    @classmethod
    def from_dict(cls, data): ...
```

`from_dict` は `order_book_mapping` キーが存在すれば dict として受け入れ、以下のキーが全て揃っていることを検証する(欠けたら `ProfileError` E1002):

```
event_type_field, event_type_snapshot, event_type_diff,
symbol_field, event_time_field,
first_update_id_field, final_update_id_field,
bids_field, asks_field,
level_price_index, level_quantity_index
```

`level_price_index` / `level_quantity_index` は int 型であること。

### 5.2 新規関数 `normalize_raw_depth`

```python
def normalize_raw_depth(
    raw: dict, profile: ExchangeProfile,
) -> OrderBookUpdate:
    """Map one raw depth event to a canonical Order Book Update.
    Raises NormalizationError on unmappable input."""
```

処理内容:
- `profile.order_book_mapping is None` なら `NormalizationError("no order_book_mapping in profile")`(呼び出し側でこれが起きないよう `DataNormalizer.process_depth` で先に filter するため、実運用ではここには到達しない。防御的にのみ実装)
- `event_type_field` の値を見て、`event_type_snapshot` と一致 → `update_type = "SNAPSHOT"`、`event_type_diff` と一致 → `update_type = "DIFF"`、どちらでもない → `NormalizationError`
- `symbol`、`event_time`(profile の `timestamp_format` で変換)、`final_update_id` を抽出
- SNAPSHOT の場合、`first_update_id` は raw に存在すれば取得、なければ `None`
- DIFF の場合、`first_update_id` は必須(欠けたら `NormalizationError`)
- `bids_field` / `asks_field` の配列を取り出し、各要素の `level_price_index` / `level_quantity_index` から `BookLevel(price=Decimal, quantity=Decimal)` を構築
- 入力順を保持したまま `tuple[BookLevel, ...]` に格納

### 5.3 `DataNormalizer` クラスへの追加

trade 側のメソッド(`process` / `flush` / dedup / reorder)は **1 行も変更しない**。以下を追加:

```python
class DataNormalizer:
    # 既存フィールドに追加
    depth_processed: int = 0
    depth_rejected: int = 0
    depth_filtered: int = 0  # order_book_mapping なしで素通り

    def process_depth(self, raw: dict) -> OrderBookUpdate | None:
        """Process one raw depth event; return canonical update or None."""
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
```

### 5.4 分類ヘルパ

pipeline 側で raw を trade か depth かに振り分けるため、以下を追加:

```python
def classify_raw(self, raw: dict) -> str:
    """Return "trade" | "depth" | "unknown"."""
    ob = self.profile.order_book_mapping
    if ob is not None and raw.get(ob["event_type_field"]) in (
        ob["event_type_snapshot"], ob["event_type_diff"]
    ):
        return "depth"
    # trade 側は Binance aggTrade の e="aggTrade" を含む raw を trade 扱いにする
    # ただし、profile に event 判別フィールドが無い場合もあるため、
    # trade 側は「depth ではないなら trade」の消極的判定とする
    return "trade"
```

pipeline 側で使うことを想定しているが、B-1 では pipeline 配線を触らないため、本ヘルパは追加のみ(呼び出しは B-2 で行う)。ユニットテストは追加する。

---

## 6. `src/acquisition/binance_ws.py` の編集

現行 `is_agg_trade` は depth を意図的に filter out している(Phase6 decision)。B-1 では depth を通す予定なので、以下のように **並列関数を追加**し、`is_agg_trade` は互換のため残す。

```python
def is_agg_trade(message: Any) -> bool:
    """既存: aggTrade のみ true。互換のため残置。"""
    return isinstance(message, dict) and message.get("e") == "aggTrade"

def is_agg_trade_or_depth(message: Any) -> bool:
    """B-1 追加: aggTrade または depthUpdate を通す。
    subscription-ack 等はここで弾く。"""
    if not isinstance(message, dict):
        return False
    return message.get("e") in ("aggTrade", "depthUpdate")
```

pipeline 側の validate 差し替えは B-2 で行う。B-1 では関数追加とテストのみ。

---

## 7. テスト

### 7.1 `tests/orderflow/test_orderbook.py`

**フィクスチャ駆動**(§4 決定 4)。全て Decimal ベース、float 禁止。

必須テスト(TV 番号は独自命名、CVD/Footprint/Imbalance のスタイルに準拠):

| 名前 | 内容 |
|---|---|
| `test_ob_snapshot_establishes_state` | SNAPSHOT 適用後、`snapshot()` が None でなくなり、bids/asks が入力通り |
| `test_ob_diff_overwrites_quantity` | SNAPSHOT の後、同じ price の DIFF が来ると quantity が上書きされる |
| `test_ob_diff_zero_quantity_removes_level` | DIFF で `quantity=0` の level は削除される |
| `test_ob_diff_adds_new_level` | DIFF で SNAPSHOT に無かった price を追加できる |
| `test_ob_diff_before_snapshot_rejected` | SNAPSHOT 未受領で DIFF 到着 → 棄却、`diffs_rejected_before_snapshot == 1` |
| `test_ob_gap_detection_triggers_reinit` | `first_update_id != last_update_id + 1` の DIFF → state クリア、`gap_detected=True`、`gaps_detected == 1` |
| `test_ob_after_gap_snapshot_recovers` | ギャップ後、次の SNAPSHOT で state 復旧 |
| `test_ob_stale_diff_rejected` | `final_update_id <= last_update_id` の DIFF → 棄却(§4 決定 3 の重複扱い) |
| `test_ob_symbol_mismatch_raises` | 別 symbol の update を apply すると `ValueError` |
| `test_ob_deterministic_replay` | 同一入力シーケンス 2 回 → `snapshot()` の bids/asks/last_update_id 完全一致 |
| `test_ob_query_missing_price_returns_zero` | `bid_quantity_at(存在しない価格)` → `Decimal("0")` |

### 7.2 `tests/normalization/test_normalizer_depth.py`

| 名前 | 内容 |
|---|---|
| `test_depth_snapshot_normalization` | Binance 形式の snapshot raw → OrderBookUpdate(update_type="SNAPSHOT") |
| `test_depth_diff_normalization` | Binance 形式の depthUpdate raw → OrderBookUpdate(update_type="DIFF")、first/final id 反映 |
| `test_depth_bids_asks_preserve_input_order` | 入力 array 順が tuple に保持される |
| `test_depth_decimal_values_exact` | price/quantity が Decimal で正確に保持(float 混入なし) |
| `test_depth_unknown_event_type_rejected` | `e` が snapshot/diff どちらでもない → NormalizationError、`depth_rejected` インクリメント |
| `test_depth_missing_final_update_id_rejected` | 必須フィールド欠落 → NormalizationError |
| `test_depth_diff_missing_first_update_id_rejected` | DIFF で `U` 欠落 → NormalizationError |
| `test_depth_filtered_when_no_mapping` | `order_book_mapping = None` の profile → `process_depth` が None、`depth_filtered == 1` |
| `test_classify_raw_trade` | `{"e": "aggTrade", ...}` → `"trade"` |
| `test_classify_raw_depth` | `{"e": "depthUpdate", ...}` → `"depth"` |
| `test_classify_raw_no_mapping` | profile に `order_book_mapping` なし → 常に `"trade"` |
| `test_profile_order_book_mapping_optional` | binance.yaml と同形式の dict をロードして `ExchangeProfile.from_dict` 成功 |
| `test_profile_order_book_mapping_missing_field_rejected` | `order_book_mapping` から必須キー 1 つ欠落 → `ProfileError` (E1002) |

### 7.3 `tests/acquisition/test_binance_ws.py` への追記

既存のテストは無変更で、以下を **追記**:

| 名前 | 内容 |
|---|---|
| `test_is_agg_trade_still_filters_depth` | 既存互換 |
| `test_is_agg_trade_or_depth_accepts_aggtrade` | 新規 predicate、aggTrade true |
| `test_is_agg_trade_or_depth_accepts_depth` | 新規 predicate、depthUpdate true |
| `test_is_agg_trade_or_depth_rejects_subscription_ack` | 新規 predicate、subscription ack を弾く |

### 7.4 Binance 実 payload に近い最小サンプル

テストで使用する raw のサンプル形は以下(Binance Futures @depth@100ms 準拠):

```python
# depthUpdate
{
    "e": "depthUpdate",
    "E": 1700000000123,
    "s": "BTCUSDT",
    "U": 100,
    "u": 105,
    "b": [["99999.50", "1.250"], ["99999.00", "0"]],
    "a": [["100000.00", "0.800"]]
}
```

SNAPSHOT は本 B-1 スコープでは wire 上には流れない(acquisition が REST snapshot に付与する想定は B-2 以降)ため、テストでは `"e": "depthSnapshot"` を持つ raw を artificial に組んで normalizer と state manager を検証する。

---

## 8. 完了条件

- [ ] `src/orderflow/orderbook.py` が全 Decimal 演算(float 不使用)
- [ ] `binance.yaml` に `order_book_mapping` ブロックが追加され、既存トレード側マッピングは無変更
- [ ] `ExchangeProfile.from_dict` が `order_book_mapping` を optional で受け入れ、既存プロファイル読み込みは無影響
- [ ] `DataNormalizer.process`(trade 側)は 1 行も変更されていない
- [ ] `DataNormalizer.process_depth` と `classify_raw` が追加されている
- [ ] `normalize_raw_depth` が新規追加されている
- [ ] `binance_ws.py` に `is_agg_trade_or_depth` が追加され、既存 `is_agg_trade` は無変更
- [ ] §7.1〜§7.4 の全テストが green
- [ ] 既存 135 tests は無影響で green のまま(合計 135 + n = ?)
- [ ] `pipeline.py`、`absorption.py`、`cvd.py`、`footprint.py`、`imbalance.py`、`signal.py` は無変更
- [ ] docs(Repository)は無変更(指示書 A で既に完了済み)

---

## 9. 報告フォーマット

完了後、以下を報告すること:

- 新規テスト件数(旧 135 件 + 新規 n 件)
- 主要 TV(TV-OB-XX 等)の実測結果サマリ
- §4 の設計判断 6 点について、実装上の逸脱があれば明記
- Order Book State Manager の主要統計カウンタ名(pipeline 配線時に参照するため)
- 指示書 B-2(M9 Absorption 実装 + pipeline 配線 + `volume_ref` 共有機構)着手可否の一言
