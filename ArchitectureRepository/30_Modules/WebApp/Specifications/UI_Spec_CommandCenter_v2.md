# UI Specification — Command Center v2

**Document ID**: REF-UI-002
**Version**: v2
**Status**: Current
**Effective date**: 2026-07-22
**Implementation baseline**: `Delta_Engine_Pro4web` commit `9c4539d`
**Supersedes**: `UI_Spec_CommandCenter_v1.md`

---

## 0. Mission

DeltaEngineのWeb UIは、注文フローと価格反応のズレを時間軸で観測し、
その後の値動きとの関係を実データで検証するための画面である。

画面は売買判断、売買確率、期待収益を生成しない。独立した観測値を不透明な
`SIGNAL`、`CONFIDENCE`、`COMPOSITE`などへ再統合しない。

## 0.1 Design principles

1. **OBSERVATION FIRST**: 最初に事実を表示し、未検証の評価と混同しない。
2. **INDEPENDENT INDICATORS**: CVD、Footprint、Imbalance、Absorption、Flowを独立して読める状態に保つ。
3. **TIME CONTEXT**: 「圧力が続く → 価格が停滞／逆行する → 数分後に動く」を同じ時間軸で追えるようにする。
4. **NO FABRICATION**: Payloadにない値は作らず、欠損時は `—` を表示する。
5. **STABLE LAYOUT**: ライブ更新でパネルやチャートヘッダーの高さを変動させない。

---

## 1. Visible language

- 画面に表示する項目名、状態名、設定、操作案内は英語で統一する。
- ユーザーが定義したPRICE・CVD・Delta・OIの組み合わせ評価表だけは、
  意味を正確に確認する参照資料として日本語表示を許可する。
- 文書の説明は日本語でもよいが、UI文字列を示す場合は実装と同じ英語を使う。
- HTMLは `lang="en"`、`translate="no"`、`notranslate`を指定し、ブラウザの自動翻訳で用語が変わらないようにする。
- `FLOW RESPONSE`、`ORDER BOOK`、`IMBALANCE`、`ABSORPTION`など、取引画面で一般的な用語を不自然な日本語へ直訳しない。

---

## 2. Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ TOP BAR: SYMBOL / PRICE / ATR / SPREAD / LATENCY / FPS / LIVE│
├──────────────────────────────────────────────────────────────┤
│ PRICE × FLOW RESPONSE                                        │
│ ┌───────────────────────────────────────┬──────────────────┐ │
│ │ PRICE + FLOW RESPONSE                 │ SELECTED CANDLE  │ │
│ │ CVD + Δ                               │ DETAILS          │ │
│ │ VOLUME                                │                  │ │
│ └───────────────────────────────────────┴──────────────────┘ │
├──────────────────┬──────────────────────┬────────────────────┤
│ FLOW EVENTS      │ FOOTPRINT            │ ORDER BOOK         │
│ ABSORPTION       │                      │                    │
│ IMBALANCE        │                      │                    │
└──────────────────┴──────────────────────┴────────────────────┘
```

実装上のDOM順序にかかわらず、ランタイム配置は左から
`FLOW EVENTS → ABSORPTION → IMBALANCE`、`FOOTPRINT`、`ORDER BOOK`を正とする。
`ABSORPTION`の直下に`IMBALANCE`を置く。

### 2.1 TOP BAR

表示項目:

- `SYMBOL`
- 現在価格（直前ティックに対して上昇ならBUY色、下落ならSELL色）
- BINANCE OI、直近1分変化率、直近5分変化率
- PRICE・CVD・Delta・OI組み合わせガイドを開く円形の「？」ボタン
- `ATR(14)`
- `SPREAD`
- `LATENCY`
- `FPS`
- 接続状態 `LIVE` / `CONNECTING` / `RECONNECTING`
- System Health、Developer Overlay、App Version

現在価格の横に変化率を表示しない。ページを開いた時点の最初の価格を基準にした
疑似騰落率は前日比ではなく、誤解を招くため禁止する。

OIはBinance USD-M Futures公式値だけを表示する。OI増加をBUY色、OI減少をSELL色へ
読み替えず、情報色の紫を使う。source受信から20秒を超えた場合はSTALE、60秒を
超えた場合は現在値を — とし、前回値による無表示補完を行わない。

### 2.2 PRICE × CVD × Delta × OI combination guide

- 「？」ボタンはTOP BARのBinance OI表示の直後に置く。
- クリック時は中央ダイアログを開き、背景を暗くして8ケースを一覧表示する。
- 閉じるボタン、ダイアログ外の背景クリック、Escapeキーのいずれでも閉じられるようにする。
- ダイアログは、今回ユーザーが定義したPRICEとCVDが同方向の8ケースだけを収録する。
- PRICEとCVDは対象足と2本前を比較し、Deltaは対象足の正負、
  OIは対象足のOPENからCLOSEへの変化として読む。

| PRICE | CVD | Delta | OI | 組み合わせによる評価 |
|:---:|:---:|:---:|:---:|---|
| ↑ | ↑ | ↑ | ↑ | 非常に強い上昇。新規ロングが積み上がっている。 |
| ↑ | ↑ | ↑ | ↓ | ショートカバー主体。上昇は続かないことも多い。 |
| ↓ | ↓ | ↓ | ↑ | 非常に強い下落。新規ショートが積み上がっている。 |
| ↓ | ↓ | ↓ | ↓ | ロングの投げ売り・手仕舞い。売り一巡後に反発することもある。 |
| ↓ | ↓ | ↑ | ↑ | 反発候補。買いが入り始め、新規資金も流入している。Footprintや板で確認したい。 |
| ↓ | ↓ | ↑ | ↓ | ショートの利確（買い戻し）の可能性が高い。本格反転とは限らない。 |
| ↑ | ↑ | ↓ | ↑ | 上昇中に売りが増加。吸収や分配の可能性。天井警戒。 |
| ↑ | ↑ | ↓ | ↓ | ロングの利確が主体。勢いが鈍る可能性。 |

この表はプロ用観測画面の凡例であり、新しい売買シグナル、確率、scoreではない。
既存のPrice・CVD・Delta 8パターンへOIを混ぜず、OI Contextの独立性を維持する。

---

## 3. Three-stage market chart

### 3.1 Structure

- 上段: candlesticks + `FLOW RESPONSE` background bands
- 中段: CVD line + current-bar Delta bars
- 下段: Volume bars
- 3段は同じ時刻軸を共有する。
- チャート右側に選択足の詳細を常設し、ツールチップによるレイアウト移動を起こさない。
- ヘッダーは固定高72pxの2行構成とし、ライブ文字列が長くなっても折り返しで画面を揺らさない。

### 3.2 Flow windows and colors

選択可能な時間窓は `30s / 1m / 3m / 5m / 15m / 30m`。
時間窓はローソク足のtimeframeではなく、各時点から過去へ遡るFlow Responseの観測窓である。
どの時間窓を選択しても、3段チャートのローソク足は`1m`のまま変更しない。

| UI state | Meaning | Chart color |
|---|---|---|
| `BUY PRESSURE · PRICE UP` | 買い圧力に価格が上方向へ追随 | pale green |
| `SELL PRESSURE · PRICE DOWN` | 売り圧力に価格が下方向へ追随 | pale red |
| `BUY PRESSURE · STALLED` | 買い圧力に対して価格が停滞 | yellow |
| `SELL PRESSURE · STALLED` | 売り圧力に対して価格が停滞 | yellow |
| `BUY PRESSURE · PRICE DOWN` | 買い圧力と価格が逆行 | purple |
| `SELL PRESSURE · PRICE UP` | 売り圧力と価格が逆行 | purple |
| `UNCLEAR` | 条件不足または中間状態 | no band |

- `PRICE × FLOW RESPONSE`の横に円形の「？」を置き、クリックすると上記7状態の
  色見本、画面表示、意味を一覧表示する。
- 黄色と紫は色だけでBUY／SELLを決めず、状態名で圧力側を確認する。
- 紫の2状態は内部状態の`BUY_TRAPPED`／`SELL_TRAPPED`と対応するが、通常画面では
  観測事実を表す`DIVERGENCE`および価格方向の表記を使う。
- 同じガイド内へ`TIME WINDOW READING MANUAL`を置き、通常運用を
  `5mで異変を見る → 1mで始点を確認 → 15mで広がりを確認`の3段階で説明する。
- 30sは早期発見、3mは1mと5mの橋渡し、30mは広い背景の補助と説明する。
- 複数窓を独立票または売買条件として数えないことを明示する。
- ガイドはoverlay dialogとし、チャート、固定詳細、ヘッダーの寸法を変更しない。
- 閉じるボタン、dialog外の背景クリック、Escapeキーのいずれでも閉じられるようにする。

`PRESSURE`、`PRICE`、`PERSISTENCE`、`VOLUME`は観測事実であり、
売買指示または確率として表示しない。

### 3.3 Controls

| Operation | Result |
|---|---|
| Left click | candleを選択し、ガイド線と固定詳細を表示 |
| `←` / `→` | 選択足を1本ずつ移動 |
| Right click | 選択、ガイド線、固定詳細を解除 |
| Mouse wheel | 表示本数を変更してzoom |
| Drag | 過去／最新方向へpan |
| `LIVE` | 最新足へ戻る |

### 3.4 Selected-candle details

固定詳細欄には時刻、OHLC、CVD、Delta、Volume、Flow Responseの状態と観測値、
価格・CVD・Deltaの8パターン、および選択足へ時刻同期したOpen Interestを表示する。

価格とCVDの方向は選択足と2本前を比較し、Deltaは選択足の正負で判定する。
8パターンは観測分類であり、売買シグナルではない。

| No. | UI name | PRICE | CVD | Δ | 読み方 |
|---:|---|:---:|:---:|:---:|---|
| 1 | `UPTREND` | ↑ | ↑ | ↑ | 累積・直近とも買い優勢で価格上昇 |
| 2 | `UPTREND PULLBACK` | ↑ | ↑ | ↓ | 累積は買い優勢、直近は売り、価格はまだ上 |
| 3 | `UPWARD REBOUND` | ↑ | ↓ | ↑ | 累積は売り優勢、直近買いと価格上昇 |
| 4 | `UPWARD DIVERGENCE` | ↑ | ↓ | ↓ | 売り圧力なのに価格が上昇 |
| 5 | `DOWNWARD DIVERGENCE` | ↓ | ↑ | ↑ | 買い圧力なのに価格が下落 |
| 6 | `DOWNTREND PULLBACK` | ↓ | ↑ | ↓ | 累積は買い優勢、直近売りと価格下落 |
| 7 | `DOWNWARD REBOUND` | ↓ | ↓ | ↑ | 累積は売り優勢だが直近買いが入る |
| 8 | `DOWNTREND` | ↓ | ↓ | ↓ | 累積・直近とも売り優勢で価格下落 |

運用上は名称の暗記より、固定詳細欄の `PRICE → CVD → Δ` の矢印を先に読む。

### 3.5 Open Interest context

- 3段チャートへ第4段またはOI線を追加しない。
- 選択足の固定詳細へOPEN、CLOSE、CHANGE、CHANGE %、SAMPLESを表示する。
- BUILDING ↑、UNWINDING ↓、UNCHANGED →は建玉総量の増減だけを表す。
- PRICE ↑ · OI ↓などの並列表記は観測事実であり、SHORT COVER等を断定しない。
- OIは既存8パターン、Flow Response、signal、scoreへ入力しない。
- bar開始時は開始時刻以前20秒以内の最新sample、bar終了時は終了時刻より前20秒以内の
  最新sampleを使う。どちらかが無い場合、変化量と変化率は — とする。
- OI欠損を補間、0埋め、forward-fillしない。
- sourceはBINANCE USDⓈ-Mと画面に明示する。

### 3.6 Recent Flow Event markers

Flow Eventが価格へどのような影響を与えたかを1〜2時間後に確認できるよう、
イベント発生時刻を含むローソク足へ小型マーカーを表示する。

- マーカー履歴はブラウザメモリ内だけで2時間保持する。
- DB、履歴API、localStorageへ保存せず、ページ再読込またはアプリ再起動で消去する。
- 2時間を過ぎたイベントはmarket timeを基準に自動消去する。
- 同じ足に複数イベントがある場合は1個のマーカーへ集約し、`L+`などで複数を示す。
- 表示幅が狭い場合は文字を省略して小さなdotへ縮退する。
- BUY eventは足の下、SELL eventは足の上へ配置する。NEUTRAL/MIXEDは白い輪郭で示す。
- marker codeは `L`=LARGE TRADE、`S`=SWEEP、`E`=EXHAUSTION、
  `U`=UNFINISHED AUCTION、`T`=TAPEとする。
- `FLOW EVENTS`の歯車に`CANDLE MARK`を設け、LARGE TRADE、SWEEP、EXHAUSTION、
  UNFINISHED AUCTION、TAPEを個別にON／OFFできるようにする。初期値はすべてONとする。
- OFFへ変更したcategoryは、現在表示中の過去足を含む全ローソク足のマーカーと
  選択足詳細から即時に隠す。同じ足にONの別categoryがあれば、そのマーカーは残す。
- CANDLE MARKは表示設定だけとし、Flow Eventの検出、FLOW EVENTS一覧、alert、
  2時間メモリからeventを削除しない。2時間内なら再びONにした時点で表示を復元する。
- event履歴そのものはlocalStorageへ保存しない。localStorageへ保存するのは
  categoryごとのCANDLE MARK表示設定と既存alert thresholdだけとする。
- candle選択時、固定詳細欄の `FLOW EVENTS · 2H MEMORY` にcategory、side、件数、
  その足の最大strengthを表示する。
- 同じイベントが即時 `FLOW` とbar-close `ANALYSIS.flow_events`の両方から届いても、
  発生時刻・category・side・price・strength・detailで重複を除外する。

これは観測位置を示す一時マーカーであり、entry、exit、売買推奨を意味しない。
Flow Responseの背景帯、CVD、Delta、Volume、8パターンの計算は変更しない。

---

## 4. Independent observation panels

### 4.1 FLOW EVENTS

- 時刻、event category、BUY/SELL、detector、strengthを表示する。
- Strengthは内部の0.00–1.00評価値であり、確率または期待収益ではない。
- 歯車内のevent名、意味、計算説明、category別`CANDLE MARK`、alert thresholdを
  英語で表示する。

### 4.2 ABSORPTION

- `BUY ABS` / `SELL ABS`、strength、観測値を表示する。
- `Stall ticks`と`Volume multiplier`は独立設定として扱う。

### 4.3 IMBALANCE

- BUY/SELLのwall、price range、stack countを1件1行で表示する。
- `Ratio`、`Stack count`、`Minimum volume`を画面上で変更し、配信済みFootprintから再計算できる。
- `ABSORPTION`の直下に配置する。

### 4.4 FOOTPRINT

- PRICE、BID、ASK、DELTA、SIG、POC、VAH、VAL、Value Areaを表示する。
- `Σ BID`、`Σ ASK`、`DELTA`は表示中barの全価格帯から集計する。
- Value Area、bar navigation、zoom、price lockを独立操作できる。

### 4.5 ORDER BOOK

- asks、mid、bidsをprice、quantity、cumulative depthで表示する。
- quantityに応じた背景濃度を使い、板の厚みを読めるようにする。
- Footprintまたは他の指標と合成したscoreを生成しない。

---

## 5. Removed legacy decision UI

次の項目は現行UIの構成要素ではなく、再導入しない。

- price-adjacent pseudo change rate
- `SIGNAL — WHY`
- `CONFIDENCE`
- `MARKET STATE`
- `CONFLUENCE`
- detector score bars
- `COMPOSITE`
- `RISK`
- `EXPECTED RR`
- `VETO`

Payloadに互換目的で同名フィールドが残っていても、UIはそれらを売買判断として表示しない。

---

## 6. Connection and failure behavior

- 欠損値は `—` とし、固定値や推測値で埋めない。
- OI取得失敗は値を生成せず更新をスキップする。リプレイ中はライブOI取得を起動しない。
- WebSocket切断時は再接続状態を表示し、段階的に再接続する。
- payload version不一致やhealth異常はbanner、health popup、Developer Overlayで確認できるようにする。
- ライブ更新中もチャート、ヘッダー、主要パネルの寸法を安定させる。

---

## 7. Acceptance baseline

- `webapp/static/index.html`のJavaScript構文が有効であること。
- 全体回帰試験が合格すること。
- ブラウザ実測でチャートと固定ヘッダーの寸法がライブ文字列更新前後で不変であること。
- Left click、arrow keys、Right click、wheel、dragが同時に維持されること。
- 画面に旧decision UIと疑似変化率が存在しないこと。
- 運用項目と状態名が英語で統一され、ユーザーが明示的に求めた組み合わせ評価表と
  Flow Response状態表の説明だけが日本語の例外であり、自動翻訳が無効であること。
- TOP BARの「？」で8行の組み合わせ表が開き、閉じるボタン、背景クリック、
  Escapeキーで閉じられること。
- `PRICE × FLOW RESPONSE`横の「？」で緑、赤、黄色、紫、色なしを含む7状態表が開き、
  `STALLED`、`TRAPPED / DIVERGENCE`、`UNCLEAR`の違いを確認できること。
- 同じガイドで`5m → 1m → 15m`の時間窓マニュアルと、切替後もローソク足が
  `1m`のままであることを確認できること。
- Flow Response状態表を開閉しても3段チャートの寸法と計算が変わらないこと。
- Flow Eventが本来の発生時刻の足へ集約表示され、選択詳細で内訳を確認できること。
- category別CANDLE MARKをOFFにすると過去足と選択詳細から即時に消え、ONにすると
  2時間メモリ内の対象だけが復元されること。FLOW EVENTS一覧とalertは影響を受けないこと。
- 重複配信を二重計上せず、market timeで2時間経過後にマーカーが消えること。
- Flow EventマーカーのためのDBまたは履歴APIを追加しないこと。
- 公式source timeを持つOIがTOP BARと選択足へ表示され、欠測時は — になること。
- OI追加後も3段構造、固定詳細、8パターン、Flow Responseの計算が不変であること。
