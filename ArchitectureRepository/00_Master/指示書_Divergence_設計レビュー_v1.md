この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_Divergence_設計レビュー_v1

**対象**: CVDレギュラーダイバージェンス検出システム — 設計レビューおよび改善設計
**レビュー対象コード**: `Delta_Engine_Pro4web/src/orderflow/divergence.py` / `tests/orderflow/test_divergence.py`（web検証済み: 2026-07-19）
**関連既存資産**: CVD / Footprint / Imbalance / Absorption / SignalEngine / AnalysisResult（すべて実装済み・221 tests passed）
**成果物**: Markdownレビュー文書のみ。**コード修正は行わない**

---

## 1. 目的

実装済みの初期版ダイバージェンス検出器を、単なるイベント検出器から

> **市場状態を評価する中核エンジン**

へ発展させるための設計方針を確立する。オーダーフロー分析・裁量トレード・Pythonシステム設計の専門家の観点から総合レビューを実施し、設計・分析・改善提案を成果物として提出すること。

---

## 2. 現状仕様（web検証済みの事実。自己申告ではなくコード実態）

### データ

- Binance Futures BTCUSDT / 1分確定足
- 入力: `Candle`（OHLC, volume, delta, cvd。全Decimal）

### スイング判定

3本Pivot。厳密不等号のみ。

```
Swing Low : Low[i-1] > Low[i] かつ Low[i+1] > Low[i]
Swing High: High[i-1] < High[i] かつ High[i+1] < High[i]
```

確定は右バー到着時（1バー遅延）。

### Divergence判定

直近2つの同種スイング点の比較のみ。

```
Bullish: Price LL かつ CVD HL（pivot.low < prev.low かつ pivot.cvd > prev.cvd）
Bearish: Price HH かつ CVD LH（pivot.high > prev.high かつ pivot.cvd < prev.cvd）
```

出力は `Divergence(direction: str, candle: Candle)` のみ。品質・信頼性・期待値・優位性の評価は一切ない。

---

## 3. 確認済み欠陥一覧（レビューで必ず個別に扱うこと）

| # | 欠陥 | 深刻度 |
|---|------|--------|
| D1 | Bearish側のテストが存在しない | 高 |
| D2 | 同値高値・安値（厳密不等号のためダブルボトム/トップがpivot落ち）の扱いが未定義 | 高 |
| D3 | 時系列順・symbol・timeframeの入力検証がない | 中 |
| D4 | `_candles` / `_lows` / `_highs` が無制限に伸びる（`_candles` は直近3本しか参照しないにも関わらず全保持。ライブ運用でメモリリーク） | 高 |
| D5 | `Divergence` 結果に前回スイング点・両スイング間の距離・CVD差分が含まれない。品質評価と検証ログへの発展に決定的に不足 | 最高 |
| D6 | `direction` が生文字列。Enum未使用 | 低 |
| D7 | 検出・棄却カウンタが皆無（no silent loss原則違反） | 中 |
| D8 | 検出タイミングの曖昧さ: 返却 `candle` はpivotだが検出時刻は右バー。タイムスタンプ混同リスク | 中 |
| D9 | 決定的リプレイテストなし | 中 |
| D10 | 連続同方向pivotの比較が直近2点のみである設計判断が明文化されていない | 低 |
| D11 | 正本Repositoryにモジュール仕様が存在しない（仕様書化・ADRが未整備） | 最高 |

各欠陥について「改善設計のどこで解消されるか」を明示すること。

---

## 4. レビュー対象

### A. スイング判定

- 3本Pivotの長所・欠点・ノイズ発生要因・遅延・誤検出を評価すること
- 比較対象: Fractal / ZigZag / ATR Pivot / Volatility Pivot / Adaptive Pivot / Swing Strength方式
- 各方式について長所・短所・リアルタイム性・実装難易度・オーダーフローとの相性を比較すること
- D2（同値の扱い）への各方式の耐性を含めること
- 最後に推奨方式を示すこと

### B. Divergence定義

- 現在の LL/HL 比較だけで十分か評価すること
- 価格側の比較対象: 終値 / 高値安値 / Pivot / VWAP
- CVD側の比較対象: 終値 / Pivot / Slope / Momentum
- Hidden Divergence（トレンド継続型）を検出対象に含めるべきかも評価すること

### C. 品質評価（最重要）

- 「検出」と「品質評価」を分離すべきか検討すること
- 品質評価で利用可能な特徴量を洗い出すこと。**重要: 以下は既存実装済みモジュールであり、仮想の候補ではない。既存資産の活用を最優先で検討すること**
  - Footprint（価格レベル別BUY/SELL出来高）
  - Imbalance（対角比較 / Stacked）
  - Absorption（吸収検出、strength付き）
  - SignalEngine（加重composite / confidence / veto）
  - AnalysisResult（market_state 5段階 / risk_level 3段階）
  - Open Interest（OIポーリング実装済み）/ Liquidation（@forceOrder実装済み）
- 外部特徴量候補（ATR / ボラティリティ / EMA・VWAP位置 / Relative Volume / Funding / Time of Day / Session）も評価すること
- 各特徴量について重要度・実装難易度・期待効果を評価し、優先順位を提示すること

### D. アーキテクチャ

以下の構成を評価し、改善案を提案すること。既存 pipeline.py（Replay/Live両対応）との統合点を明示すること。

```
Market Data → Swing Detector → Divergence Detector → Feature Generator
→ Quality Evaluator → Signal Engine → Trade Decision
```

特に「既存SignalEngineへの入力として組み込むか、並列の独立評価軸とするか」を論じること。

### E. 保存データ

- 将来のバックテスト・統計分析・AI学習を考慮し、検出イベントとして保存すべきデータ項目を一覧化すること
- 必須 / 推奨 / 不要に分類すること
- D5（前回スイング情報の欠落）の解消をこの設計に含めること
- DuckDB + Parquet前提でスキーマ案（DDLレベル）まで提示すること

### F. バックテスト

- 評価項目: 3/5/10本後リターン / MFE / MAE / RR / TP率 / SL率 / Profit Factor / Expectancy / Sharpe / Drawdown
- オーダーフロー分析特有の評価項目があれば追加提案すること
- 既存の決定的リプレイ基盤（同一入力2回で完全一致）を活用した検証設計とすること

### G. 過学習対策

- Walk Forward / Rolling Validation / Out of Sample / Regime Test について推奨すること
- 特徴量追加時の検証フローを提示すること

### H. 実装ロードマップ

- 現状（Detector初期版まで実装済み）から最も失敗しにくい実装順序を提示すること
- 各Phaseについて目的・成果物・完了条件を書くこと
- **Phase 0として「§3 欠陥一覧の解消 + 正本仕様書化（Divergence_v3.0.md + 必要ならADR）」を必ず含めること**（D11の解消。DeltaEngineの正規開発サイクルへの編入が前提）

---

## 5. 制約

- Python / asyncio単一イベントループ（ADR-003）前提
- **Decimal全域使用。float禁止**。改善設計の擬似コード・データ構造もこれに従うこと
- リアルタイム処理前提（メモリ有界であること。D4の解消）
- 決定性: 同一入力+同一Configで常に同一出力。時刻依存・乱数依存を計算パスに入れないこと
- Binance Futuresデータ前提
- 裁量トレーダーにも説明可能な構造とすること
- 固定ルールではなく市場状態に応じた適応型設計を優先すること
- 実装よりも設計品質を優先すること
- サイレントなデータ損失禁止（棄却は必ずカウント+ログ。D7の解消）

---

## 6. 成果物

以下をMarkdownで提出すること。

1. 現状評価（§3 欠陥一覧への言及を含む）
2. 問題点一覧（§3 に追加発見があれば追記）
3. 推奨アーキテクチャ（既存pipeline統合点を含む）
4. 推奨特徴量一覧（既存資産/新規の区分・優先順位付き）
5. 品質評価モデル
6. 保存データ設計（DDL案含む）
7. バックテスト設計
8. 検証方法（過学習対策含む）
9. 実装ロードマップ（Phase 0 = 欠陥解消+仕様書化から開始）
10. 最終推奨構成

可能な範囲で擬似コード・データ構造・クラス構成・特徴量テーブル・フローチャートまで提案すること。

---

## 7. 最重要事項

表面的な一般論ではなく、以下の観点からレビューすること。

- オーダーフロー分析 / CVD / Footprint
- プロトレーダーの裁量
- 実運用（ライブ・メモリ・決定性）
- Pythonシステム設計
- **DeltaEngineの既存資産（4計算器 + SignalEngine + 永続化基盤）との整合**

一般論のみのセクションは不合格として扱う。
