# UI仕様書_CommandCenter_v1

**Document ID**: REF-UI-001
**Version**: v1（デザインモック delta_command_center_v3_3 準拠）
**Status**: Historical — Superseded by v2 on 2026-07-22
**Current specification**: [`UI_Spec_CommandCenter_v2.md`](UI_Spec_CommandCenter_v2.md)
**参照**: WebSocketPayload仕様_v1（UIの唯一のデータ源）

> この文書は旧decision UIの設計経緯を残すための履歴資料であり、現行UIの実装判断には使用しない。
> 現行の正本は `UI_Spec_CommandCenter_v2.md` とする。

---

# 0. ミッション（本UIの存在理由）

> **本UIは「トレーダーが3秒以内に状況を把握し、売買判断できるコマンドセンター」である。データ表示ツールではない。**

全ての設計判断はこの一文に従属する。

# 0.1 三原則

1. **固定値・ダミー値禁止**: 画面上の全数値はPayload由来。Payloadに無い値は「—」を表示し、捏造しない
2. **UI ≠ ドメインモデル**: signal / market_state / risk_level / veto はPayloadの文字列をそのまま描画する。UI側の列挙・再分類・独自マッピングを禁止する
3. **判定ロジック禁止**: UIが行ってよい計算は表示整形のみ（Number変換、バー幅比率、累積深度Σの単純加算、LATENCY差分、FPS計測）。売買判断に関わる一切の計算はSignalEngine（Payload）の値を使う

---

# 1. 全体レイアウト

```
┌─────────────────────────────────────────────────────────────┐
│ TOP BAR: SYMBOL PRICE ▲% │ SIGNAL CONF │ ATR SPREAD LAT FPS │ LIVE 🐛 │
├────────────┬──────────────────────────────┬─────────────────┤
│ ORDER BOOK │ FOOTPRINT（主役・約58%）       │ MARKET STATE    │
│ (heatmap + │  Price/Bid×Ask/Delta/SIG      │ CONFLUENCE      │
│  Σ累積)     │  POC / VAH / VAL              │ SIGNAL — WHY    │
│            ├──────────────────────────────┤  (検出器スコア    │
│            │ FLOW EVENTS（タイムライン）     │   →Composite)   │
├────────────┴──────────────────────────────┴─────────────────┤
│ CVD+Δ / VOLUME / OI / LIQUIDATION（タブ、CVD+Δがデフォルト）   │
└─────────────────────────────────────────────────────────────┘
＋ 右下: ALERTS履歴（常設） ＋ 左下: DEVELOPER OVERLAY（デフォルト非表示）
＋ 上部中央: 🚨トースト（3秒）
```

カラム比: 左 256px 固定 / 中央 flex（全体の約55〜60%）/ 右 320px 固定。

---

# 2. カラーシステム（厳守）

| 色 | HEX | 意味（唯一） |
|---|---|---|
| 緑 | #00E676 | 買い |
| 赤 | #FF4D4D | 売り |
| 黄 | #FFC400 | 注意（POC/VAH/VAL・veto・warn） |
| 灰 | #5B6472 | 無効・WAIT・null |
| 紫 | #9C7DFF | 情報（Composite・OI・開発系） |
| 背景 | #0A0D12 / パネル #11161F / 罫線 #1E2735 | |

**FLOWカテゴリ色（バッジ専用の別名前空間。上表と混同しない）:**
DELTA=#FF4D4D / IMBALANCE=#4DA3FF / ABSORPTION=#9C7DFF / EXHAUSTION=#FFC400 / ICEBERG=#E8EDF4 / 未知=白+UNKNOWN。
BUY/SELL方向は常に緑/赤の文字で併記し、カテゴリバッジと分離する。

フォント: 等幅（tabular-nums）。

---

# 3. パネル仕様

## 3.1 TOP BAR（データ源: TICK / ANALYSIS / STATS）

SYMBOL・現在価格（直前ティック比で緑/赤）・変化率、**SIGNALチップ（Payload `signal` 文字列そのまま＋confidence%）**、ATR(14)※、SPREAD（book best差）、LATENCY（<60ms緑/<120ms黄/以上赤）、FPS、LIVE接続バッジ、🐛トグル。
※ATRはv1ではPayloadに無いため「—」。

## 3.2 ORDER BOOK（データ源: CANDLE.orderbook）

- ask上段（降順）/ MID / bid下段。各行: price / qty / **Σ累積**
- **Bookmap様式**: 行背景の濃度が qty/max に比例（バーではなく面）。最厚帯は文字を白反転
- 累積深度は外周からの下線/上線として重畳

## 3.3 FOOTPRINT（主役。データ源: CANDLE.footprint）

列: PRICE / BID（右詰め数値＋左向きバー赤）/ ×分離 / ASK（バー緑＋数値）/ DELTA（ask−bid、符号色）/ SIG。
- **POC**: 黄バッジ＋行ハイライト。**VAH/VAL**: 黄枠バッジ＋破線境界。Value Area帯は薄黄
- SIG列: Buy Imbalance ▸緑 / Sell Imbalance ◂赤（ask>bid×3 等の**表示強調のみ**。判定はFLOW/ANALYSISが正）/ Absorption ●黄
- コントロール: バー送り ◀ n/300 ▶（過去300本保持）/ ズーム±（0.75〜1.5）/ 価格ロック🔒

## 3.4 FLOW EVENTS（データ源: FLOW）

行: 時刻 / カテゴリバッジ（§2色）/ **BUY/SELL**（緑/赤）/ Detector名（灰）/ strengthブロックバー ■×10 / 数値。
新着が先頭、古い行はフェード、最大40行保持。ヘッダに凡例＋LIVEドット。

## 3.5 MARKET STATE（データ源: ANALYSIS.market_state）

**受信文字列を大型チップでそのまま描画。** ヘッダに「FROM SIGNALENGINE」。
表示ヒント: 文字列がBULLを含めば緑、BEARなら赤、他は灰（意味の再定義ではない）。

## 3.6 CONFLUENCE（データ源: ANALYSIS.confluence）

★×count（5段階）＋ CVD/FP/IMB/ABS/FLOW の✔/—チップ。**UIは受信フラグを描画するのみ**。

## 3.7 SIGNAL — WHY（データ源: ANALYSIS）

上段: `signal` 文字列（BUY緑/SELL赤/WAIT灰/その他は黄）＋CONF%。veto≠NONEなら⚠バッジ。
中段（意思決定の主役）: **検出器スコアバー5本が先**（CVD/FOOTPRINT/IMBALANCE/ABSORPTION/FLOW、±100は符号色、0〜1系は幅×100）、区切り線の下に**COMPOSITE（紫）を最後**。nullは「—」＋空バー。
下段: RISK（LOW緑/MEDIUM黄/HIGH赤）/ EXP. RR（v1は常に「—」）/ VETO。

## 3.8 ボトムチャート（データ源: CANDLE / OI / LIQUIDATION）

タブ: **CVD+Δ（デフォルト、CVD実線＋delta紫破線の重ね描き）** / VOLUME / OI（紫）/ LIQUIDATION（黄）。直近140点。

## 3.9 ALERTS履歴（右下常設）

FLOW strength≥0.85 を🚨トースト（3秒）＋履歴（直近8件: 時刻/カテゴリ点/方向/強度）。閾値はconfig `webapp.alert_threshold`。

## 3.10 DEVELOPER OVERLAY（左下、デフォルト非表示）

STATS由来: TICK/SEC・QUEUE・DROPPED・WS・CPU・RAM ＋ クライアント計測: FPS・LATENCY。🐛でトグル。

---

# 4. 接続・エラー表示

- HELLO受信で `payload_version` 検証。不一致→**画面上部にWarningバナーを常時表示し、描画は継続**（Payload仕様§6.2 の段階的縮退）。必須フィールド欠落のメッセージのみ単位でスキップ。全面停止はしない
- 切断→LIVEバッジを灰「RECONNECTING」に。指数バックオフ再接続（1s→2s→…最大10s）
- Payload欠損フィールドは「—」。UI例外で画面を落とさない（メッセージ単位でスキップ）

# 5. スコープ外（将来ADR。指示書_WebApp_v3 §1 の予約ADR番号を参照）

signal 4値化（AVOID等）/ market_state再定義 / Expected RR算出 / EconomicEventProvider / DELTA・EXHAUSTION・ICEBERG Detector。
