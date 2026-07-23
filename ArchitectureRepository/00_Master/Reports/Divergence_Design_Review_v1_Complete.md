# CVD レギュラーダイバージェンス設計レビュー v1

対象: `Delta_Engine_Pro4web/src/orderflow/divergence.py` と `tests/orderflow/test_divergence.py`。

## 結論

現行検出器は、確定足から決定的にイベントを出す初期版として有用である。一方で品質、局面、検証結果を持たないため、SignalEngineへ固定加点したり、反対シグナルを即時に止めたりしてはならない。推奨構成は、検出・特徴量化・品質評価・売買判断を分離することである。

```text
Normalized trades → CVD Candle → SwingDetector → DivergenceDetector
                                             ↓
 Footprint / Imbalance / Absorption / Trend / OI / Liquidation
                                             ↓
                    FeatureSnapshot + DivergenceEvent
                                             ↓
                 Research Store / Quality Evaluator (shadow mode)
                                             ↓
                   validated policy only → SignalEngine
```

## 現状評価

- 3本Pivot。中央足が両隣より厳密に安い/高いときだけSwing Low/High。
- 右バー到着時に確定するため、先読みはない。検出は1バー遅延。
- 直近2つの同種Pivotについて、価格LL+CVD HLをBullish、価格HH+CVD LHをBearishと判定。
- 比較対象はすべて`Decimal`で、同一Candle列に対する結果は決定的。
- 出力は方向とPivot Candleのみで、品質・比較相手・検出時刻・期待値は含まれない。

## 欠陥と改善先

| ID | 改善 |
|---|---|
| D1 Bearishテストなし | Bearish、非検出、連続イベントの対称テストを追加 |
| D2 同値Pivot未定義 | 等値クラスタを統合し、最初/最後の代表を採るポリシーを設定化 |
| D3 入力検証なし | 時刻単調、symbol/timeframe一貫性を検証し、棄却理由を計数 |
| D4 無制限履歴 | Candleは`deque(maxlen=3)`、Pivot履歴は比較に必要な最小件数へ |
| D5 比較情報不足 | previous/pivot両方の時刻・価格・CVD、差分、bar距離をEventに保持 |
| D6 生文字列 | `DivergenceDirection` Enum |
| D7 カウンタなし | input、pivot、event、rejectedを理由別に可観測化 |
| D8 時刻混同 | `pivot_time`と`detected_time`を分離 |
| D9 Replay未証明 | 同一入力を2回流し、イベント列と統計が一致するテスト |
| D10 比較方針未文書化 | 「直近2同種Pivot比較」を初期仕様として固定 |
| D11 正本仕様なし | `Divergence_v3.0.md`と必要なADRを作成 |

追加の注意点として、CVDはセッション累積値である。品質評価にはCVD絶対値だけでなく、Pivot間CVD差、Pivot間delta合計、直近CVD slopeを使う。

## スイング方式

Phase 0では3本Pivotを残す。低遅延・決定性・実装容易性があり、現行コードの安全な基準になる。最小価格幅、最小bar間隔、等値ポリシーを設定化してノイズを減らす。ZigZagとATR Pivotは同一データで比較する候補だが、初期実装を置換しない。Adaptive/strength Pivotは十分な履歴取得後の候補とする。

価格の主比較はPivot high/low、終値差やVWAP距離は品質特徴量とする。Hidden divergenceはRegularと混在させず、別`kind`として独立検証する。

## 特徴量と品質評価

品質値は売買命令ではない。初期は説明可能な`A/B/C/UNQUALIFIED`ランクとし、設定値・特徴量バージョンとともに保存する。

| 優先度 | 特徴量 | 既存資産 |
|---|---|---|
| 必須 | 2 Pivotの価格/CVD差、bar距離、検出遅延 | Event化が必要 |
| 必須 | Footprint BUY/SELL量、delta、stacked imbalance | 実装済み |
| 必須 | Absorption方向/strength | 実装済み |
| 必須 | 15分TrendState | 実装済み |
| 推奨 | AnalysisResult market_state/risk_level | 実装済み |
| 推奨 | OI変化、Liquidation notional | 実装済み |
| 推奨 | ATR、relative volume、session | 新規 |

SignalEngineは既に方向スコアとAbsorption vetoを扱う。十分なout-of-sample優位性が確認されるまで、Divergenceは同Engineの重みに混ぜない。

## 保存設計

イベント生成時には未来情報を含めず、結果は別テーブルにする。

```sql
CREATE TABLE divergence_events (
  event_id VARCHAR PRIMARY KEY,
  detected_time TIMESTAMP NOT NULL,
  pivot_time TIMESTAMP NOT NULL,
  previous_pivot_time TIMESTAMP NOT NULL,
  symbol VARCHAR NOT NULL,
  timeframe VARCHAR NOT NULL,
  direction VARCHAR NOT NULL,
  kind VARCHAR NOT NULL,
  pivot_price DECIMAL(20,8) NOT NULL,
  previous_pivot_price DECIMAL(20,8) NOT NULL,
  pivot_cvd DECIMAL(20,8) NOT NULL,
  previous_pivot_cvd DECIMAL(20,8) NOT NULL,
  price_change DECIMAL(20,8) NOT NULL,
  cvd_change DECIMAL(20,8) NOT NULL,
  bars_between INTEGER NOT NULL,
  trend_direction VARCHAR,
  feature_version VARCHAR NOT NULL,
  quality_rank VARCHAR NOT NULL,
  rejection_reason VARCHAR
);

CREATE TABLE divergence_outcomes (
  event_id VARCHAR NOT NULL,
  horizon_bars INTEGER NOT NULL,
  close_return_bps DECIMAL(20,8),
  mfe_bps DECIMAL(20,8),
  mae_bps DECIMAL(20,8),
  PRIMARY KEY (event_id, horizon_bars)
);
```

Parquetは`symbol/timeframe/year/month/day`でパーティションし、DuckDBを分析ミラーとする。保存失敗、重複、入力棄却は既存のno-silent-loss方針で計数/ログする。

## バックテストと過学習対策

方向に沿う3/5/10本後return、MFE、MAE、複数RR到達率、勝率、Expectancy、Profit Factor、Sharpe、最大Drawdownを集計する。品質ランク別の標本数と信頼区間、Trend/Session/OI別の期待値も必須とする。

開発期間で特徴量候補を固定し、次期間をvalidation、最後の期間を一度だけout-of-sampleとする。rolling walk-forwardで再校正し、異なるボラティリティ局面で再現性を確認する。本番統合の前にshadow modeで検証する。

## 実装ロードマップ

1. **Phase 0: 契約と欠陥解消** — 正本仕様/ADR、Enum/Event型、bounded history、入力検証・統計、D1〜D11のテスト。完了条件は全欠陥が仕様とテストで追跡できること。
2. **Phase 1: イベント化と保存** — Event schema、Live/Replay共通フック、監査ログ。完了条件は同一入力で同一イベント列・保存結果になること。
3. **Phase 2: 特徴量とアウトカム** — FeatureSnapshot、3/5/10本後の結果生成、集計SQL。完了条件は未来情報なしで入力と結果を追跡できること。
4. **Phase 3: 品質ランク校正** — 説明可能なEvaluator、walk-forward、shadow UI。完了条件はランク別のout-of-sample差が安定すること。
5. **Phase 4: 限定統合** — 検証済みpolicy adapterとfeature flag。無効化時は従来SignalEngine出力へ完全復帰できること。

## 最終推奨

ダイバージェンスは「反転を命令する指標」ではなく、注文フローが価格更新を支持していない可能性を示す仮説イベントである。まず初期検出器を運用可能な契約へ直し、既存の注文フロー資産を時点固定の特徴量として保存する。out-of-sampleで優位性が再現される条件だけを、独立policy経由でSignalEngineへ導入する。
