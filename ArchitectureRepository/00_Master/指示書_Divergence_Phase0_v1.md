この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_Divergence_Phase0_v1

**対象**: Divergence検出器 Phase 0 — 契約確立と欠陥解消（D1〜D11）
**根拠**: `00_Master/Reports/Divergence_Design_Review_v1_Complete.md`（web検証・承認済み 2026-07-19）
**対象ツリー**: `Delta_Engine_Pro4web/`
**スコープ外**: pipeline配線 / Storage永続化 / FeatureSnapshot / 品質評価（Phase 1以降）。SignalEngineへの接続は一切行わない（shadow mode方針）

---

## 1. 成果物

| 種別 | パス |
|---|---|
| 改修 | `src/orderflow/divergence.py`（全面改訂） |
| 改修 | `tests/orderflow/test_divergence.py`（全面改訂） |
| Config | `config/config.yaml` に `divergence:` セクション追加（および config 読込コードへの対応追加） |
| 正本 | `ArchitectureRepository/30_Modules/Divergence_v3.0.md` 新規 |
| 正本 | `ArchitectureRepository/00_Master/ADR/ADR-008_Divergence_Module_v3.0.md` 新規 |
| 正本 | `ArchitectureRepository/00_Master/CHANGELOG.md` 追記 |
| 正本 | `ArchitectureRepository/00_Master/CompletionLog.md` 追記 |

ADR番号について: ADR-006/007 は TradeStream_Sync_v1 で予約済みのため本件は **ADR-008** を使用する。既に ADR-008 が存在する場合は次の空き番号を使用し、報告に明記すること。

---

## 2. 型定義（`divergence.py`）

```python
from enum import Enum

class DivergenceDirection(Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"

class DivergenceKind(Enum):
    REGULAR = "REGULAR"   # HIDDEN は将来拡張として予約。本Phaseでは実装しない

@dataclass(frozen=True)
class DivergenceEvent:
    direction: DivergenceDirection
    kind: DivergenceKind            # 常に REGULAR
    symbol: str
    timeframe: str
    detected_time: datetime         # 検出を確定させた最新Candleの時刻（D8）
    pivot_time: datetime            # 直近スイング点の時刻
    previous_pivot_time: datetime   # 比較相手スイング点の時刻
    pivot_price: Decimal            # BULLISHならlow、BEARISHならhigh
    previous_pivot_price: Decimal
    pivot_cvd: Decimal
    previous_pivot_cvd: Decimal
    price_change: Decimal           # pivot_price − previous_pivot_price
    cvd_change: Decimal             # pivot_cvd − previous_pivot_cvd
    bars_between: int               # 2スイング点間のバー数（pivot間の確定足カウント差）
```

旧 `Divergence` 型は削除する（D5/D6/D8 の解消。本Phase時点で外部参照は存在しないことを確認済み。もし参照が見つかった場合は作業を止めて報告すること）。

---

## 3. 検出器仕様

### 3.1 スイング判定（D2: 同値ポリシー）

```
Swing Low : left.low  >  pivot.low  かつ right.low  ≥ pivot.low
Swing High: left.high <  pivot.high かつ right.high ≤ pivot.high
```

- 左側は厳密不等号、右側は等号許容。これにより同値が連続するクラスタでは**最初の足が代表**となる（equal_pivot_policy = first）
- 完全フラット（left も同値）はスイングにしない（左側厳密のため自然に除外される）
- `divergence.equal_pivot_policy` を config に置く。本Phaseで受理する値は `"first"` のみ。他の値は起動時バリデーションエラー（将来 `"last"` を追加可能な予約）

### 3.2 Divergence判定（D10: 明文化）

- 比較は**直近2つの同種スイング点**のみ（本Phaseの確定仕様。正本にこの旨を明記）
- BULLISH: `pivot.low < previous.low` かつ `pivot.cvd > previous.cvd`
- BEARISH: `pivot.high > previous.high` かつ `pivot.cvd < previous.cvd`
- 追加フィルタ（レビュー推奨のノイズ低減。デフォルトは無効化＝現行挙動維持）:
  - `divergence.min_price_move`（Decimal, default "0"）: `abs(price_change)` がこの値未満なら棄却、`rejected_min_price_move++`
  - `divergence.min_bar_distance`（int, default 0）: `bars_between` がこの値未満なら棄却、`rejected_min_bar_distance++`

### 3.3 入力検証（D3）

最初に受理した Candle の symbol / timeframe を基準とし、以後:

| 違反 | 挙動 |
|---|---|
| event_time が直前以下（非単調） | E3004 で棄却、`rejected_out_of_order++`、ログ |
| symbol 不一致 | E3001 で棄却、`rejected_symbol_mismatch++`、ログ |
| timeframe 不一致 | E3001 で棄却、`rejected_timeframe_mismatch++`、ログ |

棄却は例外を投げず None を返す（呼び出し側の継続性維持）。サイレント損失禁止: 全棄却は計数+ログ必須。

### 3.4 メモリ有界（D4）

- Candle保持は `deque(maxlen=3)` のみ
- スイング履歴は**直近の Low pivot 1件・High pivot 1件のみ**保持（比較に必要な最小。各pivotは (candle, bar_index) のペア）
- bar_index は受理Candleごとに増分する内部カウンタ。`bars_between` の算出に使う

### 3.5 カウンタ（D7）

`candles_in / pivots_low / pivots_high / events_detected / rejected_out_of_order / rejected_symbol_mismatch / rejected_timeframe_mismatch / rejected_min_price_move / rejected_min_bar_distance` を int 属性として公開する。

### 3.6 規律

- 全域 Decimal。`float()` 禁止。config の Decimal 値は文字列から `Decimal()` で読み込む
- 決定性: 同一入力+同一Configで常に同一のイベント列・カウンタ値
- 時刻依存・乱数依存を計算パスに入れない

---

## 4. テスト（`test_divergence.py`）

以下を最低限含めること（独自命名 `test_` 関数）:

1. BULLISH 検出（既存ケース移植。`DivergenceEvent` の全フィールド値をassert: price_change / cvd_change / bars_between / pivot_time / detected_time の分離を含む）
2. **BEARISH 検出**（D1。対称ケース、全フィールドassert）
3. 非検出: 価格LLだがCVDもLL（divergenceなし）
4. 非検出: スイング点が1つしかない
5. 同値ポリシー: 連続同値lowのクラスタで最初の足が代表になること（D2）
6. ダブルボトム（離れた同値low）: 両方pivot登録されるが price_change=0 のため REGULAR 不成立
7. 入力検証: 非単調時刻 / symbol不一致 / timeframe不一致 がそれぞれ棄却され、対応カウンタが増えること（D3）
8. メモリ有界: 多数Candle投入後も内部保持が規定サイズであること（D4）
9. min_price_move / min_bar_distance フィルタの発動と棄却カウンタ
10. 連続イベント: 複数divergenceが順に検出されるケース
11. **決定的リプレイ**: 同一Candle列を2つの detector に流し、イベント列とカウンタが完全一致（D9）

全テストで float リテラルを使用しないこと。

---

## 5. 正本文書

### 5.1 `Divergence_v3.0.md`（30_Modules、MOD-012）

既存モジュール仕様（CVD_v3.2 等）の章立てに準拠し、§2〜§3 の内容を仕様として記述する。最低限: 目的 / 入出力 / スイング判定規則（同値ポリシー含む）/ Divergence判定規則 / Config一覧 / エラー処理・カウンタ / 「検出と品質評価の分離」原則と Phase 1以降の拡張予定（FeatureSnapshot・保存・品質ランク）/ References。

### 5.2 `ADR-008_Divergence_Module_v3.0.md`

決定事項として記述する:

1. Divergence を独立モジュール（MOD-012）として追加する
2. 検出（Detector）と品質評価（Evaluator）を分離する。Phase 0 は Detector のみ
3. **out-of-sample 優位性が確認されるまで SignalEngine の重みに混ぜない**（shadow mode。設計レビュー結論の採用）
4. 保存スキーマ（divergence_events / divergence_outcomes）は Phase 1 で正本化する
5. 根拠: `00_Master/Reports/Divergence_Design_Review_v1_Complete.md`

### 5.3 CHANGELOG 追記（2エントリ）

1. `00_Master/Reports/` ディレクトリの正式新設（設計レビュー等の承認済み報告書の格納先。web検証・お館様承認済みの文書のみ格納可）
2. Divergence Phase 0（本指示書の成果）

### 5.4 CompletionLog 追記

既存フォーマットに従い、本Phase完了報告を追記する。

---

## 6. 完了条件

- [ ] D1〜D11 のうち D5 以外の全欠陥がコード+テストで解消（D5 は Event型拡充で本Phase解消、保存は Phase 1）
- [ ] 全域 Decimal（`grep -rn "float(" src/orderflow/divergence.py` が 0 件）
- [ ] 新規テスト全green、既存テストは無影響で全green
- [ ] デフォルトConfig（フィルタ無効）で旧版と同一の検出結果になること（挙動保存。同値クラスタ起因の差分のみ許容し、差分があれば報告に明記）
- [ ] 正本4文書（仕様/ADR/CHANGELOG/CompletionLog）が作成・追記済み
- [ ] SignalEngine / pipeline.py は無変更

---

## 7. 提出（3点セット）

1. CompletionLog.md への完了報告追記
2. `DeltaEngine_DIV0_完了.zip` として全体ZIPを提出
3. チャット報告: 新規テスト数 / 既存テスト数と結果 / §6 の挙動保存確認結果 / 仕様との差異（ゼロが原則）/ 発見した課題
