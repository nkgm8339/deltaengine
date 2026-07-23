# 指示書: Phase5 — CVD実装

## 目的

Architecture Repository の仕様に基づき、CVDパス

```text
WebSocket → DataReceiver → DataNormalizer → CVD → Storage(Parquet / DuckDB)
```

を実装し、TestSpecification_v3.2 の該当テストベクタを全数通過させる。

---

## 前提

- **情報源は Repository(docs/ 配下)のみ**とする。仕様に書かれていないことを推測で実装しない
- Repository は `project/docs/` に配置されている(DirectoryStructure_v3.0 準拠)
- 言語は Python。ADR-003 に従い asyncio を使用する
- Repository の原本は docs/ にコピーとして配置し、読み取り専用として扱う。docs/ 配下への書き込み・変更は一切禁止
- 一時ファイルが必要な場合は temp/ フォルダにのみ書き込む。既存ファイルへの加筆・修正・削除は認めない(新規ファイルの作成のみ可)

## 準拠文書(実装前に必読)

| 分類 | 文書 |
|------|------|
| 決定事項 | ADR-002(通信方式)・ADR-003(並行性) |
| モジュール仕様 | WebSocket_v3.2 / DataReceiver_v3.1 / DataNormalizer_v3.2 / CVD_v3.2 / Database_v3.2 |
| データ定義 | MarketDataSchema_v3.1 / DataDictionary_v3.1 / EnumDefinitions_v3.1 / JSONSchema_v3.1 |
| ストレージ | ParquetSchema_v3.1 / DuckDBDDL_v3.1 |
| エラー・ログ | ErrorCodes_v3.1 / LoggingReference_v3.0 |
| 規約 | CodingGuideline_v3.0 / DirectoryStructure_v3.0 / YAMLReference_v3.1 |
| テスト | TestSpecification_v3.2 §4.1(TV-CVD)・§4.6(TV-NRM) |

## スコープ

- **含む**: 上記CVDパスの実装・単体テスト・履歴データからの決定的リプレイ
- **含まない**: SignalEngine / Footprint / Imbalance / Absorption / AI Analysis / MT5 Adapter(骨格ディレクトリの作成は可、実装はしない)

---

## 実装順序(マイルストーン)

外部接続に依存しない純粋ロジックから始め、各段でテストを通してから次へ進む。

| M | 内容 | 完了条件 |
|---|------|---------|
| M1 | プロジェクト骨格(DirectoryStructure_v3.0 のレイアウト)+ Config 読み込み(YAMLReference / ConfigurationReference 準拠。起動時バリデーション含む) | 骨格生成・不正Configで起動失敗すること |
| M2 | CVD計算器(`src/orderflow/`)。純粋関数として実装 | TV-CVD-01〜04 全通過 |
| M3 | DataNormalizer(`src/normalization/`)。取引所プロファイル・重複破棄・reorder_tolerance | TV-NRM-01〜04 全通過 |
| M4 | WebSocket・DataReceiver(`src/acquisition/`)+ ADR-002 の有界 asyncio.Queue 配線。接続ライフサイクル(ExchangeConnectorReference 準拠) | 再接続・順序検証の単体テスト通過。WebSocket_v3.2 の Config パラメータが config.yaml に反映されていること |
| M5 | Storage(`src/database/`)。ParquetSchema・DuckDBDDL 準拠のバッチ書き込み | スキーマ一致検証テスト通過。Database_v3.2 の batch_size/flush_interval が config.yaml に反映されていること |
| M6 | 統合リプレイ。YAMLReference §5 の replay モードで記録済み生データ(JSON Lines)を入力し、CVD 出力が2回の実行で完全一致すること。 | 同一入力2回実行で Parquet/DuckDB 出力が完全一致。 |

マイルストーンごとにコミットし、次へ進む前にテストが全緑であることを確認する。

---

## 注意書き(最重要)

1. **仕様変更の禁止**: 実装の都合で仕様と異なる挙動にしない。仕様に矛盾・欠落・曖昧さを見つけた場合は、**実装で回避せず、作業を止めて課題として報告する**(引継ぎ書 v3.5 §5-3 の手順: 提案 → 承認 → ADR/仕様改訂)
2. **docs/ の変更禁止**: Repository 内の文書を一切書き換えない
3. **TBD値の扱い**: `cvd_slope_ref` 等のキャリブレーション対象値は Config に置き、コードにハードコードしない。Config スキーマには予約しておく。`market.bar_timeframe`(初期値 1m)を Config に含める
4. **エラー処理**: ErrorCodes_v3.1 のコードを使用。例外の握りつぶし禁止。**サイレントなデータ損失は一切禁止**(破棄・拒否は必ずカウント+ログ)
5. **決定性**: 同一入力+同一Configで常に同一出力。時刻依存・乱数依存のロジックを計算パスに入れない
6. **並行性**: ADR-003 準拠。コルーチン間で可変状態を共有しない。データ受け渡しはキュー経由のみ
7. **依存関係の最小化**: 外部ライブラリ追加は必要最小限とし、追加時は理由を報告に含める
8. **秘密情報**: APIキー等をコード・ログ・コミットに含めない(今回は公開市場データのみで不要のはず)
9. **テストの位置**: tests/ は src/ をミラーする(DirectoryStructure_v3.0)。テストベクタの数値は TestSpecification_v3.2 の値をそのまま使用し、勝手に変えない
10. **完了報告**: 各マイルストーン完了時に「実装したファイル一覧・テスト結果・仕様との差異(ゼロが原則)・発見した課題」を報告する
11. **Exchange Profile**: config/profiles/binance.yaml を YAMLReference §4 のサンプルに従って作成する。フィールドマッピングは Binance Futures aggTrade / depth ストリームの実際のペイロードに合わせる。
12. **Replay データ**: M6 用に、M4 で受信した生データを JSON Lines で記録する仕組みを M4 に含めること(ファイルパスは config.yaml の replay.data_path)。

---

## 全体の完了条件

- TV-CVD-01〜04・TV-NRM-01〜04 が自動テストとして実装され、全通過している
- M6 の決定的リプレイが成立している
- CodingGuideline_v3.0 の命名・エラー処理・ログ規約に準拠している
- docs/ に差分がない
- 未解決の課題があれば一覧として報告されている
