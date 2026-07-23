この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_A_OrderBook正本追加_v1

**対象**: Order Flow Analysis Platform — Repository 正本 3 文書への Order Book 定義追加
**参照正本(現行)**:
- ArchitectureRepository/40_Reference/MarketDataSchema_v3.1.md
- ArchitectureRepository/40_Reference/JSONSchema_v3.1.md
- ArchitectureRepository/40_Reference/YAMLReference_v3.1.md
- ArchitectureRepository/40_Reference/DataDictionary_v3.1.md (参照のみ、無変更)
- ArchitectureRepository/40_Reference/DOMReference_v3.0.md (参照のみ、無変更)
- ArchitectureRepository/40_Reference/LiquidityReference_v3.0.md (参照のみ、無変更)
- ArchitectureRepository/30_Modules/DataNormalizer_v3.2.md (参照のみ、無変更)
- ArchitectureRepository/30_Modules/DataReceiver_v3.1.md (参照のみ、無変更)
- ArchitectureRepository/30_Modules/Absorption_v3.1.md (参照のみ、無変更)

---

## 0. 前提・スコープ

これは **正本(SSOT)更新のみ**を対象とする指示書である。実装コード(`src/`)・config(`config/`)・テスト(`tests/`)は本指示書のスコープ **外**。実装は後続の「指示書 B」で扱う。

### 0.1 変更方針の例外扱い

Phase7 まで貫いてきた「docs 無変更方針」の **初めての明示的例外** として実施する。理由: M9 Absorption が要求する Order Book 入力を、指示書内の設計判断で吸収しきれる規模を超えている(入力レコードの canonical 定義そのものが正本に存在しない)ため。

CHANGELOG: **v3.6.0** 相当として記録する(YAMLReference §4 の erratum v3.5.3 とは扱いを分ける)。

### 0.2 既存 SSOT の再利用(重要)

用語・概念層は既に canonical に存在し、本指示書では **再定義せず参照のみ** とする:

- `DOMReference_v3.0.md`: Depth of Market / Bid Queue / Ask Queue / Best Bid / Best Ask / Book Imbalance
- `LiquidityReference_v3.0.md`: Resting Liquidity / Aggressive Liquidity
- `DataDictionary_v3.1.md` §4-5: bid_price / ask_price / bid_volume / ask_volume

`DataNormalizer_v3.2.md` §2-§4、`DataReceiver_v3.1.md` §4、`Absorption_v3.1.md` §3・§5.2 は既に "order book events" / "Order Book updates" を入出力として明記しているため **無変更**。本指示書は下流スキーマの空白のみを埋める。

### 0.3 永続化スキーマ

`ParquetSchema_v3.1.md` / `DuckDBDDL_v3.1.md` への Order Book テーブル追加は本指示書スコープ **外**。M11 と同じく「Absorption 実装後も生 Order Book は永続化しない、Signal のみ永続化する」方針で通す。将来永続化が必要になった時点で別指示書とする。

---

## 1. 成果物

以下 3 ファイルを編集する。バージョンは全て **v3.2** に上げる(erratum ではなく実質追加のため)。

1. `ArchitectureRepository/40_Reference/MarketDataSchema_v3.1.md` → `MarketDataSchema_v3.2.md`
2. `ArchitectureRepository/40_Reference/JSONSchema_v3.1.md` → `JSONSchema_v3.2.md`
3. `ArchitectureRepository/40_Reference/YAMLReference_v3.1.md` → `YAMLReference_v3.2.md`

**ファイル名変更(リネーム)を伴う**。旧 v3.1 ファイルは削除せず `ArchitectureRepository/temp/backup/` にバックアップコピーを残すこと(バックアップフォルダは既存)。

参照側の文書内リンクは本指示書スコープ外(参照リンクは "MarketDataSchema" のように版番号なしで書かれているため、リネームによる破損は起きない)。

---

## 2. MarketDataSchema_v3.2 への追加内容

現行の Tick Record / Candle Record セクションは **無変更**。以下 2 セクションを Candle Record と Rules の間に追加する。

### 2.1 追加セクション: Order Book Update Record

```markdown
## Order Book Update Record

  Field         Type                       Required  Description
  ------------- -------------------------- --------- -----------------------------------------
  event_time    datetime                    Yes      Event timestamp (UTC)
  symbol        string                      Yes      Trading instrument
  update_type   enum(SNAPSHOT, DIFF)        Yes      SNAPSHOT: full book replacement.
                                                    DIFF: incremental update to existing book.
  first_update_id integer                   No       Exchange-provided first sequence id in
                                                    this update (DIFF only; used for gap
                                                    detection against previous update)
  final_update_id integer                   Yes      Exchange-provided final sequence id in
                                                    this update
  bids          list<BookLevel>             Yes      Bid side price levels (see BookLevel)
  asks          list<BookLevel>             Yes      Ask side price levels (see BookLevel)

### BookLevel

  Field         Type       Required  Description
  ------------- ---------- --------- ------------------------------------------------------
  price         decimal      Yes     Price level per instrument tick size
  quantity      decimal      Yes     Resting quantity at this price level.
                                     For DIFF updates: quantity = 0 means the level was
                                     removed; quantity > 0 means the level is set to that
                                     value (not a delta).

Book state semantics:
- SNAPSHOT establishes the complete book; any pre-existing state SHALL be replaced.
- DIFF applies price levels as "set-to-value" (not delta): quantity > 0 overwrites,
  quantity = 0 deletes the level. Absent price levels are unchanged.
- SNAPSHOT SHALL precede any DIFF for a given symbol in a session (initialization order).
- Gap detection between DIFF updates uses first_update_id / final_update_id continuity
  per exchange profile; on gap detection the book SHALL be re-initialized via a fresh
  SNAPSHOT.
```

### 2.2 追加セクション: Order Book State

```markdown
## Order Book State

Order Book State is not itself a persisted record but the in-memory result of
applying Order Book Update Records in sequence. Consumers (e.g., Absorption
module per Absorption_v3.1 §5.2) query the current state at price levels of
interest to evaluate resting liquidity.

  Field         Type                       Description
  ------------- -------------------------- ----------------------------------------
  symbol        string                     Trading instrument
  last_update_id integer                   final_update_id of the last applied
                                          Order Book Update Record
  bids          map<decimal, decimal>      price → resting quantity (bid side)
  asks          map<decimal, decimal>      price → resting quantity (ask side)

Terminology (Bid Queue / Ask Queue / Best Bid / Best Ask) is defined in
DOMReference. Resting Liquidity terminology is defined in LiquidityReference.
This document does not redefine those terms.
```

### 2.3 Rules セクションへの追記

現行 Rules の末尾に 1 項追加:

```markdown
-   Order Book Update Records apply to book state per §Order Book State semantics;
    consumers SHALL NOT persist Order Book state as a canonical record.
```

### 2.4 References セクションへの追記

現行 References に以下を追加:

```markdown
- DOMReference
- LiquidityReference
```

### 2.5 Status 更新

`Status: Phase5 Pre-Implementation Fix` → `Status: v3.2 — Order Book Records added (CHANGELOG v3.6.0)`

---

## 3. JSONSchema_v3.2 への追加内容

現行 §2〜§6 は **無変更**。§6 (Candle Event) と §7 (Rules) の間に新セクション §7 として以下を追加し、既存の §7 Rules / §8 References を §8 / §9 に繰り下げる。

```markdown
---

# 7. Order Book Update Event

Snapshot form:

\`\`\`json
{
  "event_time": "2026-01-01T00:00:00.100Z",
  "symbol": "BTCUSDT",
  "update_type": "SNAPSHOT",
  "final_update_id": 987654321,
  "bids": [
    { "price": 99999.50, "quantity": 1.250 },
    { "price": 99999.00, "quantity": 3.100 }
  ],
  "asks": [
    { "price": 100000.00, "quantity": 0.800 },
    { "price": 100000.50, "quantity": 2.400 }
  ]
}
\`\`\`

Diff form:

\`\`\`json
{
  "event_time": "2026-01-01T00:00:00.200Z",
  "symbol": "BTCUSDT",
  "update_type": "DIFF",
  "first_update_id": 987654322,
  "final_update_id": 987654325,
  "bids": [
    { "price": 99999.50, "quantity": 0.000 },
    { "price": 99999.25, "quantity": 0.500 }
  ],
  "asks": [
    { "price": 100000.00, "quantity": 1.200 }
  ]
}
\`\`\`

Emitted by the Data Normalizer for each normalized order book update.
Field semantics follow MarketDataSchema Order Book Update Record. `quantity = 0`
in DIFF form indicates level removal (not a zero-sized update).

---
```

既存 §7 Rules に末尾追記:

```markdown
- Order Book Update Events with `update_type = "DIFF"` treat `quantity = 0` as
  level removal, not a zero-value update.
```

---

## 4. YAMLReference_v3.2 への追加内容

### 4.1 §4 Exchange Profiles の拡張

現行 §4 Binance サンプルの下(現行の説明文 "trade_id は Binance Futures の..." の後)に、**depth 側の field_mapping ブロック追加を含む拡張サンプル** を追記する。既存トレード側マッピングは無変更。

追記位置は現行 §4 サンプルコードブロックの直後、説明文と §5 の間。

```markdown
### 4.1 Order Book Field Mapping (optional)

Exchange profiles MAY declare an `order_book_mapping` block to enable Order Book
normalization. When absent, the Data Normalizer processes only trade events for
that profile (backward-compatible with trade-only profiles).

Sample Binance profile with Order Book mapping:

\`\`\`yaml
profile_name: binance
field_mapping:
  event_time: E
  trade_time: T
  trade_id: a
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
timestamp_format: epoch_ms
order_book_mapping:
  event_type_field: e
  event_type_snapshot: depthSnapshot
  event_type_diff: depthUpdate
  symbol_field: s
  event_time_field: E
  first_update_id_field: U
  final_update_id_field: u
  bids_field: b
  asks_field: a
  level_price_index: 0
  level_quantity_index: 1
\`\`\`

Field semantics:

| Field | Description |
|-------|-------------|
| `event_type_field` | Top-level field carrying the event type discriminator |
| `event_type_snapshot` | Value indicating a snapshot event |
| `event_type_diff` | Value indicating a diff event |
| `symbol_field` | Raw field for symbol |
| `event_time_field` | Raw field for event timestamp (uses profile-level `timestamp_format`) |
| `first_update_id_field` | Raw field for exchange first update sequence id (DIFF only, optional if absent in snapshot) |
| `final_update_id_field` | Raw field for exchange final update sequence id |
| `bids_field` | Raw field carrying the bid levels array |
| `asks_field` | Raw field carrying the ask levels array |
| `level_price_index` | Index into a level tuple where price appears (Binance-style `[price, qty]` arrays) |
| `level_quantity_index` | Index into a level tuple where quantity appears |

Note: Binance's REST depth snapshot uses `lastUpdateId` and does not carry
`event_type_field`; a profile targeting the REST snapshot path resolves the
event type externally (typically at the acquisition layer) before handing the
record to normalization. Streaming depth updates carry `e = "depthUpdate"` and
are handled by the `event_type_diff` path directly.
```

### 4.2 §2 Sample Configuration の注意書き追記

現行 §2 サンプル config は既に `"btcusdt@depth@100ms"` を `subscribe_streams` に含んでいるため、config 自体は **無変更**。ただし、depth 経路が実際に有効になるのは `normalizer.exchange_profile` が指す profile に `order_book_mapping` ブロックが存在する場合のみである旨を、§2 サンプルの直後(現行 "---" 区切りの前)に注記として 1 行追加する:

```markdown
Note: The `btcusdt@depth@100ms` subscribe stream is consumed by downstream
Order Book normalization only when the active exchange profile declares an
`order_book_mapping` block (see §4.1). Without it, depth frames are filtered
out at the acquisition layer.
```

---

## 5. CHANGELOG 記録

Repository ルート(または `ArchitectureRepository/README.md` の CHANGELOG セクション、存在する側)に以下を追記する。両方に無ければ `ArchitectureRepository/CHANGELOG.md` を新規作成する。

```markdown
## v3.6.0 — Order Book canonical records (2026-XX-XX)

**Scope**: Reference-only. No implementation, no module spec changes.

**Motivation**: M9 Absorption requires normalized Order Book input as canonical
records; DOM/Liquidity/DataDictionary terminology and DataNormalizer /
DataReceiver / Absorption input-output declarations were already canonical,
but the downstream record schema, JSON envelope, and exchange-profile mapping
were absent. This release fills only that gap.

**Changed**:
- MarketDataSchema v3.1 → v3.2: Added Order Book Update Record, BookLevel,
  Order Book State sections.
- JSONSchema v3.1 → v3.2: Added §7 Order Book Update Event (snapshot / diff
  forms).
- YAMLReference v3.1 → v3.2: Added §4.1 Order Book Field Mapping (optional
  `order_book_mapping` block for exchange profiles).

**Unchanged**:
- DataNormalizer_v3.2, DataReceiver_v3.1, Absorption_v3.1: already declared
  order book inputs/outputs; no spec change required.
- ParquetSchema, DuckDBDDL: Order Book persistence intentionally out of scope
  (M11 approach: raw not persisted).
- All 30_Modules and 20_Architecture documents.

**Follow-up**: Implementation is handled by a separate instruction ("指示書 B")
covering `binance.yaml`, `src/normalization/normalizer.py`,
`src/acquisition/binance_ws.py`, an Order Book state manager, and Absorption
detector implementation.
```

日付部分は編集時点の実日付を記入。

---

## 6. 完了条件

- [ ] `MarketDataSchema_v3.2.md` が §2.1〜§2.5 の内容を含む
- [ ] `JSONSchema_v3.2.md` が §3 の追加内容を含む
- [ ] `YAMLReference_v3.2.md` が §4.1 と §2 注記追加を含む
- [ ] 旧 v3.1 の 3 ファイルは `ArchitectureRepository/temp/backup/` にバックアップコピーされている
- [ ] 旧 v3.1 の 3 ファイルは `ArchitectureRepository/40_Reference/` から削除されている(v3.2 に置き換わる形)
- [ ] CHANGELOG v3.6.0 が記録されている
- [ ] `30_Modules/`、`20_Architecture/`、`00_Master/`、`50_Test/`、`60_Implementation/` は無変更
- [ ] `ParquetSchema_v3.1.md`、`DuckDBDDL_v3.1.md`、`DataDictionary_v3.1.md`、`DOMReference_v3.0.md`、`LiquidityReference_v3.0.md` は無変更
- [ ] `src/`、`config/`、`tests/`、`tools/` は無変更(本指示書は正本のみを対象)
- [ ] 既存 135 tests に影響がないこと(コード無変更のため自明だが確認)

---

## 7. 報告フォーマット

完了後、以下を報告すること:

- 変更した正本ファイル名(旧名 → 新名)3 件
- バックアップ保存先パス
- CHANGELOG 記録先(既存追記 or 新規作成)
- §2〜§4 の追加内容で正本文言に逸脱があれば明記
- 指示書 B(実装)の着手可否の一言
