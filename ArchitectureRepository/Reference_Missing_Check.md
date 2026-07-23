# Reference Missing Check

作成日: 2026-07-07
対象: ArchitectureRepository/40_Reference/

---

## 確認観点

Order Flow Analysis Platform として本来必要なReferenceのうち、現在存在しないものを確認する。

---

## 1. 重大度：高（プラットフォームのコアに直結）

### 1-1. AIAnalysisPipelineReference（未存在）

**必要な理由**: プロジェクト定義の関連領域に「AI Analysis Pipeline」が明記されているが、専用のReferenceが存在しない。  
JSONSchema_v3.0.md に `ai_results` 構造が定義されており、DuckDBDDL_v3.0.md にも `ai_results` テーブルが存在するにもかかわらず、AI分析の用語・概念を一元管理するSSO Tがない。

**不足している定義**:
- AI Analysis（AIによる市場分析の定義）
- Confidence Score（確信度スコアの定義・範囲）
- Market State Classification（STRONG_BULL/BULL/NEUTRAL/BEAR/STRONG_BEARの算出基準）
- Signal Generation（シグナル生成ロジックの概念定義）
- Model Inference（モデル推論の用語）
- Threshold（判定閾値の概念）

**関連する既存ファイル**: EnumDefinitions_v3.0.md（MarketState定義あり）、JSONSchema_v3.0.md（AI Result構造あり）、IndicatorDefinitions_v3.md（一部記載）

---

### 1-2. ExchangeConnectorReference（未存在）

**必要な理由**: プラットフォームはBinance等の取引所からWebSocket経由でリアルタイムデータを受信することがYAMLReference_v3.0.mdに明記されている。しかしWebSocket接続・フィード管理の用語定義がない。

**不足している定義**:
- WebSocket Connection（接続管理の概念）
- Reconnect Logic（再接続ポリシー）
- Heartbeat（接続維持の仕組み）
- Feed Subscription（データフィード購読の概念）
- Exchange（取引所の種別・分類）
- Symbol（取引銘柄の命名規則）
- Market Depth Feed（板データフィード）
- Trade Feed（約定データフィード）

**関連する既存ファイル**: YAMLReference_v3.0.md（websocket設定あり）、ErrorCodes_v3.0.md（E2xxx：Data Acquisitionエラー定義あり）、DataStreamArchitectureReference_v3.0.md（ストリーム概念定義あり）

---

## 2. 重大度：中（品質・開発プロセスに影響）

### 2-1. SignalGenerationReference（未存在）

**必要な理由**: シグナル生成はプラットフォームのコア機能であるが、シグナル生成の概念・プロセスを定義するReferenceがない。OrderFlowSignalsReferenceは「シグナルの種類」を定義しているが、「シグナル生成プロセス」は未定義。

**不足している定義**:
- Signal Condition（シグナル発生条件）
- Signal Trigger（トリガー条件）
- Signal Confirmation（シグナル確認ロジック）
- Signal Expiry（シグナル有効期限）
- Signal Combination（複合シグナルの定義）
- Confidence Threshold（確信度しきい値）

---

### 2-2. InstrumentReference（未存在）

**必要な理由**: プラットフォームは特定の取引銘柄（BTCUSDT等）を扱うが、銘柄の命名規則・分類・属性に関するReferenceがない。DataDictionary_v3.0.mdでは `symbol: STRING` と型定義のみで、銘柄の概念定義がない。

**不足している定義**:
- Symbol（銘柄識別子の形式・規則）
- Instrument（取引商品の分類：Spot/Futures/Perpetual等）
- Tick Size（最小価格変動単位）
- Contract Size（契約単位）
- Base Currency / Quote Currency（基準通貨・対象通貨）

---

### 2-3. HistoricalDataReference（未存在）

**必要な理由**: リアルタイム処理に加えて過去データの参照・分析がプラットフォームには必要だが、ヒストリカルデータの概念定義がない。DataRetentionReference_v3.0.mdは保持ポリシーを定義しているが、履歴データの活用方法は未定義。

**不足している定義**:
- Historical Data（過去データの定義と範囲）
- Backfill（過去データ補完の概念）
- Data Gap（データ欠損期間の定義）
- Replay（過去データ再現処理）
- Historical Analysis（過去データを用いた分析）

---

## 3. 重大度：低（将来的に必要になる可能性）

### 3-1. BacktestReference（未存在）

**必要な理由**: シグナル・戦略の有効性検証にバックテストが必要になるが、概念定義がない。PerformanceMetricsReference_v3.0.mdはパフォーマンス指標を定義しているが、バックテストの実行概念は未定義。

**不足している定義**:
- Backtest（バックテストの定義）
- Simulation Period（シミュレーション期間）
- Walk-Forward Analysis（ウォークフォワード分析）
- Slippage（スリッページ）
- Commission（手数料）

---

### 3-2. DataCompressionReference（未存在）

**必要な理由**: ParquetSchema_v3.0.mdでSnappy圧縮が使用されているが、圧縮に関する用語定義がない。ストレージ効率化の議論時に基準となる定義が必要。

**不足している定義**:
- Compression Format（Snappy/Zstd/Gzip等の選択基準）
- Compression Ratio（圧縮率の定義）
- Decompression Overhead（解凍コスト）

---

### 3-3. PartitioningStrategyReference（未存在）

**必要な理由**: ParquetSchema_v3.0.mdではsymbol/year/month/dayのパーティション分割が定義されているが、パーティショニング戦略の概念定義がない。

**不足している定義**:
- Partition Key（パーティションキーの選択基準）
- Partition Pruning（クエリ最適化のためのパーティション削除）
- Over-partitioning（過剰分割の弊害）

---

## 4. 不足サマリー

| No | 不足Reference | 重大度 | 既存ファイルでの部分的カバレッジ |
|----|--------------|--------|-------------------------------|
| 1 | AIAnalysisPipelineReference | 高 | JSONSchema, DuckDBDDL, EnumDefinitions |
| 2 | ExchangeConnectorReference | 高 | YAMLReference, ErrorCodes, DataStreamArchitecture |
| 3 | SignalGenerationReference | 中 | OrderFlowSignals, IndicatorDefinitions |
| 4 | InstrumentReference | 中 | DataDictionary（型定義のみ） |
| 5 | HistoricalDataReference | 中 | DataRetentionReference |
| 6 | BacktestReference | 低 | PerformanceMetricsReference |
| 7 | DataCompressionReference | 低 | ParquetSchema（方式記載のみ） |
| 8 | PartitioningStrategyReference | 低 | ParquetSchema（パーティション定義のみ） |

---

## 5. カバレッジ評価

### プロジェクト定義の関連領域とのマッピング

| 関連領域 | 主要カバーファイル | 不足 |
|---------|-----------------|------|
| Market Data | MarketDataSchema, DataDictionary, TimeAndSalesReference | ExchangeConnectorReference |
| Order Flow | OrderFlowSignals, OrderTypes, ExecutionEvents | SignalGenerationReference |
| Footprint | FootprintReference | なし |
| CVD | CVDReference, DeltaReference | なし |
| Volume Analysis | VolumeProfileReference, MarketProfileReference | なし |
| Market Structure | MarketStructureReference, AuctionMarketTheory, PriceActionReference | なし |
| Data Storage | DataStorageArchitecture, ParquetSchema, DuckDBDDL | PartitioningStrategy, DataCompression |
| Data Processing | DataProcessingArchitecture, DataPipelineReference, DataValidationReference | HistoricalDataReference |
| **AI Analysis Pipeline** | **部分的：EnumDefinitions, JSONSchema** | **AIAnalysisPipelineReference（重大不足）** |
| Repository Management | DocumentationStandard, VersioningReference | なし |
