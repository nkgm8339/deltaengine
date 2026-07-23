# 指示書: Repository v3.5.2 更新+格納(CVD実装前 最終仕様補強)

## 目的

CVD実装(Phase5 M2〜M6)で Code が足止めされる仕様の穴13件を一括解消する。

## 大原則

1. 成果物はすべて `temp/updates_v352/` に新規作成する
2. 作成完了後、**止まらずに**手順B(バックアップ→配置→削除→CHANGELOG追記)を実行する
3. ワイルドカードや一括削除の使用禁止。削除は1ファイルずつ、リストのパスを明示して実行する
4. 新版の References 節は ADR-005 準拠(版数なしベース名)で記載する
5. 新版の本文中の文書言及も ADR-005 準拠(版数なしベース名)で記載する
6. 途中で想定と異なる状態を検知したら即座に中断して報告する。自己判断で回復しない
7. 一時ファイルが必要な場合は temp/ フォルダにのみ書き込む

---

# 手順A: 新版作成(temp/updates_v352/ に10ファイル)

## 成果物1: EnumDefinitions_v3.1.md

EnumDefinitions_v3.0.md をコピーし、Version を v3.1 に更新し、以下を適用する。

(a) `# 5. SystemState` の前に次のセクションを挿入する。

```markdown
---

# 5. Timeframe

| Name | Description |
|------|-------------|
| 1s | 1 second |
| 1m | 1 minute |
| 5m | 5 minutes |
| 15m | 15 minutes |
| 1h | 1 hour |
| 4h | 4 hours |
| 1d | 1 day |
```

(b) 以降の見出し番号を繰り上げる(SystemState → 6、Ownership → 7、References → 8)。

(c) References 節を ADR-005 準拠に書き換える。

## 成果物2: JSONSchema_v3.1.md

JSONSchema_v3.0.md をコピーし、Version を v3.1 に更新し、以下を適用する。

(a) `# 4. AI Result` の後に次の2セクションを挿入する。

```markdown
---

# 5. CVD Update Event

```json
{
  "event_time": "2026-01-01T00:00:00.123Z",
  "symbol": "BTCUSDT",
  "tick_delta": 0.015,
  "tick_cvd": 1.234
}
```

Emitted by the CVD module after each normalized trade event.

---

# 6. Candle Event

```json
{
  "bar_time": "2026-01-01T00:01:00Z",
  "symbol": "BTCUSDT",
  "timeframe": "1m",
  "open": 100000.00,
  "high": 100050.00,
  "low": 99980.00,
  "close": 100020.00,
  "volume": 12.500,
  "delta": 0.800,
  "cvd": 15.300
}
```

Emitted by the CVD module at bar close. Fields align with MarketDataSchema Candle Record and ParquetSchema / DuckDBDDL Candle Schema.
```

(b) 以降の見出し番号を繰り上げる(Rules → 7、References → 8)。

(c) References 節を ADR-005 準拠に書き換える。

## 成果物3: YAMLReference_v3.1.md(全文をそのまま使用)

```markdown
# YAML Reference

**Document ID**: REF-005
**Version**: v3.1
**Status**: Draft

---

# 1. Purpose

Define the canonical configuration format for the Order Flow Analysis Platform.

---

# 2. Sample Configuration

```yaml
system:
  timezone: UTC
  log_level: INFO

market:
  symbol: BTCUSDT
  exchange: BINANCE
  bar_timeframe: 1m

websocket:
  url: "wss://fstream.binance.com/ws"
  reconnect: true
  reconnect_delay_sec: 5
  reconnect_max_retries: 0
  heartbeat_sec: 30
  connect_timeout_sec: 10
  subscribe_streams:
    - "btcusdt@aggTrade"
    - "btcusdt@depth@100ms"

normalizer:
  exchange_profile: binance
  dedup_window: 10000
  reorder_tolerance_ms: 500

queue:
  default_depth: 10000
  overflow_policy: drop_oldest_log

database:
  parquet_path: data/parquet
  duckdb_path: data/duckdb/orderflow.duckdb
  batch_size: 1000
  flush_interval_sec: 5

signal:
  enabled: false
  weight:
    cvd: 1.0
    footprint: 1.0
    imbalance: 1.0
  confidence_threshold: 0.6
  cvd_slope_ref: null
  stack_ref: 3
  absorption_veto_threshold: 0.5
  evaluation_window: 1 bar

imbalance:
  ratio_threshold: 3.0
  min_volume: null
  ratio_cap: 10.0
  stack_count: 3

absorption:
  window_sec: 10
  price_stall_ticks: 1
  volume_multiplier: 2.0
  volume_ref_bars: 20

mt5:
  enabled: false
  bind_address: 127.0.0.1
  port: 5555
  max_clients: 3
  heartbeat_interval_sec: 5
  max_buffer_messages: 1000

ai:
  enabled: false
  confidence_threshold: 0.70

replay:
  enabled: false
  data_path: null
  speed: 1.0

calibration:
  cvd_slope_ref: null
```

---

# 3. Rules

- UTF-8 encoding.
- Two-space indentation.
- snake_case keys.
- Undefined keys SHALL cause startup validation failure (E1002). No unknown keys are silently ignored.

---

# 4. Exchange Profiles

Exchange-specific field mappings are defined as separate YAML files under `config/profiles/`. The active profile is selected by `normalizer.exchange_profile`.

Sample Binance profile (`config/profiles/binance.yaml`):

```yaml
profile_name: binance
field_mapping:
  event_time: E
  trade_time: T
  trade_id: t
  symbol: s
  price: p
  quantity: q
  side_field: m
  side_rule: "m == true → SELL, m == false → BUY"
timestamp_format: epoch_ms
```

---

# 5. Replay Mode

When `replay.enabled` is true, the WebSocket module is replaced by a file reader that reads recorded trade events (one JSON object per line, conforming to JSONSchema Trade Event) from `replay.data_path`. The `replay.speed` multiplier controls playback rate (1.0 = real-time, 0 = as fast as possible). All downstream processing is identical to live mode, enabling deterministic replay.

---

# 6. References

- ConfigurationReference
- EnumDefinitions
- ErrorCodes
```

## 成果物4: WebSocket_v3.2.md

WebSocket_v3.1.md をコピーし、Version を v3.2 に更新し、以下を適用する。

(a) `# 5. Connection Lifecycle` の後に次のセクションを挿入する。

```markdown
---

# 6. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `websocket.url` | string | — | Exchange WebSocket endpoint URL |
| `websocket.reconnect` | bool | true | Enable automatic reconnection |
| `websocket.reconnect_delay_sec` | int ≥ 1 | 5 | Seconds between reconnect attempts |
| `websocket.reconnect_max_retries` | int ≥ 0 | 0 (unlimited) | Maximum reconnect attempts; 0 = unlimited |
| `websocket.heartbeat_sec` | int ≥ 1 | 30 | Heartbeat / ping interval in seconds |
| `websocket.connect_timeout_sec` | int ≥ 1 | 10 | Timeout for initial connection |
| `websocket.subscribe_streams` | list of string | — | Exchange-specific stream names to subscribe |

Missing `websocket.url` or empty `subscribe_streams` shall cause startup validation failure (E1002).
```

(b) 以降の見出し番号を繰り上げる(Error Handling → 7、Performance Targets → 8、References → 9)。

(c) References 節を ADR-005 準拠に書き換える。

## 成果物5: CVD_v3.2.md

CVD_v3.1.md をコピーし、Version を v3.2 に更新し、以下を適用する。

注意: コピー元は `CVD_v3.1.md`(v3.5.1 格納済みの最新版)。なければ CVD_v3.0.md をコピーした上で v3.1 の変更(bar_timeframe パラメータ追記)も含めて適用する。

(a) `# 4. Outputs` を次の通り置換する。

```markdown
# 4. Outputs

## 4.1 Tick CVD

Emitted after each normalized trade event (JSONSchema CVD Update Event):

- `tick_delta`: Delta of the current trade (positive for BUY, negative for SELL)
- `tick_cvd`: Running cumulative CVD since system start

Tick CVD is passed to downstream modules (Signal Engine) via asyncio.Queue per ADR-002.

## 4.2 Bar CVD (Candle)

Emitted at bar close (JSONSchema Candle Event):

- `bar_time`: UTC-aligned bar start time
- OHLC: open/high/low/close prices within the bar
- `volume`: total executed quantity within the bar
- `delta`: sum of all trade deltas within the bar (resets each bar)
- `cvd`: running cumulative CVD as of bar close (never resets)

Bar CVD is passed to Storage for persistence via asyncio.Queue per ADR-002.
```

(b) `# 5. Processing Rules` の既存内容の末尾(bar_timeframe パラメータ表の後、もしくは v3.0 ベースの場合は既存テキストの後)に次を追記する。

```markdown
## Bar Boundary Rules

- Bar boundaries are aligned to UTC clock time (e.g., 1m bars start at hh:mm:00).
- `delta` (bar delta) is the sum of all trade deltas within the bar. It resets to 0 at each bar boundary.
- `cvd` is the cumulative sum of all deltas since system start. It never resets within a session.
- At bar close, the module emits one Candle Event and begins a new bar.
- The first trade after system start opens the first bar.

## Replay Support

In replay mode (YAMLReference §5), the CVD module processes events identically to live mode. Deterministic replay requires identical input sequence and identical configuration.
```

(c) References 節を ADR-005 準拠に書き換え、JSONSchema への参照を追加する。

## 成果物6: Database_v3.2.md

Database_v3.1.md をコピーし、Version を v3.2 に更新し、以下を適用する。

注意: コピー元は `Database_v3.1.md`(v3.5.1 格納済み)。なければ Database_v3.0.md をコピーした上で v3.1 の変更(§3 Candle入力追記・§5 Candle保存追記)も含めて適用する。

(a) `# 5. Storage Policy` の後に次のセクションを挿入する。

```markdown
---

# 6. Configuration Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `database.parquet_path` | string | data/parquet | Root directory for Parquet files |
| `database.duckdb_path` | string | data/duckdb/orderflow.duckdb | DuckDB database file path |
| `database.batch_size` | int ≥ 1 | 1000 | Maximum records per write batch |
| `database.flush_interval_sec` | int ≥ 1 | 5 | Maximum seconds before flushing a partial batch |

Write is triggered by whichever condition is met first: `batch_size` records accumulated, or `flush_interval_sec` elapsed since last write. This ensures low-latency persistence without excessive I/O.
```

(b) 以降の見出し番号を繰り上げる(Error Handling → 7、Performance Targets → 8、References → 9)。

(c) References 節を ADR-005 準拠に書き換える。

## 成果物7: DataNormalizer_v3.2.md

DataNormalizer_v3.1.md をコピーし、Version を v3.2 に更新し、以下を適用する。

注意: コピー元は `DataNormalizer_v3.1.md`(v3.5.1 r2 格納済み)。なければ DataNormalizer_v3.0.md をコピーした上で v3.1 + r2 の全変更を含めて適用する。

(a) `# 5. Processing Rules` の `## 5.2 Exchange Profiles` を次の通り置換する。

```markdown
## 5.2 Exchange Profiles

Per-exchange field mappings are defined as configuration-driven exchange profiles stored as YAML files under `config/profiles/` (see YAMLReference §4 for schema and sample). The active profile is selected by `normalizer.exchange_profile` in the main configuration.

Adding an exchange requires a new profile YAML file only, not code changes to downstream modules.

Profile validation rules:
- All fields in `field_mapping` must be present.
- `timestamp_format` must be one of: `epoch_ms`, `epoch_us`, `iso8601`.
- `side_rule` must map to EnumDefinitions TradeSide values (BUY / SELL).
- Unknown profile name at startup → fail with E1002.
```

(b) References 節を ADR-005 準拠に書き換える(r2 で既にベース名化済みなら変更なし)。

## 成果物8: Sequence_v3.1.md

Sequence_v3.0.md をコピーし、Version を v3.1 に更新し、以下を適用する。

(a) `# 3. Sequence Rules` の3番目のルールを置換する。

置換前:
```text
- Each module completes before the next module begins.
```

置換後:
```text
- Pipeline stages run as concurrent coroutines connected by asyncio.Queue (ADR-002 / ADR-003). Within the Order Flow Engine, the four calculators (CVD, Footprint, Imbalance, Absorption) are called synchronously per ADR-002.
```

(b) References 節を ADR-005 準拠に書き換え、ADR-002 / ADR-003 への参照を追加する。

## 成果物9: CHANGELOG_v3.5.2_追記分.md(全文をそのまま使用)

```markdown
# v3.5.2 — 2026-07-08

## Added

- JSONSchema に CVD Update Event・Candle Event を追加(CVD出力のモジュール間契約を定義)。
- EnumDefinitions に Timeframe enum を追加(1s/1m/5m/15m/1h/4h/1d)。
- YAMLReference に全モジュールの Config パラメータを網羅したサンプル、Exchange Profile スキーマ(§4)、Replay Mode 仕様(§5)、unknown キー拒否ポリシーを追加。
- WebSocket に Config パラメータ表(URL・再接続・タイムアウト等)を追加。
- Database に Config パラメータ表(batch_size・flush_interval)を追加。
- CVD にバー境界動作規則(delta はバーごとリセット、cvd は累積)・Tick/Bar CVD の出力構造・リプレイ対応を追加。
- DataNormalizer に Exchange Profile の検証規則を追加。

## Changed

- Sequence §3 を ADR-002/003 と整合(同期直列 → asyncio コルーチン並行に修正)。
- 上記新版の References を ADR-005 準拠(版数なしベース名)に移行。

## Removed

- EnumDefinitions_v3.0 / JSONSchema_v3.0 / YAMLReference_v3.0 / WebSocket_v3.1 / CVD_v3.1 / Database_v3.1 / DataNormalizer_v3.1 / Sequence_v3.0 / 指示書_Phase5_CVD実装_v2 — 各新版に差し替え。

結果: ファイル数は変動なし(40_Reference 55 / 30_Modules 11 / ADR 6 / 50_Test 3)。Phase5 M2〜M6 の足止め要因13件を解消。

---
```

## 成果物10: 指示書_Phase5_CVD実装_v3.md

指示書_Phase5_CVD実装_v2.md をコピーし、以下を適用する。

(a) 準拠文書表の版数をすべて最新に更新する。

| 置換前 | 置換後 |
|--------|--------|
| CVD_v3.1 | CVD_v3.2 |
| DataNormalizer_v3.1 | DataNormalizer_v3.2 |
| Database_v3.1 | Database_v3.2 |
| MarketDataSchema_v3.1 | MarketDataSchema_v3.1(変更なし) |
| ParquetSchema_v3.1 | ParquetSchema_v3.1(変更なし) |
| DuckDBDDL_v3.1 | DuckDBDDL_v3.1(変更なし) |
| ErrorCodes_v3.1 | ErrorCodes_v3.1(変更なし) |
| TestSpecification_v3.2 | TestSpecification_v3.2(変更なし) |

(b) 準拠文書表に以下を追加する。

```text
| データ定義 | JSONSchema_v3.1 / EnumDefinitions_v3.1 |
| 規約 | YAMLReference_v3.1 |
```

(c) M4 の完了条件に `WebSocket_v3.2 の Config パラメータが config.yaml に反映されていること` を追記する。

(d) M5 の完了条件に `Database_v3.2 の batch_size/flush_interval が config.yaml に反映されていること` を追記する。

(e) M6 の内容を次に置換する。

```text
M6: 統合リプレイ。YAMLReference §5 の replay モードで記録済み生データ(JSON Lines)を入力し、CVD 出力が2回の実行で完全一致すること。
完了条件: 同一入力2回実行で Parquet/DuckDB 出力が完全一致。
```

(f) 注意書きに以下を追加する。

```text
11. Exchange Profile: config/profiles/binance.yaml を YAMLReference §4 のサンプルに従って作成する。フィールドマッピングは Binance Futures aggTrade / depth ストリームの実際のペイロードに合わせる。
12. Replay データ: M6 用に、M4 で受信した生データを JSON Lines で記録する仕組みを M4 に含めること(ファイルパスは config.yaml の replay.data_path)。
```

---

# 手順B: 格納(手順A完了後、止まらずに実行)

## B-0: バックアップ

1. `temp/backup/` を作成する(既にあればそのまま使用)
2. Repository 全体を `temp/backup/ArchitectureRepository_v351_backup.zip` として圧縮する
3. zip が開けること・ファイル数が Repository と一致することを確認する
4. 確認できるまで B-1 以降に進まない

## B-1: 新版の配置(コピー10件)

| # | コピー元(temp/updates_v352/) | コピー先 |
|---|------|---------|
| 1 | EnumDefinitions_v3.1.md | 40_Reference/ |
| 2 | JSONSchema_v3.1.md | 40_Reference/ |
| 3 | YAMLReference_v3.1.md | 40_Reference/ |
| 4 | WebSocket_v3.2.md | 30_Modules/ |
| 5 | CVD_v3.2.md | 30_Modules/ |
| 6 | Database_v3.2.md | 30_Modules/ |
| 7 | DataNormalizer_v3.2.md | 30_Modules/ |
| 8 | Sequence_v3.1.md | 20_Architecture/ |
| 9 | CHANGELOG_v3.5.2_追記分.md | (配置しない。B-3 で使用) |
| 10 | 指示書_Phase5_CVD実装_v3.md | 00_Master/ |

## B-2: 旧版の削除(9件・1ファイルずつ)

各削除の前に、対応する新版が B-1 で配置済みであることを確認してから削除する。

| # | 削除するファイル |
|---|----------------|
| 1 | 40_Reference/EnumDefinitions_v3.0.md |
| 2 | 40_Reference/JSONSchema_v3.0.md |
| 3 | 40_Reference/YAMLReference_v3.0.md |
| 4 | 30_Modules/WebSocket_v3.1.md |
| 5 | 30_Modules/CVD_v3.1.md |
| 6 | 30_Modules/Database_v3.1.md |
| 7 | 30_Modules/DataNormalizer_v3.1.md |
| 8 | 20_Architecture/Sequence_v3.0.md |
| 9 | 00_Master/指示書_Phase5_CVD実装_v2.md |

## B-3: CHANGELOG への追記

対象: `00_Master/CHANGELOG.md`

1. `temp/updates_v352/CHANGELOG_v3.5.2_追記分.md` の全文を読み込む
2. CHANGELOG.md の `# v3.5.1 — 2026-07-08` の**直前**に挿入する
3. `# v3.5.2` → `# v3.5.1` → `# v3.5` → `# v3.4` → `# v3.0` の順に並んでいることを確認する
4. 挿入以外、既存行を1文字も変更しない

## B-4: 検証

1. ファイル数: 30_Modules = 11 / 20_Architecture = 4 / 40_Reference = 55 / 00_Master/ADR = 6 / 50_Test = 3
2. B-2 の旧版9件が存在しないこと
3. B-1 の新版9件(#1〜#8, #10)が配置先に存在すること
4. CHANGELOG.md 先頭エントリが `# v3.5.2 — 2026-07-08` であること
5. バックアップ zip が temp/backup/ に存在すること

---

# 完了報告(必須)

- 手順A(成果物10件)の一覧と適用した変更の要約
- 手順B(コピー10・削除9・追記1)の操作結果
- B-4 の検証結果
- リスト外のファイルに一切触れていないことの宣言
- 想定外事象があればその内容と中断箇所
