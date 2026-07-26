# オーダーフロー分析システム 詳細評価報告書

作成: 2026-07-26 / 対象: `Delta_Engine_Pro4web`（branch: ui-refresh-v2）
評価前提: オーダーフロー分析の本質は「現況分析（DOM＋歩み値＋その関係性）」であり、時間足への集計は攻防の過程を潰しうる、という指示書の定義に従う。

> **後続訂正（2026-07-26）**
> 本書のコード監査結果は保存するが、Flow単体sidecarを先行稼働する提案は撤回された。
> 正本の採用境界は`PROJECT_MEMORY.md`と
> `ORDERFLOW_ENTRY_TRIGGER_DESIGN_HANDOFF_20260726.md`であり、Flow単体変換はENTRYロジックとして
> 採用禁止、LIVE起動禁止、注文0件である。以下のexecution記述は機械的prototype能力の記録であり、
> 稼働許可または推奨ではない。

---

## 0. 結論（要約）

このシステムは **「ティック粒度のオーダーフロー観測基盤 ＋ 約定フロー反応ベースの単一トリガー試作機」** である。

- **データ層は本物のオーダーフロー基盤**（生DOM＋歩み値＋清算、Decimal精度、決定論リプレイ）。時間足の統計処理ではない。
- **だが自動判断は歩み値ベースの1指標に縮退**。板の攻防はデータとして在るのに判断に使われていない。
- **統合判断層は撤去済み**で定数を返すだけ。これが評価の中心的発見。

定義（Step 4）: 現時点は「オーダーフロー分析による発注」ではなく **「約定フロー反応シグナルによる発注」**。板を見る裁量トレーダーの意思決定とはまだ差がある。

---

## 1. 決定的発見：判断層の空洞化

`src/orderflow/signal.py:33-57` と `src/ai/analysis.py:59-68` で、複合判断層が撤去されていることを確認。

```python
# signal.py — SignalEngine.evaluate() は常に固定値
def evaluate(self, ...) -> SignalResult:
    """Return fixed NO_INPUT for backward-compatible storage callers."""
    return SignalResult(_ZERO, _ZERO, "WAIT", (REASON_NO_INPUT,), None)

# analysis.py — AnalysisEngine.evaluate() も常に固定値
return AnalysisResult(..., market_state="NEUTRAL", confidence=_ZERO, ...)
```

`pipeline.py:602-608` のコメントが経緯を明示：CVD・Footprint・Imbalance は「独立ネイティブ指標」へ切り出され（`s_cvd = None; s_fp = None; s_imb = None`）、複合スコアに合流しなくなった。**cvd+fp+imb+absorption+flow を統合する層は現在存在しない。** 統合は「WebAppで人が見る」か、自動トリガーでは「行われない」。

---

## 2. Step 3：観点別評価（コード根拠付き）

### 2.1 現況分析か / 過去の要約か → 層で二分される

| 層 | モジュール | 粒度 | 性質 |
|---|---|---|---|
| 生DOM | `OrderBookStateManager` | tick（100ms差分） | **現況** |
| 吸収 | `AbsorptionDetector` | 毎tick | **現況（板×約定）** |
| テープ/大口/スイープ | `flow_detector.py` | tick | **現況** |
| 圧力vs反応 | `flow_price_response.py` | 1秒バケット窓 | near-current |
| CVD/FP/IMB | `cvd.py`/`footprint.py`/`imbalance.py` | **1m足確定** | **過去の要約** |

### 2.2 DOM的要素（板の攻防、指値の補充・消滅）

- **板の生状態は保持**：`orderbook.py:182-240`。差分の set-to-value 適用、gap検出で state リセット（`_apply_diff`）、`pu`ベースの連続性チェック、初期同期。堅牢。
- **補充の追跡あり**：`absorption.py:181-188` が `current_snap.bid_quantity_at(p) >= ws.bid_quantity_at(p)` で板厚維持を判定。**「成行がぶつかっても板が持ちこたえ補充される」という攻防を実際にモデル化。**
- **欠落**：指値の消滅・pull・spoof を独立検出する機構は **なし**。板は WebApp表示（15段）と吸収入力に使われるが、**発注トリガーには一切接続されていない**。

### 2.3 Time & Sales的要素（約定の流れ・偏り・連続性・速度）→ 最も強い

`btcusdt@trade` を1件ずつ処理。成行方向は取引所提供（推定でなく正確）。
- 偏り：`flow_price_response.py:277` `pressure_ratio = delta/total_volume`、`flow_detector.py:295` `aggression_ratio`
- 連続性：`flow_detector.py:278-288` `max_consecutive_side`、`flow_price_response.py:280-286` `persistence`
- 速度：`flow_detector.py:275` `trades_per_sec`、休止検出 `pause_ms`
- 大口/連続：`LargeTradeDetector`、`SweepDetector`（窓内複数レベル約定）

裁量トレーダーの歩み値要素をほぼ網羅。

### 2.4 時間足集計による情報喪失

- 該当するのは **CVD/FP/IMB のみ**（1m足確定）。指示書の懸念（1分デルタ+200が一方的か攻防の末か区別不能）はここに当てはまる。
- **緩和されている**：テープ・吸収・flow_response が tick/1秒で並行動作するため、攻防の過程は tick層に残る。
- **実トリガーは1m足ではなく1秒バケットのローリング窓を使う**（`flow_price_response.py`）→ 集計損失の最悪ケースは回避。ただしサブ秒解像度は無い（最小1秒）。

### 2.5 統合構造か（板＋約定＋関係性）

- **本物の統合は吸収の1箇所のみ**（板×約定）。
- 旧統合層は撤去（§1）。
- **自動トリガーは単一次元**：`flow_hfm_executor.py:487-540` は指定1窓の flow_response 状態遷移のみで side を決定。板・footprint・吸収の合流なし。

**捕捉 vs 判断接続**

| 要素 | 生データ捕捉 | 自動判断への接続 |
|---|:---:|:---:|
| DOM（攻防・補充） | ○ | ✕ |
| 指値の消滅/pull/spoof | ✕ | ✕ |
| 歩み値（偏り/速度/連続/大口/スイープ） | ○ | △（圧力のみ） |
| 板×約定の関係性（吸収） | ○ | ✕ |
| 集計指標（CVD/FP/IMB） | ○ | ✕（表示のみ） |
| 約定圧力 vs 価格反応 | ○ | ○（唯一） |

---

## 3. Step 4：定義

**素材のレベルでは「オーダーフロー分析」と呼べる**（現況のDOM＋歩み値＋吸収による関係性を扱う）。一般的な「テクニカル指標の集合」とは明確に異なる。

**現状の自動判断のレベルではまだ呼べない**（板を判断に使わない単一軸トリガー）。

### 名前をつける

> **ティック粒度のオーダーフロー観測基盤（Observation Platform）＋ 約定フロー反応ベースの単一トリガー試作機。**

**できること（境界の内側）:**
- 現況のDOM保持、清算取得、決定論的リプレイ
- 歩み値の偏り・速度・連続性・大口・スイープ・吸収（板×約定）の検出
- 約定圧力と価格反応の関係の状態化（EFFECTIVE/STALLED/TRAPPED/UNCLEAR）と forward outcome 記録
- それらを人が見るWebApp UI
- flow_response の状態遷移 → HFM(MT5) 自動発注（observe/check/live、check実機成功済み）

**できないこと（境界の外側）:**
- 複数次元（板×約定×吸収×footprint）を統合した自動判断（統合層は撤去済み）
- 指値の消滅・pull・spoof からのトリガー
- バー集計指標（CVD/FP/IMB）のトリガー化（現状は表示のみ）
- リスク管理を伴う実運用（SL/TP・spread制限・ポジション管理は未実装）

---

## 4. Step 5：発注トリガーまでのロードマップ

### A. 現状のままトリガー化できる部分（改修ほぼ不要）

1. **flow_response → flow_hfm_executorの機械的prototype経路は存在する。** 実機`order_check`は
   BUY/SELLとも成功（`retcode=0/Done`）したが、統合ENTRY GOではないためLIVE起動は禁止する。
   algorithmic tradingをONにしてFlow単体で発注してはならない。
   - 固定変換: `BUY_EFFECTIVE→BUY` / `SELL_EFFECTIVE→SELL` / `BUY_TRAPPED→SELL` / `SELL_TRAPPED→BUY`
   - 起動直後の状態は baseline 扱いで発注しない設計も既にある。
2. **outcome tracker が既に forward return を記録** → トリガー条件の事後検証・較正の土台がある。

### B. 改修が必要な部分

1. **統合判断層の再建（最重要）。** 撤去された `SignalEngine`/`AnalysisEngine` の代替として、複数指標の合流（confluence）をトリガー条件にする層を作り直す。現状は単一指標依存。
2. **DOM・吸収をトリガー入力に接続。** 現在は表示・吸収内部利用のみ。吸収結果（BUY/SELL_ABSORPTION）と板厚を、発注の確認/否定条件として flow_response と合流させる。
3. **リスク管理の実装。** SL/TP、spread 制限、ポジション/クールダウン管理、同方向連続発注の抑制。checkpoint でも「後工程」と明記の未実装領域。
4. **上位足トレンドフィルタの有効化。** `trend_state` は配線済みだが常に `None`。5m/15m集計（`higher_timeframe_candles`）は在るので接続すれば逆張り抑制に使える。

### C. 新たに追加すべき機能

1. **DOM変化の時系列イベント検出。** 大口指値の突然消滅（pull）、板の急な薄化、指値の移動。裁量トレーダーが最も見る要素で、現状ゼロ。
2. **板×約定の関係性イベントの明示化。** 「大口指値に成行がぶつかった→食い破った／反発した」を独立イベントとして検出（現状は吸収の内部条件に埋没）。
3. **合流トリガーの検証・較正ループ。** 既存の outcome 記録を使い、どの状態遷移＋確認条件が forward return と相関するかをリプレイで検証してから live 化する。
4. **サブ秒解像度の攻防メトリクス（任意）。** 現状は1秒バケットが最小。より速い攻防を捉えるなら100ms級の集計軸を追加。

### 推奨順序

後続訂正後の順序は、`B1 統合層再建` → `B2 DOM/吸収の合流接続` →
`C1/C2 板変化イベント` → `C3 較正ループ` → 期間外検証 → risk／execution接続である。
単一指標トリガーの先行稼働は行わない。

---

## 付録：確認したデータフロー

```
Binance Futures WS（@trade / @depth@100ms / @forceOrder）
  → Connector → Queue → DataReceiver（検証＋JSONL記録）→ Queue → classify_raw
    ├ trade → Normalizer（重複排除/整列/Decimal）
    │   → CVD(1m) / Footprint(1m) / Imbalance(1m)   ……バー確定・表示
    │   → Absorption(板×約定) / FlowDetector(tick) / FlowPriceResponse(1秒窓)
    ├ depth → OrderBookStateManager（板の生状態）
    └ liquidation → バッファ
  バー確定 → SignalEngine/AnalysisEngine（★撤去済み・定数返し）
  出力: Storage(parquet+duckdb) / WebApp WS配信 / MT5配信
       / 執行sidecar: FLOW_RESPONSE 状態遷移 → HFM MT5発注（唯一の自動トリガー）
```

以上。
