# 指示書: Repository v3.5.1 更新(CVD実装前の欠落・矛盾解消)

## 目的

CVD実装(Phase5)で Claude Code が足止めされる欠落・矛盾を解消する。作業は新規ファイルの作成のみで行う。

---

## 作業ルール(最重要・全作業に適用)

1. **既存ファイルへの加筆・修正・削除は一切禁止**。Repository の原本は読み取り専用として扱う
2. **成果物・一時ファイルはすべて `temp/updates/` に新規作成する**。Repository 内には何も書き込まない
3. 格納(新版の配置・旧版の削除・CHANGELOG への貼り付け)は人間が行う。本指示書の作業には含まれない
4. 新版ファイルの References 節は、**版数サフィックスを除いたベース名**で記載する(例: `- ErrorCodes_v3.0.md` → `- ErrorCodes`)。これは成果物1(ADR-005)で決定される新方針である
5. 本指示書に書かれていない内容変更をしない。判断に迷う点があれば作業を中断して報告する

## 成果物一覧(temp/updates/ に11ファイル)

| # | ファイル | 種別 |
|---|---------|------|
| 1 | ADR-005_Reference_Versioning_v3.0.md | 新規 |
| 2 | MarketDataSchema_v3.1.md | 新版(全文置換) |
| 3 | ParquetSchema_v3.1.md | 新版(追記あり) |
| 4 | DuckDBDDL_v3.1.md | 新版(追記あり) |
| 5 | ErrorCodes_v3.1.md | 新版(追記あり) |
| 6 | CVD_v3.1.md | 新版(追記あり) |
| 7 | DataNormalizer_v3.1.md | 新版(修正あり) |
| 8 | Database_v3.1.md | 新版(修正あり) |
| 9 | TestSpecification_v3.2.md | 新版(修正あり) |
| 10 | CHANGELOG_v3.5.1_追記分.md | 貼り付け用スニペット |
| 11 | 指示書_Phase5_CVD実装_v2.md | 実装指示書の改訂版 |

「新版」は、対応する既存ファイルの内容を**新しいファイルへコピーしたうえで**、下記の指定変更を適用して作成する。全新版ファイルに共通の変更: ヘッダの `**Version**` を新版数に更新し、References 節をルール4の版数なし方式に書き換える。

---

## 成果物1: ADR-005_Reference_Versioning_v3.0.md(全文をそのまま使用)

```markdown
# ADR-005 — Reference Versioning

**Status**: Accepted  
**Version**: v3.0

---

# Context

References sections across the repository pin exact versioned filenames (e.g., `ErrorCodes_v3.0.md`). When a document is revised, every referencing document holds a stale reference. Under the repository rule that existing files shall not be edited, fixing stale references requires re-issuing every referencing document, which cascades indefinitely.

---

# Decision

References sections shall cite documents by **base name without version suffix** (e.g., `- ErrorCodes`).

- The authoritative version of each document is determined by its filename and header in the repository, and by the CHANGELOG.
- Existing version-pinned references are NOT corrected retroactively; they are converted to base-name form when the containing document is next revised for other reasons.
- ADR identifiers (ADR-000 …) remain unchanged; only the version suffix is omitted (e.g., `- ADR-002_Module_Communication`).

---

# Rationale

- Eliminates reference-update cascades permanently.
- Preserves the no-edit rule for existing files.
- Version history remains traceable via document headers and CHANGELOG.

---

# Consequences

Positive

- Document revisions no longer force changes in referencing documents.

Trade-offs

- References no longer state which version was current at writing time; the CHANGELOG provides that history.
- Mixed styles (pinned / base-name) coexist until documents are naturally revised.

---

# Related Documents

- Documentation_Standard
- CHANGELOG.md
- ADR-001_Documentation_First
```

---

## 成果物2: MarketDataSchema_v3.1.md(全文をそのまま使用)

```markdown
# MarketDataSchema_v3.1

# Purpose

Defines the canonical market data schema used throughout the repository.
This document is the Single Source of Truth (SSOT) for market data
records.

------------------------------------------------------------------------

## Tick Record

  Field        Type              Required  Description
  ------------ ----------------- --------- ----------------------------
  event_time   datetime            Yes     Event timestamp (UTC)
  trade_time   datetime            Yes     Trade timestamp (UTC)
  trade_id     integer             Yes     Exchange trade identifier
  symbol       string              Yes     Trading instrument
  price        decimal             Yes     Executed price
  quantity     decimal             Yes     Executed quantity
  side         enum(BUY,SELL)      Yes     Aggressor side per EnumDefinitions

------------------------------------------------------------------------

## Candle Record

  Field       Type
  ----------- ---------
  bar_time    datetime
  symbol      string
  timeframe   string
  open        decimal
  high        decimal
  low         decimal
  close       decimal
  volume      decimal
  delta       decimal
  cvd         decimal

Candles are aggregated per `market.bar_timeframe` (see CVD module and
YAML configuration). Default timeframe: 1m.

------------------------------------------------------------------------

## Rules

-   UTC timestamps internally (ISO-8601).
-   Price precision follows instrument tick size.
-   Quantity and volume are decimal (fractional quantities are valid).
-   Field names align with JSONSchema, ParquetSchema, and DuckDBDDL.
-   Enumerations are defined only in EnumDefinitions.
-   Derived values are never used as source data.

Status: Phase5 Pre-Implementation Fix

## References

- JSONSchema
- ParquetSchema
- DuckDBDDL
- DataDictionary
- EnumDefinitions
```

---

## 成果物3: ParquetSchema_v3.1.md

ParquetSchema_v3.0.md をコピーし、以下を適用する。

(a) `# 5. AI Result Schema` の後、References の前に次のセクションを挿入する。

```markdown
---

# 6. Candle Schema

| Column | Type |
|---------|------|
| bar_time | TIMESTAMP |
| symbol | STRING |
| timeframe | STRING |
| open | DECIMAL(20,8) |
| high | DECIMAL(20,8) |
| low | DECIMAL(20,8) |
| close | DECIMAL(20,8) |
| volume | DECIMAL(20,8) |
| delta | DECIMAL(20,8) |
| cvd | DECIMAL(20,8) |

Partition: symbol/timeframe/year/month/day
```

(b) 既存の References 見出し番号を `# 7. References` に繰り上げる。

## 成果物4: DuckDBDDL_v3.1.md

DuckDBDDL_v3.0.md をコピーし、以下を適用する。

(a) `# 4. ai_results` の後、Index Strategy の前に次のセクションを挿入する。

```markdown
---

# 5. candles

```sql
CREATE TABLE candles (
    bar_time TIMESTAMP,
    symbol VARCHAR,
    timeframe VARCHAR,
    open DECIMAL(20,8),
    high DECIMAL(20,8),
    low DECIMAL(20,8),
    close DECIMAL(20,8),
    volume DECIMAL(20,8),
    delta DECIMAL(20,8),
    cvd DECIMAL(20,8),
    PRIMARY KEY (bar_time, symbol, timeframe)
);
```
```

(b) 以降の見出し番号を繰り上げる(Index Strategy → 6、References → 7)。Index Strategy に `- Candle queries optimized by bar_time and symbol` を1行追加する。

## 成果物5: ErrorCodes_v3.1.md

ErrorCodes_v3.0.md をコピーし、`# 4. Standard Error Codes` の表に次の2行を追加する(E3003 の下に E3004、E9001 の下に E9002)。

```text
| E3004 | Out-of-order event rejected (beyond reorder tolerance) |
| E9002 | Bounded queue overflow |
```

## 成果物6: CVD_v3.1.md

CVD_v3.0.md をコピーし、`# 5. Processing Rules` の末尾に次を追加する。

```markdown
Bar CVD is aggregated per the configured bar timeframe:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `market.bar_timeframe` | string | 1m | Candle aggregation interval for Bar CVD |

Bar boundaries are aligned to UTC clock time (e.g., 1m bars start at hh:mm:00).
```

## 成果物7: DataNormalizer_v3.1.md

DataNormalizer_v3.0.md をコピーし、以下を適用する。

- §4 Outputs の `(timestamp, instrument, price, volume, side)` を `(event_time, trade_time, trade_id, symbol, price, quantity, side)` に置換する
- §5.1 の表で、行「Timestamp」の説明はそのまま、行「Instrument」を「Symbol | Map exchange symbol to canonical symbol identifier」に、行「Volume」を「Quantity | Convert to decimal quantity per MarketDataSchema rules」に置換する

## 成果物8: Database_v3.1.md

Database_v3.0.md をコピーし、以下を適用する。

- §3 Inputs の `- Order Flow results` を `- Order Flow results (Candle records including delta / cvd)` に置換する
- §5 Storage Policy に `- Candle records are persisted per ParquetSchema Candle Schema and DuckDBDDL candles table.` を1行追加する

## 成果物9: TestSpecification_v3.2.md

TestSpecification_v3.1.md をコピーし、TV-NRM-01 を次の通り置換する。

- 入力の `sym = BTCUSDT` は変更なし。期待出力の `timestamp = 2026-01-01T00:00:01Z, instrument = BTCUSDT, price = 50000.5, volume = 3, side = BUY` を `event_time = 2026-01-01T00:00:01Z, symbol = BTCUSDT, price = 50000.5, quantity = 3, side = BUY` に置換する
- §4.6 冒頭の Fixture 説明のフィールド対応 `(epoch_ms → timestamp UTC, sym → instrument, px → price, qty → volume, aggr → side)` を `(epoch_ms → event_time UTC, sym → symbol, px → price, qty → quantity, aggr → side)` に置換する

## 成果物10: CHANGELOG_v3.5.1_追記分.md(貼り付け用・全文をそのまま使用)

```markdown
# v3.5.1 — 2026-07-08

## Added

- `00_Master/ADR/ADR-005_Reference_Versioning_v3.0.md` — References 節は版数なしのベース名で記載する方針を決定。参照更新の連鎖を解消。
- ParquetSchema / DuckDBDDL に Candle スキーマ(candles テーブル)を追加。CVD 出力の保存先欠落を解消。
- `40_Reference/ErrorCodes_v3.1.md` — E3004(順序異常拒否)・E9002(キュー溢れ)を追加。

## Changed

- `40_Reference/MarketDataSchema_v3.1.md` — Tick Record を JSONSchema / ParquetSchema / DuckDBDDL / DataDictionary と整合(event_time / symbol / quantity(DECIMAL) / side(BUY,SELL))。Candle Record に timeframe を追加。
- `30_Modules/CVD_v3.1.md` — Bar CVD の集計時間足パラメータ `market.bar_timeframe`(初期値 1m)を追加。
- `30_Modules/DataNormalizer_v3.1.md`・`50_Test/TestSpecification_v3.2.md` — 正規化出力の用語を symbol / quantity に整合。
- `30_Modules/Database_v3.1.md` — Candle 保存を Storage Policy に明記。
- 上記新版の References は ADR-005 の版数なし方式に移行。

## Removed

- 各旧版(MarketDataSchema_v3.0 / ParquetSchema_v3.0 / DuckDBDDL_v3.0 / ErrorCodes_v3.0 / CVD_v3.0 / DataNormalizer_v3.0 / Database_v3.0 / TestSpecification_v3.1)— 新版に差し替え。

---
```

## 成果物11: 指示書_Phase5_CVD実装_v2.md

00_Master に格納済みの `指示書_Phase5_CVD実装20260708.md` をコピーし、以下を適用する。

- 準拠文書表の版数を更新する: CVD_v3.1 / DataNormalizer_v3.1 / Database_v3.1 / MarketDataSchema_v3.1 / ParquetSchema_v3.1 / DuckDBDDL_v3.1 / ErrorCodes_v3.1 / TestSpecification_v3.2
- 「前提」に次の2項目を追加する:
  - `Repository の原本は docs/ にコピーとして配置し、読み取り専用として扱う。docs/ 配下への書き込み・変更は一切禁止`
  - `一時ファイルが必要な場合は temp/ フォルダにのみ書き込む。既存ファイルへの加筆・修正・削除は認めない(新規ファイルの作成のみ可)`
- 注意書き3の「今回のスコープでは未使用だが」を削除する(bar_timeframe が今回から使用されるため)。同項に `market.bar_timeframe(初期値 1m)を Config に含める` を追記する

---

## 完了条件

- temp/updates/ に成果物11件が存在する
- Repository 原本に一切の差分がない
- 各新版のヘッダ Version が指定の版数になっている
- 各新版の References 節に `_v3` を含む文字列が存在しない(検証: `grep -l "_v3" temp/updates/*.md` で References 節を目視確認)
