この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_M8_Imbalance実装_v1

**対象**: Order Flow Analysis Platform — M8（Imbalance 検出器）
**参照正本**: ArchitectureRepository/30_Modules/Imbalance_v3.1.md
**関連**: Footprint_v3.0.md / SignalEngine_v3.1.md / DataDictionary_v3.1.md / ErrorCodes_v3.1.md / TestSpecification_v3.2.md §4.3（TV-IMB-01〜06）
**現状確認済み**: `project/src/orderflow/footprint.py`（`PriceLevel`, `FootprintBar`）／ `project/src/config.py` の `imbalance` セクション（`ratio_threshold=3.0`, `min_volume=null`, `ratio_cap=10.0`, `stack_count=3`）を実ファイルから確認した上で本指示書を作成している。

---

## 0. 前提・スコープ

M7（Footprint 計算器）と同一の粒度。**検出器の実装とユニットテストのみ**を対象とし、pipeline.py への配線・Storage 永続化・SignalEngine 連携は本指示書のスコープ外。

入力は `footprint.py` の `FootprintBar`（確定済みバー、`levels: tuple[PriceLevel, ...]`、price 昇順ソート済み・重複価格なし）とする。tick footprint（`current_tick_snapshot()`）への適用は本指示書のスコープ外（将来必要になった時点で別途判断）。

**Repository（docs）は無変更**。

---

## 1. 成果物

- 新規: `src/orderflow/imbalance.py`
- 新規: `tests/orderflow/test_imbalance.py`

---

## 2. 仕様サマリ（Imbalance_v3.1 §5 より）

対角比較（Diagonal Comparison）:

```text
Buy Imbalance  @P : BuyVol(P)  / SellVol(P−1tick) ≥ ratio_threshold
Sell Imbalance @P : SellVol(P) / BuyVol(P+1tick)  ≥ ratio_threshold
```

qualify 条件（すべて満たす場合のみ）:

1. **Ratio条件**: 対角比率 ≥ `ratio_threshold`
2. **Volume条件**: 比較対象2レベルの `BuyVol + SellVol` ≥ `min_volume`
3. **ゼロ分母規則**: 分母が0の場合、Volume条件(2)を満たせば qualify。報告比率は `ratio_cap` で頭打ち

Stacked Imbalance: 同方向に `stack_count` 以上連続して qualify するレベルが並んだ場合に成立。

---

## 3. 設計判断（正本に明記がないため、本指示書で確定する）

### 決定4: 「隣接価格レベル」の定義（P−1tick / P+1tick の解釈）

Footprint_v3.0 の決定2（tick_size丸めなし）により、正本・config のいずれにも `tick_size` は定義されていない（config.yaml・binance.yaml を確認済み、該当キーなし）。よって **「隣接」は `FootprintBar.levels`（price昇順・重複なし）における配列上のインデックス隣接とする**。つまり `levels[i]` と `levels[i+1]` を比較対象とし、実価格差が1tickかどうかの検証は行わない。

TV-IMB-01〜06 の全フィクスチャは連番価格（100/101, 101/102/103 等）を使っており、この解釈と矛盾しない。

### 決定5: `min_volume` のデフォルト（null → volume_ref）解決の扱い

`imbalance.min_volume` の config デフォルトは `null` であり、正本 §6 では null の場合 `volume_ref`（直近 `volume_ref_bars` 本の移動平均、Absorption と共有）を使うと定義されている。しかし移動平均の算出には複数バーの履歴保持が必要で、この機構は Absorption（M9、正本 §6 に "shared with Absorption module" と明記）と共同で設計すべき性質のものである。

M8では、TestSpecification の全フィクスチャが `min_volume` を直接の数値（例: 50）として与えていることに合わせ、**`min_volume` を検出器の必須パラメータとして受け取る**（null→自動算出のフォールバック機構は実装しない）。null解決ロジックは M9（Absorption）着手時に `volume_ref` 共有ユーティリティとして別途設計する。

### 決定6: エラーハンドリング

Imbalance_v3.1 §7 に「Missing Footprint data / Invalid volume / Price level inconsistency」が列挙されている。以下のように扱う:

| ケース | 挙動 |
|---|---|
| 入力 `FootprintBar.levels` が空 | Imbalance検出なし（空の結果を返す、エラーではない） |
| レベルの `buy_volume` / `sell_volume` が負値 | E3001 として棄却し、そのレベルペアはスキップ（他のレベルの検出は継続） |
| `levels` が price 非昇順（本来 Footprint 側で保証されるが防御的に検証） | E3001、検出処理全体を中断せず該当ペアのみスキップ |

---

## 4. インターフェース設計（CVD/Footprint実装パターンに準拠）

```python
@dataclass(frozen=True)
class BuyImbalance:
    price: Decimal
    ratio: Decimal

@dataclass(frozen=True)
class SellImbalance:
    price: Decimal
    ratio: Decimal

@dataclass(frozen=True)
class StackedImbalance:
    start_price: Decimal
    end_price: Decimal
    count: int
    direction: str  # "BUY" | "SELL"

@dataclass(frozen=True)
class ImbalanceResult:
    bar_time: datetime
    symbol: str
    buy_imbalances: tuple[BuyImbalance, ...]
    sell_imbalances: tuple[SellImbalance, ...]
    stacked_imbalances: tuple[StackedImbalance, ...]

class ImbalanceDetector:
    def __init__(
        self,
        ratio_threshold: Decimal,
        min_volume: Decimal,
        ratio_cap: Decimal,
        stack_count: int,
    ) -> None: ...

    def detect(self, bar: FootprintBar) -> ImbalanceResult:
        """FootprintBar.levels を配列インデックス隣接で対角比較する（決定4）。"""
```

Decimal演算のみ、float禁止。`_to_decimal` は `cvd.py` から再利用可。

---

## 5. テストベクタ（TestSpecification_v3.2 §4.3 準拠、必須）

fixture: `ratio_threshold=3.0`, `min_volume=50`（`volume_ref`固定値）, `ratio_cap=10.0`, `stack_count=3`

### TV-IMB-01 Ratio boundary（qualify）
SellVol(100)=100, BuyVol(101)=300。結合出来高400≥50。→ Buy Imbalance at 101, ratio 3.0

### TV-IMB-02 Ratio boundary（not qualify）
SellVol(100)=100, BuyVol(101)=299。→ imbalanceなし（ratio 2.99 < 3.0）

### TV-IMB-03 Zero denominator（qualify）
SellVol(100)=0, BuyVol(101)=60。結合60≥50。→ Buy Imbalance at 101, 報告ratio=10.0（capped）

### TV-IMB-04 Zero denominator（not qualify）
SellVol(100)=0, BuyVol(101)=40。結合40<50。→ imbalanceなし

### TV-IMB-05 Stacked Imbalance（qualify）
101, 102, 103 で連続して Buy Imbalance が qualify。→ Stacked Imbalance, direction BUY, count 3, range 101–103

### TV-IMB-06 Stacked Imbalance（not qualify）
101, 102 のみ qualify（2件、stack_count=3未満）。→ 個別 imbalance は publish、Stacked Imbalanceは成立しない

上記6件に加えて、以下を独自命名で追加すること:

- 決定4の確認: インデックス非隣接（価格が飛んでいる）2レベル間でも配列上隣接なら比較対象になること
- 決定6の確認: 負のvolumeを含むレベルペアがE3001棄却され、他のペアの検出に影響しないこと
- 決定的リプレイ（同一 `FootprintBar` を2回 `detect()` して出力完全一致）

---

## 6. 完了条件

- [ ] `ImbalanceDetector` が全て Decimal 演算（float不使用）
- [ ] TV-IMB-01〜06 をテストとして実装し green
- [ ] 追加テスト（決定4/決定6の確認、決定的リプレイ）green
- [ ] 既存 82 tests は無影響で green のまま
- [ ] `docs/`（Repository正本）は無変更
- [ ] pipeline.py・Storage・SignalEngineには触れない（M8スコープ外）

---

## 7. 報告フォーマット

完了後、以下を報告すること:

- 新規テスト件数（旧82件 + 新規n件）
- TV-IMB-01〜06 の実測結果
- §3 の設計判断3点（決定4/5/6）について、実装上の逸脱があれば明記
- 次M（M9 Absorption）着手可否の一言。特に決定5で保留にした `volume_ref` 共有ユーティリティの設計について、M9でどう扱うか一言添えること
