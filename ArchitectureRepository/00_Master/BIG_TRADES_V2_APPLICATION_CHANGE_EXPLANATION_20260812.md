# Big Trades V2でアプリの何がどう変わるか

作成日: 2026-08-12

## 1. 現在の状態

現時点では、アプリ本体は何も変わっていない。

変更したのは次の設計文書である。

- Big Trades Effort／Result・Reaction Zoneロジック正本V2。
- Big Trades Effort／Result・Reaction Zone実装指示書V2。
- 書き直し作業のcheckpoint。

ソースコード、画面、DB、設定、実行中serviceには変更を入れていない。したがって、現在起動しているDeltaEngine05Mの表示と動作は、V2文書作成前と同じである。

## 2. V2を実装した場合に追加されるもの

### 2.1 Big Trades専用表示

既存の3段chartを変更せず、独立したBig Trades表示modeを追加する。

Big Trades表示では、大口約定event、約定価格帯、後続価格の反応、同じ価格帯で発生した後続大口約定を確認できる。

### 2.2 大口約定の選別

大口約定の選別方法として、次の2modeを使用できるようにする。

#### Manual

userが数量のMin／Maxを設定する。

```text
Min以上
かつ
Max以下
```

の約定eventをBig Tradeとして採用する。

#### Automatic

銘柄、session、quantity step、取引数量の分布、activity、volatilityに対応するcalibrationからSize Filterを決定する。

Automaticで使用したcalibration versionとthresholdはeventへ記録し、後から同じ条件を再現できるようにする。

### 2.3 Big Trade markerと一件ごとの履歴

Size Filterを通過したBig Tradeを、一件ずつchart markerとして表示する。

各eventには次を保存する。

- BUY／SELL。
- 合計数量。
- event開始時刻と終了時刻。
- 約定価格の安値と高値。
- event VWAP。
- eventを構成した個別約定。
- 適用したsettings version。
- 適用したcalibration version。
- Live／Replayで共通するdeterministic event ID。

markerを選択すると、そのeventの詳細と後続履歴を表示する。

### 2.4 Reaction Zone

一件のBig Tradeが成立した実際の約定安値から約定高値までをReaction Zoneにする。

```text
zone low  = event内の最安約定価格
zone high = event内の最高約定価格
zone anchor = event VWAP
```

この価格帯をevent発生後の時間方向へ延長する。

Reaction Zoneは単なる水平線ではない。後続価格がその価格帯に対して何をしたかを継続記録する観測領域である。

価格がZoneを一度突破してもZoneを削除しない。同じUTC session内では、突破後の戻り、再接触、再突破、反対方向への移動を同じZoneの履歴として保持する。

## 3. 大口約定後に記録される価格結果

Reaction Zoneごとに、後続価格から次を記録する。

- 最初にZoneの上へ出たか。
- 最初にZoneの下へ出たか。
- Zoneの上へ最大何tick進んだか。
- Zoneの下へ最大何tick進んだか。
- Zoneへ戻ったか。
- Zoneへ再び接触したか。
- Zone全体を横断したか。
- 同じ価格帯で別のBig Tradeが発生したか。
- 後続Big TradeがBUYだったかSELLだったか。
- 1秒後の価格位置。
- 5秒後の価格位置。
- 15秒後の価格位置。
- 30秒後の価格位置。
- 60秒後の価格位置。
- 180秒後の価格位置。
- 300秒後の価格位置。
- 600秒後の価格位置。
- 1-minute candleがZone外でcloseしたか。
- candleのwickだけがZone外へ出てZone内へ戻ったか。

各時点の価格位置は次の3種類で保存する。

```text
ABOVE  = Zoneより上
INSIDE = Zone内
BELOW  = Zoneより下
```

## 4. 画面で確認できる内容

選択したBig Trade／Reaction Zoneの詳細画面で、次を時系列に確認できるようにする。

1. どちら側のBig Tradeだったか。
2. 約定数量はいくらだったか。
3. どの価格帯で成立したか。
4. 成立直後に価格がどちらへ移動したか。
5. 各経過時間で価格がZoneの上、内側、下のどこにいたか。
6. Zoneから最大何tick離れたか。
7. Zoneを抜けた後に戻ったか。
8. Zoneへ何回再接触したか。
9. 同じ価格帯で後続Big Tradeが発生したか。
10. 後続Big Tradeのsideと数量。
11. candleがZone外で確定したか、wickだけ外へ出たか。
12. 同時刻のCVD、Delta、Footprint、Flow Price Response。

これにより、次の二つを同じevent／zone画面で比較できる。

```text
effort
= どちら側が、どの価格帯で、どれだけ大きく約定したか

price result
= その後、価格がどちらへ、どれだけ動いたか
```

## 5. Fabio型の判断との関係

V2実装後は、大口約定のmarkerを見るだけではなく、大口約定というeffortと、その後のprice resultを同じ画面で確認できるようになる。

確認できる事実は次である。

```text
大口約定が発生した
  → 約定価格帯から価格が離れた
  → 離れた方向と距離を確認する
  → 価格帯へ戻ったかを確認する
  → 同じ価格帯で大口約定が再発したかを確認する
  → candle closeとwick returnを確認する
```

これが、Fabio型の「大きなeffortに対して、価格がどのようなresultを返したか」を人間が判断するために追加される機能である。

## 6. アプリが自動では行わない判断

systemは次を自動確定しない。

- 吸収確定。
- 買い手の勝ち。
- 売り手の勝ち。
- 同一人物または同一機関の取引。
- entry指示。
- exit指示。
- 売買signal。

systemが保存・表示するのは、Big Tradeの規模、価格帯、後続価格、再接触、突破、戻り、後続eventという市場事実である。

userが判断結果を記録する場合は、system factとは別のuser assessmentとして保存する。

## 7. 既存機能への影響

V2は次の既存機能を変更しない前提で実装する。

- 既存3段chartの配置、寸法、意味。
- Flow Price Responseの6窓、分類、outcome。
- CVD。
- Footprint。
- DOM。
- Tape。
- Book。
- Heatmap。

CVD、Delta、Footprint、Flow Price Responseは、Big Trades判定を変更する入力ではなく、選択したBig Tradeと同時刻の参考情報として読み取り表示する。

## 8. 変更の核心

V2実装によるアプリ変更の核心は次である。

```text
大口約定候補をSize Filterで抽出する
  → 一件ごとのmarkerと履歴を作る
  → 実約定価格帯をReaction Zoneとして残す
  → 後続価格の突破、戻り、再接触、反復大口約定を記録する
  → 大口のeffortと実際のprice resultを同じ画面で比較できる
```

単に大口markerが追加されるのではない。大口約定が発生した価格帯と、その後に価格が示した結果を継続して確認できるようになる。

## 9. 現時点で完了している範囲

現時点で完了しているのは、V2ロジック正本、V2実装指示書、本説明書の作成である。

次は未実施である。

- source code実装。
- Big Trades画面追加。
- DB schema追加。
- API／WebSocket追加。
- calibration生成。
- runtime接続。
- production activation。

したがって、現在のアプリには上記機能はまだ追加されていない。
