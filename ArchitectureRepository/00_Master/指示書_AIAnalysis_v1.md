この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_AIAnalysis_v1

**対象**: AI Analysis モジュール（MOD-009）
**参照正本**: AIAnalysis_v3.1.md / AIAnalysisPipelineReference_v3.0.md / EnumDefinitions_v3.1.md §4
**前提**: 188 passed。SignalEngine が SignalResult を返す。AI Analysis はその上流。

---

## 0. スコープ

計算器の実装とユニットテストのみ。pipeline 配線・Storage 永続化は別指示書。

正本無変更。`src/ai/__init__.py`（スケルトン）は上書きしてよい。

---

## 1. 成果物

- 新規: `src/ai/analysis.py`
- 新規: `tests/ai/test_analysis.py`
- 編集可: `src/ai/__init__.py`

---

## 2. 型

```python
@dataclass(frozen=True)
class AnalysisInput:
    analysis_time: datetime
    symbol: str
    signal_result: SignalResult          # from orderflow.signal
    cvd_delta: Decimal                  # 当該バーの CVD delta
    fp_buy_total: Decimal               # Footprint BUY 合計
    fp_sell_total: Decimal              # Footprint SELL 合計
    imbalance_result: Optional[ImbalanceResult]
    absorption_result: Optional[AbsorptionResult]

@dataclass(frozen=True)
class AnalysisResult:
    analysis_time: datetime
    symbol: str
    market_state: str       # STRONG_BULL | BULL | NEUTRAL | BEAR | STRONG_BEAR
    confidence: Decimal     # 0.0–1.0
    risk_level: str         # LOW | MEDIUM | HIGH
    summary: str            # human-readable
    reasons: tuple[str, ...]
```

全フィールド Decimal（float 禁止）。

---

## 3. AnalysisEngine

```python
class AnalysisEngine:
    def __init__(self, confidence_threshold: Decimal = Decimal("0.70")) -> None: ...

    def evaluate(self, inp: AnalysisInput) -> AnalysisResult: ...
```

### 3.1 market_state 判定（正本 AIAnalysisPipelineReference §MarketState + §Confidence）

SignalResult の signal と confidence を基軸にする:

| signal | confidence | market_state |
|--------|-----------|-------------|
| BUY | ≥ 0.90 | STRONG_BULL |
| BUY | ≥ 0.70 | BULL |
| BUY | < 0.70 | NEUTRAL |
| SELL | ≥ 0.90 | STRONG_BEAR |
| SELL | ≥ 0.70 | BEAR |
| SELL | < 0.70 | NEUTRAL |
| WAIT | any | NEUTRAL |

### 3.2 confidence

SignalResult.confidence をそのまま引き継ぐ（AI Analysis は集約層であり、独自のスコアリングは v3.0 では行わない。正本 §5「deterministic rule-based evaluation」）。

### 3.3 risk_level

| 条件 | risk_level |
|------|-----------|
| signal ≠ WAIT かつ absorption が存在（veto 可能性あり） | MEDIUM |
| signal = WAIT または confidence < threshold | HIGH |
| それ以外 | LOW |

### 3.4 summary

`f"{market_state}: {signal} signal at {confidence:.0%} confidence"` のような 1 行テンプレート。

### 3.5 reasons

SignalResult.reasons をそのまま引き継ぎ、absorption_result があれば `"ABSORPTION_ACTIVE"` を追加。

---

## 4. テスト（8 本）

1. STRONG_BULL（BUY + confidence 0.95）
2. BULL（BUY + confidence 0.75）
3. NEUTRAL from BUY（confidence 0.50）
4. STRONG_BEAR（SELL + confidence 0.92）
5. BEAR（SELL + confidence 0.80）
6. NEUTRAL from WAIT
7. risk_level = MEDIUM（absorption あり）
8. 決定的リプレイ

---

## 5. 完了条件

- [ ] 196 本以上 green（188 + 8）、既存 188 本無影響
- [ ] float 禁則 0 件
- [ ] 正本無変更

---

## 6. 報告

CompletionLog.md 追記 + `DeltaEngine_AIAnalysis_完了.zip` + チャット報告
