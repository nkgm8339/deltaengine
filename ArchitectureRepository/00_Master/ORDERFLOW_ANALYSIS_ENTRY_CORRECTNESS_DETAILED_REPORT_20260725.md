# Order Flow 分析正確性・entry時点正確性 詳細説明レポート

- 作成日: 2026-07-25 JST
- 対象期間: 2026-07-24 01:55 JST〜2026-07-25 16:55 JST（約39時間）
- 対象市場: Binance Futures `BTCUSDT`、HFM MT5 `#BTCUSDr`
注文送信: 0

## 0. このレポートの目的

このレポートは、結果の数字だけを並べるものではない。次の順番で、何をしたかを一つずつ説明する。

1. 何を明らかにしたかったのか
2. 用語が何を意味するのか
3. どの実データを使ったのか
4. 1件の分析をどう正しい／不正確に分けたのか
5. 「全decision」と「最初のentry」がなぜ別集計なのか
6. 何件を評価し、何件を除外したのか
7. 実際の結果はどうだったのか
8. どこまで結論にしてよく、何がまだ未確定なのか
9. なぜ期間外追試という次工程が出てくるのか

先に最終結論だけを言うと、今回の約39時間では、**Flow状態を表示中ずっとentryに使う方法と、状態が現れた最初の時点だけentryする方法で結果が違った**。特に`TRAPPED_REVERSAL`の10分評価は、全更新時点では50%未満だったが、最初の非重複entryに限定するとBinance 57.31%、HFM 55.95%になった。

ただし、この文の意味を理解するには「全更新」「最初」「非重複」の定義が必要なので、以下で順番に説明する。

---

## 1. 今回明らかにしたかった二つのこと

今回の目的は、取引コストを計算することではない。次の二つを分けて調べることだった。

### 1.1 分析の正確さ

ある時点でFlow Price Responseが上方向または下方向を示したとき、その方向へ将来価格が動いたかを調べる。

例:

- `BUY_EFFECTIVE`が出た
- その時点では「買い圧力が価格上昇として有効に反応している」と読む
- 10分後、20分後、30分後、45分後、60分後の価格を確認する
- 上昇していれば方向は正しい
- 下落していれば方向は不正確

### 1.2 entry時点の正確さ

分析内容が正しくても、状態が表示されている間ならいつ入ってもよいとは限らない。

例えば`SELL_TRAPPED`が30秒間続き、その間に10回更新された場合、次の二つは別問題である。

- 10回の観測内容がそれぞれ正しかったか
- 最初の1回だけentryした場合、そのentry時点は正しかったか

今回の重要点はここである。分析ラベルの意味と、実際に入る瞬間を同じものとして扱わなかった。

---

## 2. 今回の用語

| 用語 | このレポートでの意味 |
|---|---|
| Flow row | 保存されたFlow Price Responseの1回の観測更新 |
| decision | Flow rowから作った上方向／下方向の評価判断 |
| hypothesis | そのdecisionで検証する方向の意味。継続、反転、STALLED対照など |
| entry | decision時点で、その方向へゼロスプレッドの架空取引を開始すること |
| fixed exit | entryから10／20／30／45／60分後に機械的に観測を終了すること |
| 正しい | BUYならexit価格がentry価格より高い、SELLなら低い |
| 不正確 | BUYならexit価格が低い、SELLなら高い |
| FLAT | entry価格とexit価格が同じ。正しい件数には入れないが分母には残す |
| 方向正確率 | 正しい件数 ÷ 有効評価件数 |
| bps | 価格変化率の単位。1bps = 0.01% |
| signed return | BUY上昇／SELL下落をプラスへそろえた変化率 |
| MFE | entry後、評価終了までに最も有利だった値動き |
| MAE | entry後、評価終了までに最も不利だった値動き |
| ゼロスプレッド | Bid／Ask差、手数料、slippageを差し引かず、方向と時点だけを見る評価 |

ここでいう「正しい」は、実口座で利益が出たという意味ではない。**分析方向とentry時点が、その後の価格方向と一致した**という意味である。

---

## 3. なぜ最初にゼロスプレッドで評価したのか

実取引損益は、大きく分けると次の要素で決まる。

1. 分析方向が正しいか
2. entry時点が正しいか
3. exit方法が正しいか
4. spread、手数料、slippageを払っても残るか

この四つを最初から一つに混ぜると、負けた理由を区別できない。例えば、分析とentryが正しかったのにHFM spreadだけでマイナスになった場合、それを「分析が不正確」と結論してはいけない。

そのため今回は、1と2を先に調べた。3は10〜60分の固定時点へ単純化し、4は完全に除外した。

今回使用していないもの:

- spread控除
- 売買手数料
- slippage
- TP
- SL
- trailing stop
- 状態を見た動的exit
- 結果を見た後の保有時間変更

したがって、以前の`NO_GO_FOR_HFM_ENTRY_V1`は、30 USDのcostを入れた特定Episode仕様についての結論に限定される。今回の分析方向・entry時点の正確性を否定する結論としては使用しない。

---

## 4. 使用した期間

### 4.1 Flow decisionの期間

- 開始付近: 2026-07-24 01:55 JST
- decision cutoff: 2026-07-25 15:55 JST
- 最大保有時間: 60分
- outcome cutoff: 2026-07-25 16:55:05 JST

15:55 JSTまでに発生したdecisionだけを対象にした。そこから最大60分後まで価格を必要とするため、価格データは16:55 JSTまで使用した。

### 4.2 固定した保有時間

- 10分
- 20分
- 30分
- 45分
- 60分

すべてを同時に出した。結果が良かった時間だけに途中変更していない。

---

## 5. 使用した実データ

### 5.1 分析元のFlowデータ

二種類を使用した。

1. `ROLLING_FLOW_RESPONSE`
   - 30秒、60秒、180秒、300秒、900秒、1800秒のrolling窓
2. `NATIVE_FLOW_5M10M`
   - native 5分、10分のFlow event

読み込んだ元データ:

- rolling Flow rows: 5,957
- native 5m／10m Flow rows: 277

### 5.2 Binance価格

entry価格には、各Flow eventへその時点で保存されていた実約定価格`last_price`を使用した。

固定時間後のexit価格とMFE／MAEには、Binance Futures公開REST APIの確定1分足を使用した。

- symbol: `BTCUSDT`
- interval: 1分
- snapshot全体: 2,341本
- expected: 2,341本
- missing: 0
- duplicate: 0
- invalid: 0
- 60秒超gap: 0
- 認証: なし
- 注文API: 不使用

評価器が実際に読み込んだ対象barは2,339本である。これはsnapshot端のうちdecision評価範囲外のbarを除いたためであり、欠損ではない。

### 5.3 HFM価格

接続中のHFM MetaTrader 5から`#BTCUSDr`の実tick履歴を読み取った。

- tick snapshot: 594,229件
- 評価範囲へ読み込んだtick: 593,474件
- invalid quote: 0
- duplicate: 0
- 最大gap: 57.547秒
- 120秒超gap: 0
- positions: 0
- orders: 0
- 注文送信: 0

ゼロスプレッド評価なので、HFMでは`(Bid + Ask) / 2`のmidを評価価格にした。BidとAsk自体はsnapshotへ保存しているが、今回の方向判定にはspreadを適用していない。

---

## 6. データ入力で起きた問題と訂正

### 6.1 HFM quoteが0 bytesという以前の確認は誤りだった

workspace内のbind targetを実ファイルと誤認していた。実際のHFM quoteはMT5 Common Filesに63MB以上存在していた。

また、MT5 history APIから実tickを読み取れることも確認した。したがって、以前の「HFM同一時計quoteが無いため未評価」という説明は今回訂正した。

### 6.2 HFMのserver clockをUTCとして扱わなかった

HFM server timestampはUTCより10,800秒、つまり3時間進んでいた。次の二つで確認した。

- 保存済みsource timeとlocal received timeの対応点199件
- live tick sample 20件

両方が+10,800秒で一致したため、server timeから10,800秒を引いてUTCへ正規化した。推測だけで時刻を変えてはいない。

### 6.3 Binanceのローカル保存データには収録停止区間があった

最初の評価では、保存済みBinance生約定を使った。しかしFlow decisionが存在する時刻に生約定ファイルが止まっている区間があり、entry時刻から約95分後の価格を誤って「最初の価格」として選ぶ例が出た。

ローカル1分足も調べたが、対象期間に60秒超gap 82件、最大gap 25,920秒があった。そのため代替には使わなかった。

最終評価では次のように訂正した。

- entry: Flow eventに保存されたsignal実約定価格
- exit／MFE／MAE: 欠損0の公式Binance Futures確定1分足

### 6.4 Signal価格と公式価格の整合性

Flow eventのsignal実価格を、同じ時刻の公式Binance 1分足high／lowと照合した。

- unique signal observation: 6,234
- 公式barで時刻を確認できた件数: 6,234
- high〜low範囲内: 6,234
- 範囲外: 0
- 整合率: 100.00%

これにより、entryへ使ったFlow eventの`last_price`が公式市場価格と矛盾していないことを確認した。

---

## 7. Flow状態をどの方向へ読んだか

完成済みFlow Price Responseの状態名の意味は変更していない。方向への変換は評価前に次のように固定した。

| Flow状態 | 評価方向 | 仮説名 | 意味 |
|---|---|---|---|
| `BUY_EFFECTIVE` | BUY | `EFFECTIVE_CONTINUATION` | 買い圧力が価格上昇として有効なので上方向継続 |
| `SELL_EFFECTIVE` | SELL | `EFFECTIVE_CONTINUATION` | 売り圧力が価格下落として有効なので下方向継続 |
| `BUY_TRAPPED` | SELL | `TRAPPED_REVERSAL` | 買い圧力が吸収されたため反対の下方向 |
| `SELL_TRAPPED` | BUY | `TRAPPED_REVERSAL` | 売り圧力が吸収されたため反対の上方向 |

### 7.1 STALLEDを方向確定にしなかった理由

`BUY_STALLED`／`SELL_STALLED`は、圧力があるが価格が十分反応していない状態である。それだけでは、その後に突破するか反転するかを一方向へ確定できない。

そこでentry研究用の対照として、同じ時点に二つのprobeを作った。

- `STALLED_PRESSURE_PROBE`: 圧力側へ進むと仮定
- `STALLED_REVERSAL_PROBE`: 圧力と反対へ進むと仮定

これは二つとも同時に取引するという意味ではない。同じ価格変化を正方向と逆方向から比較するための対照である。そのため両者の結果は原則として反対になる。

---

## 8. 1件のdecisionをどう評価したか

例として、時刻`t`に`SELL_TRAPPED`が発生し、signal価格が64,000だったとする。

### Step 1: 方向へ変換

`SELL_TRAPPED`は、売り圧力が下へ進めず捕まった状態なので、評価方向をBUYにする。

### Step 2: entry価格を決める

- Binance: Flow eventに保存された`t`時点の実約定価格64,000
- HFM: 正規化した`t`以後、2秒以内に到着した最初の実tick mid

### Step 3: 10分後の価格を取る

- Binance: `t + 10分`以後に閉じる最初の確定1分足close
- HFM: `t + 10分`以後、5秒以内の最初の実tick mid

仮にexit価格が64,064なら、上昇率は約10bpsである。BUY評価なのでsigned returnは+10bpsとなり、方向は正しい。

exit価格が63,936なら約-10bpsとなり、方向は不正確である。

### Step 4: 20／30／45／60分も別々に計算

10分結果を使って20分以降を決めない。各固定時間を独立した反実仮想として同時に保存した。

---

## 9. BinanceとHFMで価格時刻の精度が違う理由

### 9.1 Binance

entryはFlow eventに保存された実約定価格なのでentry lagは0msである。

exitは1分足closeを使うため、目標時刻から最大約60秒後になる。非重複entry評価でのoutcome lagは次のとおり。

- 中央値: 25.606秒
- 95%点: 57.218秒
- 最大: 59.733秒

この1分未満のずれは、固定決済が「およそ10分〜1時間」でよいという今回の目的に合わせた。

BinanceのMFE／MAEは、signalが含まれる途中の1分足を使わず、signal時刻以後に開始する最初の完全な1分足から測った。途中のbarを使うとsignal前のhigh／lowまで混ざるためである。この方法ではsignal直後の最大60秒弱をMFE／MAEから省くので、Binanceの経路値は1分解像度の近似として扱う。fixed exitの方向判定にはsignal実価格と将来bar closeを使う。

### 9.2 HFM

HFMはtickを使う。非重複entry評価でのlagは次のとおり。

- entry lag中央値: 96ms
- entry lag 95%点: 878ms
- entry lag最大: 1.977秒
- outcome lag中央値: 140ms
- outcome lag 95%点: 1.307秒
- outcome lag最大: 4.661秒

entryが2秒を超えた結果、またはoutcomeが5秒を超えた結果は有効結果へ混ぜず、明示的に除外した。

---

## 10. 「全decision」と「非重複entry」の違い

ここが今回もっとも重要な区別である。

### 10.1 全decision集計

Flow状態は市場が動くたびに更新される。同じ`SELL_TRAPPED`が20秒続けば、似た状態のrowが何回も保存される。

全decision集計では、その一つ一つを分析観測として評価する。これは「表示されていた分析内容が各時点で正しかったか」を見る集計であり、独立した取引回数ではない。

### 10.2 非重複entry集計

実際に1回entryしたら、同じポジションを保有中に同じpolicyで何度もentryしない。

例えば10分保有policyなら、次のようにする。

```text
12:00:00  最初のTRAPPED → entryとして採用
12:00:20  TRAPPED継続     → 保有中なので不採用
12:01:10  TRAPPED継続     → 保有中なので不採用
12:10:00  10分終了
12:10:05  新しいTRAPPED   → 次のentryとして採用可能
```

この重複除外は、次の単位ごとに別々に行った。

- symbol
- source family
- window
- hypothesis
- fixed horizon

10分policyと60分policyでは保有中として除外される範囲が違うため、選ばれるdecisionも違う。したがって、5種類のhorizon結果を単純に5倍の独立取引とは扱わない。

---

## 11. 評価件数の内訳

### 11.1 評価candidate

合計9,208 candidateを作った。

| class | hypothesis | 件数 |
|---|---|---:|
| 分析 | `EFFECTIVE_CONTINUATION` | 2,679 |
| 分析 | `TRAPPED_REVERSAL` | 581 |
| 対照probe | `STALLED_PRESSURE_PROBE` | 2,974 |
| 対照probe | `STALLED_REVERSAL_PROBE` | 2,974 |
| 合計 |  | 9,208 |

STALLEDは同じrowから正反対のprobeを二つ出すため、candidate数が増える。

### 11.2 固定horizon outcome

| Scope | Binance | HFM | 合計 |
|---|---:|---:|---:|
| 全decision × 5 horizon | 46,040 | 46,040 | 92,080 |
| 非重複entry outcome | 4,852 | 4,852 | 9,704 |

Binanceの非重複entry outcome 4,852のうち、horizon間の重複を除いたunique decision IDは2,627である。HFMで有効価格までそろったunique decision IDは2,510である。

ただし、異なるwindowが同じ市場時刻を含む場合があるため、2,627件も完全に独立した2,627回の相場現象という意味ではない。

### 11.3 有効／除外件数

| Scope | Market | OK | ENTRY_LAG | OUTCOME_LAG | DATA_GAP |
|---|---|---:|---:|---:|---:|
| 全decision | Binance | 46,040 | 0 | 0 | 0 |
| 全decision | HFM | 43,935 | 1,620 | 485 | 0 |
| 非重複entry | Binance | 4,852 | 0 | 0 | 0 |
| 非重複entry | HFM | 4,651 | 166 | 35 | 0 |

HFMの`ENTRY_LAG`と`OUTCOME_LAG`は、tick間隔が閾値を超えた評価を結果へ混ぜないための除外である。

---

## 12. Step A — 二市場の価格方向は同じだったか

BinanceとHFMの両方で有効だった同一decision・同一horizonだけを組にした。

| Scope | paired OK | 同じ方向結果 | signed return相関 | signed return差の絶対値中央値 |
|---|---:|---:|---:|---:|
| 全decision | 43,935 | 95.83% | 0.993651 | 0.598bps |
| 非重複entry | 4,651 | 95.94% | 0.992723 | 0.507bps |

意味:

- BinanceとHFMは別価格配信、別instrumentだが、今回の固定時間方向は約96%一致した
- return相関も0.99以上だった
- したがって、Binanceだけの偶然な価格方向をHFMへそのまま当てはめた結果ではない

注意:

BinanceとHFMは同じBTC相場を追うため、二つを独立標本として合算してはいけない。HFMは実際の取引先価格でも同方向だったかを確認する再現市場として扱う。

---

## 13. Step B — 全decisionで分析内容は正しかったか

この節はentry回数ではない。状態が表示されている各更新時点で、分析方向が将来価格と一致した割合である。

### 13.1 EFFECTIVE_CONTINUATION

| Hold | Binance n | Binance正確率 | Binance中央値bps | HFM n | HFM正確率 | HFM中央値bps |
|---:|---:|---:|---:|---:|---:|---:|
| 10分 | 2,679 | 50.73% | +0.109 | 2,617 | 51.24% | +0.218 |
| 20分 | 2,679 | 50.47% | +0.062 | 2,606 | 51.57% | +0.342 |
| 30分 | 2,679 | 48.45% | -0.453 | 2,615 | 48.30% | -0.337 |
| 45分 | 2,679 | 52.97% | +0.998 | 2,612 | 53.10% | +1.377 |
| 60分 | 2,679 | 49.72% | -0.047 | 2,604 | 49.69% | -0.115 |

読み方:

- EFFECTIVE状態を表示中の全時点で継続方向が常に正しい、とは言えない
- 全window合算では45分が約53%だった
- 30分は全decision集計では50%未満だった

### 13.2 TRAPPED_REVERSAL

| Hold | Binance n | Binance正確率 | Binance中央値bps | HFM n | HFM正確率 | HFM中央値bps |
|---:|---:|---:|---:|---:|---:|---:|
| 10分 | 581 | 46.64% | -0.624 | 562 | 46.26% | -0.732 |
| 20分 | 581 | 44.75% | -1.091 | 567 | 44.44% | -1.418 |
| 30分 | 581 | 43.55% | -1.699 | 568 | 44.37% | -1.898 |
| 45分 | 581 | 41.31% | -2.261 | 566 | 41.17% | -1.732 |
| 60分 | 581 | 46.64% | -1.154 | 564 | 46.45% | -1.008 |

一見すると、TRAPPEDを反転方向として読むのは不正確に見える。しかし、この表には状態が続いてから遅れて更新された時点もすべて入っている。そこで次に、最初のentryだけを見る。

---

## 14. Step C — 最初の非重複entryは正しかったか

### 14.1 EFFECTIVE_CONTINUATION entry

| Hold | Binance 正しい/n | 正確率 | 中央値bps | HFM 正しい/n | 正確率 | 中央値bps |
|---:|---:|---:|---:|---:|---:|---:|
| 10分 | 298/619 | 48.14% | -0.156 | 290/604 | 48.01% | -0.286 |
| 20分 | 187/395 | 47.34% | -0.338 | 191/383 | 49.87% | -0.226 |
| 30分 | 156/287 | 54.36% | +1.185 | 153/282 | 54.26% | +1.825 |
| 45分 | 113/211 | 53.55% | +1.107 | 108/201 | 53.73% | +1.205 |
| 60分 | 85/165 | 51.52% | +0.483 | 83/161 | 51.55% | +0.202 |

読み方:

- 最初のEFFECTIVE entryは10分／20分では50%未満
- 30分／45分では両市場とも約54%
- 「EFFECTIVEが出たらすぐ短時間で正しい」という結果ではない
- この期間では30〜45分後に方向が現れる割合の方が高かった

### 14.2 TRAPPED_REVERSAL entry

| Hold | Binance 正しい/n | 正確率 | 中央値bps | HFM 正しい/n | 正確率 | 中央値bps |
|---:|---:|---:|---:|---:|---:|---:|
| 10分 | 149/260 | 57.31% | +1.101 | 141/252 | 55.95% | +1.162 |
| 20分 | 107/201 | 53.23% | +1.574 | 103/197 | 52.28% | +1.376 |
| 30分 | 83/166 | 50.00% | +0.171 | 82/160 | 51.25% | +0.568 |
| 45分 | 67/131 | 51.15% | +0.654 | 66/128 | 51.56% | +0.734 |
| 60分 | 51/109 | 46.79% | -0.546 | 52/107 | 48.60% | -0.655 |

読み方:

- TRAPPED reversalは最初の10分entryで最も高かった
- 20分では約52〜53%へ低下
- 30〜45分は約50〜52%
- 60分では両市場とも50%未満
- したがって、この期間のTRAPPEDは「早い反転entry」であり、1時間保有の分析ではない

### 14.3 STALLED pressure probe

| Hold | Binance 正しい/n | 正確率 | 中央値bps | HFM 正しい/n | 正確率 | 中央値bps |
|---:|---:|---:|---:|---:|---:|---:|
| 10分 | 214/430 | 49.77% | 0.000 | 201/404 | 49.75% | -0.127 |
| 20分 | 134/264 | 50.76% | +0.475 | 128/247 | 51.82% | +0.697 |
| 30分 | 102/199 | 51.26% | +0.169 | 96/192 | 50.00% | +0.032 |
| 45分 | 82/146 | 56.16% | +2.077 | 76/138 | 55.07% | +1.698 |
| 60分 | 57/115 | 49.57% | -0.047 | 50/107 | 46.73% | -1.172 |

STALLEDを圧力方向へ読む場合、全window合算では45分だけが両市場で55%を超えた。ただしこれは方向確定ラベルではなく対照probeである。

### 14.4 STALLED reversal probe

| Hold | Binance 正しい/n | 正確率 | 中央値bps | HFM 正しい/n | 正確率 | 中央値bps |
|---:|---:|---:|---:|---:|---:|---:|
| 10分 | 213/430 | 49.53% | 0.000 | 203/404 | 50.25% | +0.127 |
| 20分 | 130/264 | 49.24% | -0.475 | 119/247 | 48.18% | -0.697 |
| 30分 | 97/199 | 48.74% | -0.169 | 96/192 | 50.00% | -0.032 |
| 45分 | 64/146 | 43.84% | -2.077 | 62/138 | 44.93% | -1.698 |
| 60分 | 58/115 | 50.43% | +0.047 | 57/107 | 53.27% | +1.172 |

45分ではpressure probeとreversal probeが明確に反対になった。これは同じSTALLED現象を正反対のsideで評価したためである。良かった側だけを結果後に採用せず、次の期間では事前に方向条件を固定する必要がある。

---

## 15. なぜTRAPPEDの「全decision」と「最初のentry」で逆転したのか

10分結果を直接比較する。

| Market | 状態継続中の全decision | 最初の非重複entry | 差 |
|---|---:|---:|---:|
| Binance | 46.64% | 57.31% | +10.67pt |
| HFM | 46.26% | 55.95% | +9.69pt |

これは、分析名を変えた結果ではない。どちらも同じ`TRAPPED_REVERSAL`方向である。違うのはentry時点の数え方だけである。

考えられる時系列は次のとおり。

1. TRAPPEDが最初に成立する
2. その直後に反転が始まる
3. 状態表示はしばらくTRAPPEDのまま更新され続ける
4. 遅い更新時点では、反転値動きの一部がすでに終わっている
5. そこから新しく10分を測ると方向正確率が落ちる

今回のデータから直接確認できた事実は、最初のentryに限定すると正確率が上がったことである。上記1〜5の細かい価格経路は説明仮説であり、次の分析ではstate初回からの経過秒数別に直接検証できる。

この結果が示すのは、**分析が正しいかどうかと、いつentryするかは同じ問題ではない**ということである。

---

## 16. MFE／MAEから見た価格経路

MFE／MAEはexit最適化のためではなく、entry後にどれくらい有利・不利へ動いたかを確認する補助値として保存した。

| Entry条件 | Market | Hold | 中央MFE | 中央MAE | fixed exit中央値 |
|---|---|---:|---:|---:|---:|
| TRAPPED reversal | Binance | 10分 | +5.690bps | -4.616bps | +1.101bps |
| TRAPPED reversal | HFM | 10分 | +5.635bps | -4.752bps | +1.162bps |
| EFFECTIVE continuation | Binance | 30分 | +8.180bps | -8.245bps | +1.185bps |
| EFFECTIVE continuation | HFM | 30分 | +7.998bps | -7.965bps | +1.825bps |
| STALLED pressure probe | Binance | 45分 | +10.004bps | -7.802bps | +2.077bps |
| STALLED pressure probe | HFM | 45分 | +10.265bps | -7.777bps | +1.698bps |

この表からexit ruleを決めてはいない。MFEとMAEの両方がfixed exit中央値より大きいため、entry後の途中経路には上下動があると分かる。決済最適化は今回の目的外である。

---

## 17. window別に見ると何が起きていたか

全window合算だけではentry時点の違いが隠れるため、両市場で同方向だった主な内訳も示す。これは今回の期間から見つけた探索結果であり、production採用表ではない。

### 17.1 両市場で正確率が比較的高かった内訳

| Source | Window | Entry意味 | Hold | Binance | HFM |
|---|---:|---|---:|---:|---:|
| rolling | 30秒 | TRAPPED reversal | 10分 | 40/64 = 62.50%、med +1.845 | 39/62 = 62.90%、med +1.756 |
| rolling | 30秒 | TRAPPED reversal | 20分 | 29/47 = 61.70%、med +3.244 | 29/46 = 63.04%、med +4.668 |
| rolling | 60秒 | EFFECTIVE continuation | 20分 | 45/75 = 60.00%、med +1.382 | 43/70 = 61.43%、med +1.505 |
| rolling | 60秒 | EFFECTIVE continuation | 30分 | 32/52 = 61.54%、med +2.891 | 32/51 = 62.75%、med +2.979 |
| rolling | 60秒 | EFFECTIVE continuation | 45分 | 23/38 = 60.53%、med +1.816 | 21/36 = 58.33%、med +3.872 |
| rolling | 30秒 | STALLED pressure probe | 30分 | 37/58 = 63.79%、med +1.309 | 34/55 = 61.82%、med +2.112 |
| rolling | 30秒 | STALLED pressure probe | 45分 | 23/39 = 58.97%、med +4.014 | 23/39 = 58.97%、med +4.172 |
| rolling | 30秒 | STALLED pressure probe | 60分 | 20/30 = 66.67%、med +3.465 | 18/29 = 62.07%、med +2.793 |

### 17.2 同じ種類でも不正確だった内訳

| Source | Window | Entry意味 | Hold | Binance | HFM |
|---|---:|---|---:|---:|---:|
| rolling | 300秒 | STALLED pressure probe | 10分 | 15/47 = 31.91%、med -2.172 | 17/45 = 37.78%、med -1.973 |
| native | 10分 | EFFECTIVE continuation | 30分 | 11/27 = 40.74%、med -3.743 | 11/26 = 42.31%、med -3.760 |

300秒STALLEDの同じ10分時点を反転方向で読むと、Binance 68.09%、HFM 62.22%だった。これはSTALLEDがwindowによって突破／反転の意味を変える可能性を示すが、今回の結果を見てから選んだ方向なので、そのまま仕様にはしない。

重要なのは、「TRAPPEDなら常に正しい」「EFFECTIVEなら常に正しい」ではないことである。**状態、window、最初のentry、評価時間の組合せを分けなければ正確性を判断できない。**

---

## 18. 正確率の不確実性

標本数が有限なので、57%や62%を真の固定値として扱ってはいけない。参考として95% Wilson区間を示す。

| Entry条件 | Market | n | 正確率 | 95%区間 |
|---|---|---:|---:|---:|
| TRAPPED reversal 10分・全window合算 | Binance | 260 | 57.31% | 51.23〜63.17% |
| TRAPPED reversal 10分・全window合算 | HFM | 252 | 55.95% | 49.78〜61.95% |
| EFFECTIVE continuation 30分・全window合算 | Binance | 287 | 54.36% | 48.57〜60.02% |
| EFFECTIVE continuation 30分・全window合算 | HFM | 282 | 54.26% | 48.42〜59.97% |

HFMの区間とBinanceの区間を独立標本として合算しない。両方とも同じBTC相場期間を観測しているためである。HFMで同じ方向を再現したことは重要だが、時間的に独立した再試験ではない。

---

## 19. 今回の結果から言えること

### 19.1 言えること

1. Flow eventへ保存されたBinance signal価格は、公式同時刻価格と100%整合した
2. BinanceとHFMの固定時間方向は約96%一致した
3. 全状態・全更新をそのままentryにする方法は正しくない
4. TRAPPED reversalは、状態継続中の全時点より最初の10分entryの方が正確だった
5. EFFECTIVE continuationは、最初の10〜20分より30〜45分の方が正確だった
6. entry時点は分析ラベルと独立して評価する必要がある
7. HFM spreadを適用する前に、方向と時点だけを切り分ける評価は実行できた

### 19.2 まだ言えないこと

1. 実口座で利益が出る
2. HFM spreadを払っても残る
3. 30秒TRAPPED 10分が将来も必ず60%以上になる
4. 今回良かったwindowを選べば完成である
5. 最適なTP／SLが決まった
6. 2,627 unique decisionが完全に独立した2,627相場である
7. 約39時間の中に無かった相場環境でも同じになる

---

## 20. なぜ期間外追試をするのか

期間外追試は、今回の結果を否定するためではない。今回の期間を見た後で選んだ細かい条件が、別の新しい期間でも同じ意味を持つか確認するためである。

今回比較した軸は多い。

- source: rolling／native
- window: 30／60／180／300／900／1800秒
- hypothesis: 4種類
- hold: 5種類
- market: 2種類

組合せが多ければ、その中に偶然60%以上になる小標本が出る可能性がある。特に30秒TRAPPED 10分の62%は有望な探索結果だが、nは64／62である。

期間外追試では、結果を見る前に次を固定する。

1. 対象状態
2. window
3. 最初のentry定義
4. side
5. hold
6. data gap除外条件
7. 正確／不正確の式
8. 合格基準

その後、新しい期間の結果を一度だけ出す。そこで同じ条件が再び正しければ、今回だけの偶然という可能性が下がる。50%前後へ戻れば、今回の期間に依存した条件だったと判断する。

現在の結果のうち、期間外追試を待たずに確定してよいのは、**分析内容とentry時点を別々に評価しなければならない**という設計上の結論である。

---

## 21. 次の工程を細かく分ける

### Phase 1: 追試条件を文章で固定

候補例:

- rolling 30秒の最初のTRAPPED reversal、10分評価
- rolling 60秒の最初のEFFECTIVE continuation、30分評価

ここで候補を増やしすぎない。方向とholdを結果後に変更しない。

### Phase 2: 新しい実データを収集

- Binance Futures公式1分足
- HFM MT5 `#BTCUSDr`実tick
- Flow event
- clock normalization metadata
- missing／gap監査

### Phase 3: ゼロスプレッドで一度だけ再評価

- BinanceとHFMを別集計
- 正しい／不正確／FLAT
- signed return中央値
- MFE／MAE
- 入力除外件数

### Phase 4: 分析・entry時点の判断

- 事前基準を満たす: 正しい候補として次へ
- 満たさない: 不正確または未確定として戻す

### Phase 5: 最後に取引コストを別評価

ここで初めて次を載せる。

- HFM Bid／Ask spread
- commission
- slippage stress
- order方式
- exit設計

spreadで失敗した場合も、「分析が不正確」ではなく「方向とentryは正しいが取引コスト後に成立しない」と原因を分けて記録する。

---

## 22. 再現手順

作業directory: `Delta_Engine_Pro4web`

### 22.1 Binance公式1分足snapshot

```powershell
python tools/snapshot_binance_futures_klines.py `
  --start 2026-07-23T16:55:00Z `
  --end 2026-07-25T07:56:00Z
```

公開market dataだけを読み、認証・注文は行わない。

### 22.2 HFM MT5 tick snapshot

```powershell
python tools/snapshot_mt5_hfm_ticks.py `
  --start 2026-07-23T16:55:00Z `
  --end 2026-07-25T07:55:05Z
```

MT5からの読み取り専用であり、order helperをimportせず、注文関数を呼ばない。

### 22.3 最終評価

```powershell
$env:PYTHONPATH = '.'
python tools/evaluate_analysis_entry_correctness.py `
  --decision-cutoff 2026-07-25T06:55:00Z
```

### 22.4 Test

```powershell
python -m pytest tests -q -p no:cacheprovider `
  --basetemp C:\Users\user\AppData\Local\Temp\deltaengine_analysis_entry_20260725
```

workspace直下には過去セッションが作ったアクセス不能な一時directoryが残るため、正式な`tests/`だけを収集し、通常のユーザーTempを使う。

最終結果:

- 新規対象test: 13 passed
- repository全回帰: 464 passed in 16.72s

---

## 23. 成果物の関係

| File | 内容 |
|---|---|
| `ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_DETAILED_REPORT_20260725.md` | 今読んでいる段階説明用レポート |
| `ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_EVALUATION_20260725.md` | source／window／hypothesis／hold別の全機械集計表 |
| `ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_CHECKPOINT_20260725.md` | 作業経過、blocker、再開位置 |
| `analysis_entry_correctness_20260725.json` | metadataと集計の機械可読結果 |
| `analysis_entry_correctness_20260725.parquet` | 101,784 outcome行の全ledger |
| `binance_futures_1m_20260725.parquet` | Binance公式確定1分足snapshot |
| `hfm_mt5_ticks_20260725.parquet` | HFM実tick snapshot |

---

## 24. 最終要約

今回行ったのは、spreadを克服できるかのテストではない。

1. Flow分析方向が将来価格方向と一致したか
2. 最初の架空entry時点が正しかったか

を、BinanceとHFMの実データで別々に調べた。

結果は次のとおり。

- 全状態を常時entryに使えるわけではない
- TRAPPED reversalは、状態継続中すべてでは不正確だった
- しかし最初の10分entryに限定するとBinance 57.31%、HFM 55.95%
- EFFECTIVE continuationは最初の30分entryで両市場約54%
- window別には60%を超える探索結果もあったが、同期間から選んだため未確定
- 二市場の方向結果は約96%一致
- 注文は一度も送っていない

したがって、今回の中心結論は次の一文になる。

> **分析ラベルだけではentryを決められない。状態が最初に成立した時点と、その後の継続更新を分けることが、正しいentry時点を見つけるために必要である。**
