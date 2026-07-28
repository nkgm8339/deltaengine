# WebSocketPayload仕様_v1

**Document ID**: REF-WSP-001
**Version**: v1.3（payload `"v": 1`、additive extension）
**Status**: Fixed（追加fieldは§6.1に従いpayload v1を維持する）

---

# 1. 目的と大原則

本文書は DeltaEngine WebApp の WebSocket 配信メッセージ（Payload）の**唯一の正**である。

1. **UIはPayloadのみを参照する。** UIがバックエンドの内部構造・DB・別APIを直接参照することを禁止する
2. **SignalEngineが唯一の判定主体（Source of Truth）。** signal / confidence / composite / market_state / risk_level / veto / reasons はすべて SignalEngine / AnalysisEngine の出力をそのまま搬送する。UI側での再計算・再分類・独自マッピングを禁止する
3. **versionフィールド必須。** 全メッセージは `"v": 1` を持つ。UIは自身の対応バージョンと不一致の場合、警告表示のうえ描画を継続しない
4. **数値は全て文字列。** バックエンドはDecimalを`str()`で搬送する（float禁止、ADR準拠）。UI側の`Number()`変換は描画専用として許可する
5. **UIに判定ロジックを置かない。** 派生値（confluence等）が必要な場合はサーバー側（webapp層）で本仕様の定義式に従って計算し、Payloadに含める

---

# 2. エンベロープ（全メッセージ共通）

```json
{
  "v": 1,
  "type": "<MESSAGE_TYPE>",
  "time": "2026-07-16T12:34:56.789+00:00",
  "symbol": "BTCUSDT",
  "payload": { }
}
```

| フィールド | 型 | 説明 |
|---|---|---|
| v | int | Payload仕様バージョン。本仕様は 1 |
| type | string | §3 のいずれか |
| time | string | ISO8601 UTC |
| symbol | string | 対象シンボル |
| payload | object | type別本体 |

---

# 3. メッセージタイプ一覧

| type | 頻度 | 用途 |
|---|---|---|
| HELLO | 接続時1回 | バージョン・設定の握手 |
| TICK | 約定毎 | 価格・tick CVD |
| CANDLE | バー確定毎 | Footprint / OrderBook / POC / VAH / VAL |
| BAR_UPDATE | 設定間隔毎 | 形成中バー / Footprint / Session VWAP |
| BOOK_UPDATE | 100ms sampling・状態変化時 | LIVE DOM最新同期Snapshot / Best Bid・Ask / Spread |
| TAPE_UPDATE | 100ms batch | DataNormalizerが受理した約定のTime & Sales |
| ANALYSIS | バー確定毎 | シグナル・スコア内訳・confluence・market_state |
| FLOW | 検出毎 | Detector発火イベント（リアルタイム） |
| LIQUIDATION | 発生毎 | 強制決済 |
| OI | ポーリング毎 | Open Interest |
| STATS | 5秒毎 | サーバー統計（Developer Overlay用） |

---

# 4. 各payload定義

## 4.1 HELLO

```json
{
  "server": "DeltaEngine WebApp",
  "payload_version": 1,
  "bar_timeframe": "1m",
  "signal_enabled": true
}
```

UIは `payload_version` 不一致の場合、Warningバナーを表示したうえで描画を継続する（§6.2 の段階的縮退に従う。全面停止はしない）。

## 4.2 TICK

```json
{
  "price": "63988.5",
  "quantity": "0.012",
  "side": "BUY",
  "tick_delta": "0.012",
  "tick_cvd": "15.303"
}
```

## 4.3 CANDLE

```json
{
  "bar_time": "2026-07-16T12:34:00+00:00",
  "timeframe": "1m",
  "open": "63980.0", "high": "63995.5", "low": "63975.0", "close": "63988.5",
  "volume": "12.500", "delta": "0.800", "cvd": "15.300",
  "vwap": "63984.125",
  "vwap_status": "EXACT",
  "footprint": {
    "levels": [
      { "price": "63988.5", "bid": "1.203", "ask": "2.881" }
    ],
    "poc_price": "63988.5",
    "vah_price": "63991.0",
    "val_price": "63986.0"
  },
  "orderbook": {
    "last_update_id": 123456789,
    "bids": [ { "price": "63988.0", "qty": "4.120" } ],
    "asks": [ { "price": "63989.0", "qty": "2.010" } ],
    "depth_levels": 15
  }
}
```

- `footprint.levels` は価格降順
- `vwap`は実約定`Σ(price×quantity)/Σ(quantity)`のUTC Session VWAP。値なしはnull
- `vwap_status`は`EXACT`／`PARTIAL`／null。UTC 00:00からのcoverageを確認できない表示用累積は`PARTIAL`
- `PARTIAL`は表示専用であり、Strategy EngineのSession VWAP condition材料へ使用しない
- **POC**: bid+ask 合計が最大のレベルの価格（同値なら価格が高い方）
- **VAH/VAL**: POCから両側へ、合計出来高の70%に達するまで大きい側から拡張して得た価格帯の上端/下端（Value Area 70%規則。計算はサーバー側。UIは受信値を描画するのみ）
- `orderbook` は best から `depth_levels` 段。累積深度（Σ）は**UI側で単純加算表示してよい**（判定ではなく表示整形のため許可）

### 4.3.1 BAR_UPDATE

```json
{
  "bar_time": "2026-07-16T12:34:00+00:00",
  "timeframe": "1m",
  "in_progress": true,
  "source_trade_id": 123456789,
  "source_event_time": "2026-07-16T12:34:11.123+00:00",
  "open": "63980.0", "high": "63995.5", "low": "63975.0", "close": "63988.5",
  "volume": "12.500", "delta": "0.800", "cvd": "15.300",
  "vwap": "63984.125",
  "vwap_status": "PARTIAL",
  "footprint": {
    "levels": [],
    "poc_price": null,
    "vah_price": null,
    "val_price": null
  }
}
```

- `CANDLE`と同じSession VWAP品質契約を使う
- 軽量化のため`orderbook`を含めない
- `source_trade_id`／`source_event_time`は当該形成中snapshotのsource境界

### 4.3.2 BOOK_UPDATE（v1.2 additive）

```json
{
  "event_time": "2026-07-28T10:00:00.100000+00:00",
  "projection_time": "2026-07-28T10:00:00.200000+00:00",
  "last_update_id": 123456789,
  "sync_state": "SYNCED",
  "bids": [
    { "price": "63988.0", "qty": "4.120" }
  ],
  "asks": [
    { "price": "63989.0", "qty": "2.010" }
  ],
  "depth_levels": 50,
  "best_bid": "63988.0",
  "best_ask": "63989.0",
  "spread": "1.0",
  "age_ms": 100
}
```

| field | 型 | 契約 |
|---|---|---|
| event_time | string \| null | 最新受理Snapshot／DIFFのsource time。ISO8601 UTC |
| projection_time | string | server投影時刻。ISO8601 UTC |
| last_update_id | int \| null | 投影元Order Bookの最終update ID |
| sync_state | string | 下記の列挙値 |
| bids | array | best bidから価格降順。`SYNCED`時のみ最大`depth_levels`件 |
| asks | array | best askから価格昇順。`SYNCED`時のみ最大`depth_levels`件 |
| depth_levels | int | 片側最大段数。既定50 |
| best_bid | string \| null | `SYNCED`時だけ存在するserver算出値 |
| best_ask | string \| null | `SYNCED`時だけ存在するserver算出値 |
| spread | string \| null | `best_ask - best_bid`。`SYNCED`時だけ存在 |
| age_ms | int \| null | 最新受理updateから投影までのmonotonic age |

`sync_state`:

- `SYNCED`: 初期／再同期Snapshot後の最初のDIFFまで整列済みで、両側板が正常
- `NO_SNAPSHOT`: Snapshot未取得、または初期SnapshotのDIFF整列待ち
- `RESYNCING`: gap検出後、Snapshot取得または最初のDIFF整列待ち
- `STALE`: 最終受理updateのageが設定閾値（既定2000ms）を超過
- `EMPTY`: bid／askの片側または両側が空
- `LOCKED`: best bidとbest askが同値
- `CROSSED`: best bidがbest askより高い
- `INVALID`: source時刻または価格／数量が不正

Fail-closed契約:

- `SYNCED`以外では`bids`／`asks`を必ず空配列にする。
- `SYNCED`以外では`best_bid`／`best_ask`／`spread`を必ずnullにする。
- 直前の正常数量を保持表示してはならない。
- analysis／detector／Hook／storageは全depth updateを従来どおり受理する。
  `BOOK_UPDATE`は同一stateをread-onlyで投影し、analysis updateを間引かない。
- serverは100msごとに最新状態だけをsampleし、状態fingerprintが変わった場合だけ送る。
  全Snapshotをbrowser向けqueueへ積まない。
- serverは接続ごとに最新の`BOOK_UPDATE` 1件だけを再送する。
- replay modeではlive `BOOK_UPDATE` projectorを起動しない。

## 4.4 ANALYSIS

```json
{
  "signal": "BUY",
  "confidence": "0.84",
  "composite": "62.5",
  "scores": {
    "cvd": "61.0",
    "footprint": "48.2",
    "imbalance": "91.0",
    "absorption": "0.83",
    "flow": "0.78"
  },
  "confluence": {
    "cvd": true, "footprint": true, "imbalance": true,
    "absorption": false, "flow": true, "count": 4
  },
  "market_state": "BULL",
  "risk_level": "LOW",
  "veto": "NONE",
  "reasons": ["CVD_POSITIVE", "STACKED_BUY_IMBALANCE"],
  "expected_rr": null
}
```

**搬送規則（Source of Truth）:**

| フィールド | 出所 | UI規則 |
|---|---|---|
| signal | SignalEngine（BUY / SELL / WAIT） | **受信文字列をそのまま表示**。LONG/SHORT/AVOID等への読み替え禁止（4値化は将来のSignalEngine拡張ADR） |
| confidence / composite | SignalEngine | そのまま表示 |
| scores.cvd/footprint/imbalance | SignalEngine M11 スコア（−100〜+100）。未較正時 null | null は「—」表示 |
| scores.absorption | AbsorptionResult.strength（0〜1）。非活性時 null | null は「—」表示 |
| scores.flow | **派生値（informational）**: 直近60秒のFLOWイベントstrength加重平均（サーバー計算、§5.1）。compositeには不参加 | そのまま表示 |
| confluence | サーバー計算（§5.2 の固定式） | そのまま表示 |
| market_state | AnalysisEngine（STRONG_BULL/BULL/NEUTRAL/BEAR/STRONG_BEAR） | **受信文字列をそのまま表示**。UI側列挙・マッピング禁止 |
| risk_level | AnalysisEngine（LOW/MEDIUM/HIGH） | そのまま表示 |
| veto | SignalEngineのveto理由。無しは "NONE"。v1対象: ABSORPTION_VETO / ABNORMAL_BOOK / EXTREME_DELTA / MARKET_HALT / DATA_ERROR のうちSignalEngineが現に出力するもの | そのまま表示 |
| expected_rr | **v1では常に null**（SignalEngine未実装。将来ADR） | 「—」表示。UI側推定計算の禁止 |

## 4.5 FLOW

```json
{
  "event_time": "2026-07-16T12:34:11.123+00:00",
  "category": "IMBALANCE",
  "side": "BUY",
  "strength": "0.91",
  "detector": "ImbalanceDetector",
  "detail": "stacked_count=4"
}
```

- **v1のcategory**: `IMBALANCE`（stacked検出時）/ `ABSORPTION`（検出時）の2種のみ（既存Detectorに限定）
- `DELTA / EXHAUSTION / ICEBERG` は**予約値**。対応Detector実装後の仕様改訂（v2）で追加する。UIは未知categoryを白色・"UNKNOWN"バッジで描画してよい（前方互換）
- strength: Imbalance = min(stacked_count / stack_ref, 1)、Absorption = AbsorptionResult.strength

## 4.6 LIQUIDATION

```json
{ "side": "SELL", "price": "63970.0", "quantity": "3.210" }
```

## 4.7 OI

```json
{
  "open_interest": "84213.550",
  "prev": "84190.120",
  "change": "23.430",
  "change_pct": "0.027829...",
  "source_time": "2026-07-22T08:13:29.405000+00:00",
  "received_time": "2026-07-22T08:13:30+00:00",
  "source": "BINANCE_USDM",
  "poll_interval_sec": 10
}
```

- `open_interest`はBinance USD-M Futures `GET /fapi/v1/openInterest` の文字列値。
- envelope `time`と `source_time`はBinance responseの `time`をUTCへ変換したもの。
- `received_time`はローカル受信時刻。source freshnessの表示にのみ使う。
- `change`と `change_pct`は直前の正常取得値との差。初回または比較不能時はnull。
- 取得失敗、非正値、非有限値、symbol不一致ではOI messageを配信しない。
- リプレイ中に現在時刻のライブOIを混在させない。

## 4.8 STATS

```json
{
  "tick_per_sec": "142", "queue_depth": "3", "dropped": "0",
  "ws_upstream": "OPEN", "clients": "1",
  "cpu_percent": "12.0", "ram_mb": "486"
}
```

FPSはクライアント計測（描画性能のため。判定に不使用）。LATENCYは `TICK.time` と受信時刻の差をUIが表示用に計算してよい。

## 4.9 TAPE_UPDATE（v1.3 additive）

```json
{
  "batch_time": "2026-07-28T10:00:00.200000+00:00",
  "stream_id": "3fd6b05b-51bb-43ca-bab1-6760433dd905",
  "first_sequence": 1201,
  "last_sequence": 1202,
  "accepted_count": 2,
  "dropped_count": 0,
  "trades": [
    {
      "sequence": 1201,
      "trade_id": 987654321,
      "event_time": "2026-07-28T10:00:00.123000+00:00",
      "price": "63988.0",
      "quantity": "0.125",
      "notional": "7998.5000",
      "side": "BUY"
    },
    {
      "sequence": 1202,
      "trade_id": 987654322,
      "event_time": "2026-07-28T10:00:00.180000+00:00",
      "price": "63987.5",
      "quantity": "0.080",
      "notional": "5119.0000",
      "side": "SELL"
    }
  ]
}
```

| field | 型 | 契約 |
|---|---|---|
| batch_time | string | serverがbatchを送信対象として確定した時刻。ISO8601 UTC |
| stream_id | string | process／replay session単位のUUID |
| first_sequence | int | batch先頭のstream-local sequence |
| last_sequence | int | batch末尾のstream-local sequence |
| accepted_count | int | 当該messageの`trades`件数。`accepted_count == trades.length` |
| dropped_count | int | 前回の正常送信以降にoverflow／送信失敗で欠落した件数 |
| trades | array | sequence昇順。1 message最大250件 |

`trades`要素:

| field | 型 | 契約 |
|---|---|---|
| sequence | int | `stream_id`内で1から単調増加する配信順序 |
| trade_id | int | source trade ID。履歴との重複排除keyは`(symbol, trade_id)` |
| event_time | string | source約定時刻。ISO8601 UTC |
| price | string | 約定価格。Decimal文字列 |
| quantity | string | 約定数量。Decimal文字列 |
| notional | string | `price × quantity`のDecimal文字列。float再計算禁止 |
| side | string | `BUY`または`SELL` |

生成・batch契約:

- sourceはDataNormalizerが正常受理した約定だけとする。duplicate／invalidはsequenceを消費しない。
- `TICK`、latest-value pump、Flow/CVDの後段出力からTapeを再構成してはならない。
- 既定100ms間隔、1 message最大250件、pending上限10,000件とする。
- message内のsequenceは連続し、`first_sequence`／`last_sequence`と一致する。
- overflow時は古いpending約定からdropする。割り当て済みsequenceを詰め直さず、
  次の正常送信の`dropped_count`とsequence gapで欠落を明示する。
- `accepted = sent + pending + in_flight + dropped`を常時成立させ、
  overflow、送信失敗、accounting不一致はSTATS／healthへ公開する。
- `stream_id`はprocess／replay sessionごとに新規生成し、sequenceは1から開始する。
  同一processへのWebSocket再接続では同じstreamを継続し、新しいstreamではclientも
  gap判定状態をリセットする。
- Tape batchは再接続用cacheへ保存しない。clientは履歴APIで初期化後、
  `(symbol, trade_id)`でliveとの重複を排除する。
- replay modeではreplay accepted tradeだけを流し、現在時刻のlive tapeを混在させない。

履歴API:

- `GET /api/history/time-sales`
- queryは`symbol`、`limit`（1〜500）、`before`（ISO8601 UTC）、
  `before_trade_id`（同時刻を安全に辿る複合cursor）を受ける。
- responseの`trades`は古い順で、`next_before`と`next_before_trade_id`を返す。
- price／quantity／notionalはDecimal文字列、sideは`BUY`／`SELL`、
  event timeはUTCとする。
- liveとの接続境界では`(symbol, trade_id)`を重複排除keyとする。

---

# 5. サーバー側派生値の定義（固定式）

## 5.1 scores.flow

```
直近 flow_window_sec（デフォルト60）内の FLOW イベントについて
flow = Σ(strength_i × w_i) / Σ(w_i),  w_i = 0.5^(経過秒_i / 30)
イベント0件なら null
```

informationalであり、SignalEngineのcomposite・signalに一切影響しない。

## 5.2 confluence

```
cvd:        scores.cvd が non-null かつ signal方向に |値| ≥ 40
footprint:  同上
imbalance:  同上
absorption: scores.absorption non-null かつ ≥ 0.5 かつ vetoがsignal方向を妨げない
flow:       scores.flow non-null かつ ≥ 0.5
count:      上記trueの数（0〜5）
signal が WAIT のとき全て false / count 0
```

閾値（40 / 0.5）は config `webapp.confluence` に置く。本式の変更は本仕様の改訂として扱う。

---

# 6. Version Policy（互換性規則）

## 6.1 変更の分類

| 変更内容 | 可否 | version |
|---|---|---|
| 新規フィールド追加 | **OK** | v据え置き（v1.x として本文書に追記） |
| 新規メッセージtype追加 | **OK** | v据え置き（同上） |
| category等の列挙値追加 | **OK** | v据え置き（UIは未知値を前方互換描画） |
| 既存フィールド削除 | **NG** | Breaking → v2 |
| 型変更 | **NG** | Breaking → v2 |
| 名称変更 | **NG** | Breaking → v2 |
| 意味変更（同名で別の値） | **NG** | Breaking → v2 |

## 6.2 UIのversion不一致時の動作（段階的縮退）

```
version不一致を検知
  ↓
Warning表示（画面上部バナー。描画は止めない）
  ↓
可能な限り描画を継続（未知フィールド無視・未知type破棄）
  ↓
必須フィールド欠落のメッセージのみスキップ（該当メッセージ単位。画面全体は停止しない）
```

全面停止は行わない。運用上、サーバーが先行更新されてもUIは劣化描画で生存する。

## 6.3 UI側の前方互換義務

- 未知フィールドを無視する
- 未知typeを破棄する
- 未知の列挙値（FLOW category等）は中立表示（白 / UNKNOWN）で描画する

---

# Appendix A. Backward Compatibility

| 遷移 | 互換性 | UI対応 |
|---|---|---|
| v1 → v1.x | **互換あり**（追加のみ可） | 更新不要。新フィールドは未対応なら無視される |
| v1 → v2 | **互換なし**（Breaking Change） | UI更新必須。移行期間中はWarning表示のもと劣化描画 |
| Deprecated フィールド | 廃止予定を本文書に明記 | **最低2バージョン維持**してから削除する |

Breaking Changeを行う場合は、本文書の改訂＋ADR記録＋HELLOでの通知を必須とする。

---

# 7. References

- SignalEngine / AIAnalysis / Imbalance / Absorption / JSONSchema（版数なしベース名、ADR-005準拠）
- UI仕様書_CommandCenter
- 指示書_WebApp_v3
