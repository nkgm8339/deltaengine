# WebSocketPayload仕様_v1

**Document ID**: REF-WSP-001
**Version**: v1（payload `"v": 1`）
**Status**: Fixed（実装前凍結。変更は本文書の改訂＝vインクリメントによってのみ行う）

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
- **POC**: bid+ask 合計が最大のレベルの価格（同値なら価格が高い方）
- **VAH/VAL**: POCから両側へ、合計出来高の70%に達するまで大きい側から拡張して得た価格帯の上端/下端（Value Area 70%規則。計算はサーバー側。UIは受信値を描画するのみ）
- `orderbook` は best から `depth_levels` 段。累積深度（Σ）は**UI側で単純加算表示してよい**（判定ではなく表示整形のため許可）

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
