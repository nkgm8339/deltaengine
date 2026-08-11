# Big Trades V1／V1.1対V2 Scope・Static UI Mock Review

作成日: 2026-08-12

## 1. V1／V1.1の到達点

V1／V1.1の中心pipelineは次で終了していた。

```text
raw trade
  → 40ms same-side cluster
  → Manual／Automatic Size Filter
  → accepted Big Trade event
  → storage／WebSocket／history
  → chart marker
```

V1／V1.1で定義済みだった機能:

1. Manual Min／Max。
2. Automatic Low／Medium／Strong。
3. aggregate quantity、fills、価格範囲、時間範囲を持つevent。
4. marker priceをstart／last／VWAPから選択。
5. event persistenceとhistory hydration。
6. Live／Replay determinism。
7. calibration artifactとactivation history。

V1／V1.1では、accepted event後の価格経路をevent固有の価格帯へ関連付けて保存するcontractがなかった。

そのため次はV1／V1.1の完成条件に含まれていなかった。

- execution rangeを時間方向へ延長するReaction Zone。
- Zoneに対する`ABOVE／INSIDE／BELOW`。
- first exit。
- touch／reentry／cross。
- max above／below excursion。
- 1秒～600秒horizon result。
- candle close outside／wick return。
- 同じ価格帯の後続Big Trade link。
- break後のretest履歴。
- effortとprice resultの同一画面比較。

## 2. V2で追加したscope

V2ではSize Filterの後を次まで延長した。

```text
accepted Big Trade event
  → exact execution-range Reaction Zone
  → later accepted tradeとの位置関係
  → first exit／touch／reentry／cross
  → max excursion
  → fixed-horizon result
  → 1-minute close／wick observation
  → later Big Trade same-area link
  → event／zone／result history
  → selected zone detail UI
```

V2はV1／V1.1を破棄するものではない。Manual、Automatic、aggregation、event、marker、historyを前段として保持し、その後へReaction Zoneとresult observationを追加する。

## 3. 四機能の対応

| 要求機能 | V1／V1.1 | V2 |
|---|---|---|
| Manual Min／Max | あり | 継承。境界値込み、Max 0は上限なし |
| Automatic Size Filter | あり | 継承。20完了session、20／9／2順位、volatility補正、versioned activation |
| 一件ごとのmarkerと履歴 | あり | 継承。eventと全fillsに加えzone／result履歴へ拡張 |
| 約定価格から延長するReaction Zone | なし | exact event low～highをsession内で保持 |

四つ目がない状態を、V2完成またはFabio型判断材料の完成として扱わない。

## 4. Fabio型判断に対する差

V1／V1.1で確認できる内容:

```text
どちら側に、どれだけ大きな約定が出たか
どの価格で発生したか
```

V2で追加される内容:

```text
その約定価格帯から価格がどちらへ離れたか
何tick動いたか
価格帯へ戻ったか
同じ価格帯で大口約定が再発したか
candleが外でcloseしたか、wickだけ外へ出たか
```

したがってV2では、executed effortとsubsequent price resultを一つのselected zoneで比較できる。

V2 systemは吸収、買い手勝利、売り手勝利、entry、exitを自動確定しない。表示するのは判断材料となる事実である。

## 5. Static UI mock files

- HTML: `BIG_TRADES_STATIC_UI_MOCK.html`
- screenshot: `big_trades_static_ui_mock_1280x900.png`
- viewport: 1280×900
- horizontal overflow: 0 px
- page error: 0
- HTML SHA-256: `D7EB2269D9E8A92733E5D09753E01567D29680785153BD28A1A447BACB52FFE6`
- screenshot SHA-256: `0C624D51D8B1FD9201FBE0D5DC09910FE06D63A9202873F83AEECD5290262DD1`

このmockはstandalone fileであり、現行`webapp/static/index.html`、runtime、WebSocket、DBへ接続していない。

## 6. Mock上の配置

### Protected area

上段の`PRICE × FLOW RESPONSE`に、現在のPRICE／CVD+Delta／VOLUMEという3段構造を残す。

Big Tradesの都合で上段3段chartの位置、寸法、meaningを変更しない。

### Order Flow View mode

既存中央panelのmode selectorを次の3modeにする。

```text
FOOTPRINT | HEATMAP | BIG TRADES
```

Big Trades選択時だけ中央CanvasをBig Trades viewへ切り替える。FootprintとHeatmapの既存描画sourceを変更しない。

### Big Trades Canvas

表示:

- BUY／SELL marker。
- aggregate quantity label。
- exact execution-range Reaction Zone。
- Zoneの右方向extension。
- selected Zone。
- later linked Big Trade marker。
- price path。
- source gap表示。

### Selected Reaction Zone detail

同じpanel内で次を表示する。

- event side／quantity／time。
- execution range／VWAP／fill count。
- current relation。
- first exit direction／time。
- max above／below ticks。
- linked event count。
- interaction timeline。
- system facts。
- user assessment。

system factsとuser assessmentは別枠にする。

### Right observation panel

selected Zoneのeffort、price result、horizon facts、read-only contextを表示する。

画面下部へ、systemがabsorption、buyer victory、seller victory、entry、exitを確定しないことを常時明示する。

### Existing Tape

Time & Salesは従来の個別約定表示のまま残す。Tape filterとV2 Size Filterを同一設定として扱わない。

## 7. Mockで使用した未承認値

表示例として次を置いた。

```text
filter mode = MANUAL
Manual Min = 20.000 BTC
Manual Max = 0／unbounded
side = BOTH
```

これはstatic表示例であり、production値として承認・採用されていない。

## 8. UI実装前に必要なuser確認

1. `FOOTPRINT | HEATMAP | BIG TRADES`の第3mode配置。
2. Big Trades Canvas内にselected Zone detailを置く配置。
3. 右側observation panelをBig Trades選択時に切り替える配置。
4. system factsとuser assessmentの分離表示。
5. Manual Min／Max、mode、side filterをmode headerへ置く配置。

未承認のまま現行`index.html`へ反映しない。
