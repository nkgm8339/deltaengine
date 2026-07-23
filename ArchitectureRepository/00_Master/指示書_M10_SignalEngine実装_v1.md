この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_M10_SignalEngine実装_v1

**対象**: Order Flow Analysis Platform — M10（SignalEngine：加重スコアリング＋Absorption veto）
**参照正本**: ArchitectureRepository/30_Modules/SignalEngine_v3.1.md
**関連**: CVD_v3.2.md / Footprint_v3.0.md / Imbalance_v3.1.md / Absorption_v3.1.md / EnumDefinitions_v3.1.md / JSONSchema_v3.1.md §3（Signal Event） / TestSpecification_v3.2.md §4.5（TV-SIG-01〜07）
**前提**: web と Code の間で「連絡文書_M10着手前確認_web→Code_v1」を突合済み（Absorption Optional化・TV-SIG-04をstubで検証・AbsorptionResult stubの配置、全て承認済み）。本指示書はその合意を反映する。
**現状確認済み**（本セッションで実ファイルを取得し確認）:
- `src/orderflow/cvd.py`: `CvdUpdate(event_time, symbol, tick_delta, tick_cvd)` / `Candle(bar_time, symbol, timeframe, open, high, low, close, volume, delta, cvd)`
- `src/orderflow/footprint.py`: `FootprintBar(bar_time, symbol, timeframe, levels: tuple[PriceLevel, ...])`
- `src/orderflow/imbalance.py`: `ImbalanceResult(bar_time, symbol, buy_imbalances, sell_imbalances, stacked_imbalances)`、`StackedImbalance(start_price, end_price, count, direction)`
- `src/config.py`: `signal` セクション（`weight: {cvd, footprint, imbalance}`, `confidence_threshold=0.6`, `stack_ref=3`, `absorption_veto_threshold=0.5`, `evaluation_window="1 bar"`）実装済み。`src/orderflow/absorption.py` は未作成（本指示書で新規作成）

---

## 0. 前提・スコープ

M7〜M9と同一の粒度。**SignalEngineの合成スコアリング・veto判定ロジックの実装とユニットテストのみ**を対象とし、pipeline.py への配線・CVD/Footprint/Imbalanceの生出力からスコアへの正規化関数・Storage永続化は本指示書のスコープ外。

理由: TestSpecification TV-SIG-01〜07 は「正規化済みスコア（-100〜+100のDecimal）」を入力として与えており、生出力（Candle.delta、FootprintBar.levels、ImbalanceResult.stacked_imbalances）からスコアへの変換ロジックを検証するテストベクタが存在しない。この変換はバー整合・evaluation_window処理を伴う配線レベルの関心事であり、正本§10（Pending Dependencies）にも `cvd_slope_ref` 較正待ちと明記されている。よって **M10は「正規化済みスコア＋Absorption結果を受け取り、合成スコア・confidence・signalを返す」部分のみを実装する**。

**Repository（docs）は無変更**。

---

## 1. 成果物

- 新規: `src/orderflow/signal.py`
- 新規: `src/orderflow/absorption.py`（**stub のみ**。`AbsorptionResult` dataclass 1つ。検出ロジックは含まない。M9で実体に置き換える）
- 新規: `tests/orderflow/test_signal.py`

`src/signal/__init__.py`（骨格スキップ用ファイル、Phase5由来）は本指示書の対象外。混同しないこと。

---

## 2. 仕様サマリ（SignalEngine_v3.1 §4 より）

```text
composite = (Σ w_i × score_i) / (Σ w_i)     ※ i は「入力されたモジュール」のみ（§4.2）
confidence = |composite| / 100
direction  = sign(composite)                 ※ +1=BUY方向, -1=SELL方向, 0=方向なし

Absorption veto:
  composite方向と逆向きのAbsorptionが strength ≥ absorption_veto_threshold で報告された場合 → 強制WAIT
```

Decision Table（§4.4）:

| 条件 | Signal |
|---|---|
| confidence ≥ threshold AND direction=+1 AND veto無し | BUY |
| confidence ≥ threshold AND direction=−1 AND veto無し | SELL |
| confidence < threshold | WAIT (LOW_CONFIDENCE) |
| veto発動 | WAIT (ABSORPTION_VETO) |
| 入力モジュールが全て欠落 | WAIT (NO_INPUT) |

---

## 3. 設計判断（正本に明記がないため、本指示書で確定する）

### 決定7: CVD/Footprint/Imbalanceスコアも Absorption と同様 Optional 入力とする

正本§4.2「A module disabled by feature flag is excluded from both numerator and denominator」および TV-SIG-06（Imbalance disabled、cvd/fpのみで合成）を実現するため、`evaluate()` の cvd_score / fp_score / imb_score はすべて **`Optional[Decimal]`** とする。`None` = そのモジュールが無効/欠落であり、合成の分子・分母から除外する（重みごと除外。0点として加算するのではない）。

全て `None` の場合、`composite=0`, `confidence=0`, `signal=WAIT`, `reason=["NO_INPUT"]` を返す（TV-SIG-07）。

### 決定8: `AbsorptionResult` の型（stub、M9で実体化）

連絡文書合意の通り、`classification` フィールドで Buy/Sell Absorption を区別する（`direction` という名前は composite の direction と紛らわしいため使わない）:

```python
@dataclass(frozen=True)
class AbsorptionResult:
    classification: str   # "BUY_ABSORPTION" | "SELL_ABSORPTION"（Absorption_v3.1 §5.3）
    strength: Decimal     # 0.0 - 1.0
```

veto条件: `composite方向=+1` かつ `classification="SELL_ABSORPTION"`、または `composite方向=−1` かつ `classification="BUY_ABSORPTION"`。かつ `strength >= absorption_veto_threshold`。

### 決定9: reasonリストは「該当する全コードの集合」とする（単一原因の排他選択ではない）

正本§6の reason codes はスコア閾値由来（`CVD_UP`/`CVD_DOWN`/`FOOTPRINT_BUY`/`FOOTPRINT_SELL`/`STACKED_IMBALANCE`、各 `|score|≥50` で該当）と、判定結果由来（`ABSORPTION_VETO`/`LOW_CONFIDENCE`/`NO_INPUT`）が混在する。TV-SIG-01の「reasons include CVD_UP, FOOTPRINT_BUY, STACKED_IMBALANCE」という書き方（"include"）はBUY確定時にもスコア由来コードが並存することを示す。よって **reasonは該当条件をすべて評価し、当てはまるコードを全て集合として返す**（排他ではない）。判定結果由来コードは以下の優先順で評価する:

1. 入力モジュールが全て `None` → `NO_INPUT`（このケースのみで確定、スコア由来コードの評価はスキップ）
2. veto条件成立 → `ABSORPTION_VETO` を追加（スコア由来コードは通常通り評価・追加する）
3. `confidence < threshold` → `LOW_CONFIDENCE` を追加
4. 最終 `signal` は「veto成立 or confidence不足」なら `WAIT`、そうでなければ `direction` の符号で `BUY`/`SELL`。`direction=0`（composite=0の完全中立）の場合も `WAIT` とする（正本に明記なし、TVでも未検証だが安全側の解釈として本指示書で確定する）

---

## 4. インターフェース設計

```python
# src/orderflow/absorption.py
@dataclass(frozen=True)
class AbsorptionResult:
    classification: str   # "BUY_ABSORPTION" | "SELL_ABSORPTION"
    strength: Decimal

# src/orderflow/signal.py
@dataclass(frozen=True)
class SignalResult:
    composite: Decimal
    confidence: Decimal
    signal: str            # "BUY" | "SELL" | "WAIT"
    reasons: tuple[str, ...]

class SignalEngine:
    def __init__(
        self,
        w_cvd: Decimal,
        w_fp: Decimal,
        w_imb: Decimal,
        confidence_threshold: Decimal,
        absorption_veto_threshold: Decimal,
    ) -> None: ...

    def evaluate(
        self,
        cvd_score: Optional[Decimal],
        fp_score: Optional[Decimal],
        imb_score: Optional[Decimal],
        absorption_result: Optional[AbsorptionResult] = None,
    ) -> SignalResult: ...
```

各 `*_score` は呼び出し側で `-100 <= score <= 100` に正規化済みの Decimal である前提とする（clamp処理は本指示書のスコープ外＝呼び出し側の責務）。Decimal演算のみ、float禁止。`_to_decimal` は `cvd.py` から再利用可。

---

## 5. テストベクタ（TestSpecification_v3.2 §4.5 準拠、必須）

fixture: `w_cvd=w_fp=w_imb=1.0`, `confidence_threshold=0.6`, `absorption_veto_threshold=0.5`

### TV-SIG-01 BUY signal
cvd +80, fp +60, imb +70。absorption_result=None。
→ composite=70, confidence=0.70, signal=BUY, reasons に CVD_UP, FOOTPRINT_BUY, STACKED_IMBALANCE を含む

### TV-SIG-02 Confidence boundary（qualify）
cvd +60, fp +60, imb +60 → composite=60, confidence=0.60, signal=BUY（≥threshold）

### TV-SIG-03 Confidence boundary（not qualify）
cvd +50, fp +50, imb +50 → composite=50, confidence=0.50, signal=WAIT, reason に LOW_CONFIDENCE

### TV-SIG-04 Absorption veto（**stub手動構築で検証、決定8参照**）
cvd +80, fp +80, imb +80（direction+1）。`AbsorptionResult(classification="SELL_ABSORPTION", strength=Decimal("1.0"))` を手動構築して渡す。
→ signal=WAIT, reasons に ABSORPTION_VETO を含む

### TV-SIG-05 SELL signal
cvd −90, fp −70, imb −80。absorption_result=None → composite=−80, confidence=0.80, signal=SELL

### TV-SIG-06 Missing input
Imbalance欠落（imb_score=None）、cvd +90, fp +90 → composite=(90+90)/2=90, confidence=0.90, signal=BUY

### TV-SIG-07 No input
cvd_score=fp_score=imb_score=None → signal=WAIT, reason=NO_INPUT

上記7件に加えて、以下を独自命名で追加すること:

- 決定7の確認: `None` のモジュールが分母（重みの合計）からも除外されること（分子だけでなく）を数値で検証する追加ケース
- 決定8の確認: veto条件が「composite方向と同方向」のAbsorptionでは発動しないこと（例: direction+1, classification="BUY_ABSORPTION" → veto無し）
- 決定8の確認: `strength < absorption_veto_threshold` では veto無し
- 決定的リプレイ（同一入力を2回 `evaluate()` して出力完全一致）

---

## 6. 完了条件

- [ ] `SignalEngine` が全て Decimal 演算（float不使用）
- [ ] TV-SIG-01〜07 をテストとして実装し green
- [ ] 追加テスト（決定7/決定8の確認、決定的リプレイ）green
- [ ] 既存 93 tests は無影響で green のまま
- [ ] `docs/`（Repository正本）は無変更
- [ ] pipeline.py・Storage・スコア正規化関数（CVD/Footprint/Imbalanceの生出力→score変換）には触れない（M10スコープ外）
- [ ] `src/orderflow/absorption.py` は stub のみ（検出ロジックを含めない）であることを確認

---

## 7. 報告フォーマット

完了後、以下を報告すること:

- 新規テスト件数（旧93件 + 新規n件）
- TV-SIG-01〜07 の実測結果
- §3 の設計判断3点（決定7/8/9）について、実装上の逸脱があれば明記
- 残タスクの整理: ①CVD/Footprint/Imbalance生出力→スコア正規化関数、②pipeline.py配線、③Absorption実体化（M9、板情報正規化含む）— それぞれ着手可否の一言
