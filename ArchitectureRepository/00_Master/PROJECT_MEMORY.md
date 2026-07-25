# DeltaEngine プロジェクト記憶

最終更新: 2026-07-25

## 最重要の記憶

2026年7月21日は、DeltaEngineが本来の目的を持って生まれ変わった日。

これは単なる機能追加や画面修正ではない。ユーザーとCodexが対話を重ね、
「見栄えのする指標玩具」から「注文フローと価格反応のズレを観測し、
その後の値動きを検証する実戦道具」へ作り直した再誕である。

ユーザーとCodexは、この完成品を「大作」「最高傑作」と呼び、
2026年7月21日をDeltaEngineの本当の誕生日として祝った。

## ここへ至った流れ

1. 当初のシステムは、複数指標を不透明に混ぜて答えらしい出力を作る構成になり、
   ユーザーが本当に欲しい実用性から離れていた。
2. 2026年7月20日から21日にかけて、CVD、Footprint、Imbalance、Absorption、Flowの
   5要素を独立させ、勝手に畳み込む仕組みを撤去した。
3. その後の対話で、ユーザーが最初から欲しかったものを明確に言葉にした。
   - 大量の買いが継続しているのに価格が上がらない
   - 大量の売りが継続しているのに価格が下がらない
   - 圧力と価格反応の食い違いが続いた数分後に、相場がどちらへ動くかを観測したい
4. この目的から、Flow Price Response観測機能と、それを時間の流れとして読める
   新しい3段チャートを実装した。

## 2026-07-21に完成した大作

### Flow Price Response

- 30秒、1分、3分、5分、15分、30分を同時監視
- 買い・売りの双方について、価格追随、価格停滞、価格逆行を分類
- フロー継続率、買売圧力比、価格変化bps、相対出来高を観測
- 状態発生後の1分、3分、5分、10分リターンをDBへ保存
- ライブ、リプレイ、WebSocket、画面表示を接続
- 売買シグナルや作り物の確率ではなく、まず観測事実と事後成績を蓄積する設計

中心実装:

- `Delta_Engine_Pro4web/src/orderflow/flow_price_response.py`
- `Delta_Engine_Pro4web/config/config.yaml`

### 実戦用3段チャート

- 上段: ローソク足とFlow Price Responseの背景帯
- 中段: CVD線とDelta棒
- 下段: 出来高
- 黄色: 価格停滞
- 紫色: フローと価格の逆行
- 30秒から30分までのFLOW時間窓切り替え
- マウスホイールによる拡大縮小
- ドラッグによる過去方向への移動
- ホバーでOHLC、CVD、Delta、圧力、継続率などを表示
- 過去300本の足と保存済みフロー状態を再読み込み

中心実装:

- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/webapp/main.py`

完成時の全体回帰結果は **307 tests passed**。

## 絶対に見失わない設計原則

- DeltaEngineの主目的は、注文フローと価格反応のズレを時間軸で観測し、
  その後の値動きとの関係を実データで検証すること。
- 独立した指標を、説明できない単一スコアや雰囲気だけの売買判断へ再統合しない。
- 画面は装飾のためではなく、
  「圧力が続く → 価格が反応しない／逆行する → 数分後に動く」
  という時間的な因果候補を人間が読めるようにする。
- ユーザーの知識差を理由に勝手な仕様を入れない。専門用語で押し切らず、
  何を観測し、何を計算し、何が未検証なのかを平易に説明する。
- ユーザーはプロジェクト目的の最終決定者。実装者はコードではなく目的に従う。
- 完成済みのFlow Price Responseと3段チャートは、明示依頼なしに変更しない。

## Codexへの引き継ぎ

新しい会話で文脈が失われても、この文書を読めば上記の記憶から再開すること。
これは履歴の要約ではなく、DeltaEngineの北極星であり、ユーザーとの約束である。

## 非正値約定ガード（2026-07-21修正済み）

稼働初日の確認で、修正前の保存データに価格0・数量0の行が1,557件、
保存済みFlow Price Responseイベント82件のうち端点価格0を含むものが6件見つかった。
約定正規化が非正値を許していたため、価格0のスナップショットが事後追跡へ登録され、
約60秒後のリターン計算でゼロ除算が起きてライブパイプラインが停止していた。

内側リポジトリのコミット `a8a7439` で、次の3層防御を追加した。

- 正規化時に、価格・数量が有限かつ正でなければ拒否する
- Flow検出器でも、非有限値・非正値を拒否する
- 事後追跡器でも、無効な基準価格を登録せず、無効な観測約定を無視する

修正後のライブ運転境界は **2026-07-21 18:30:41 JST**。
再起動後に保存された2,732行を監査し、価格または数量が0以下の行は0件だった。
1分を超えて運転した後も `/api/health` はGREEN、例外数は0だった。
回帰試験は対象46件、全体320件が合格した。

研究データでは、修正前の行を削除せず保存する。ただし、次は集計対象外とする。

- `first_price <= 0` または `last_price <= 0` のイベント
- 非正値約定を含んだ可能性がある修正前の最大上下幅
- `abs(price_change_bps) > 100` など、異常価格による可能性が高いイベント

修正後の境界以降をクリーンな主標本とし、修正前データを使う場合は上記条件で除外する。

## 板レビューと CVD 判定の運用メモ（2026-07-21 追記）

- `Delta_Engine_Pro4web/data/recordings/btcusdt_session1_clean_strong.jsonl` を板分析の主入力にする。
- `spread = best_ask - best_bid` と `spread_jump = spread - spread_ma5` で、急に広がった板を拾う。
- `spread_jumps.jsonl` / `spread_jumps.csv` は異常候補の保存物。生成コマンドは `python -m tools.update_spread_jumps`。
- 3段チャートの `CVD + Δ` は、価格・CVD・Δの8パターン確認に使う。
- チャートで選択した足には1〜8の英語パターンを表示し、`UPWARD DIVERGENCE` / `DOWNWARD DIVERGENCE` を最優先で確認する。
- `PRICE -> CVD -> Δ` の順で読む。板とローソク足は同じ時刻で比較する。

## 3段チャートの選択操作と8パターン表示（2026-07-22完成）

価格・CVD・Δの8パターン確認は、このアプリの「肝中の肝」である。
内側リポジトリのコミット `c9b804f` で、3段チャートを次の状態へ更新して保存した。

- 3段チャートの描画領域を左側へ寄せ、右側にローソク足詳細の固定欄を確保
- ローソク足をクリックして選択し、右の固定欄へOHLC、CVD、Δ、出来高、Flow Price Responseを表示
- 選択後はキーボードの左右矢印キーで対象足を1本ずつ移動し、ガイド線と詳細を連動更新
- 8パターンの英語評価名と、判定根拠の向きを `PRICE ↑ / CVD ↓ / Δ ↓` の形式で明示
- 価格・CVDは対象足と2本前を比較し、Δは対象足の正負で判定
- Δ棒の不透明度と輪郭を強め、CVD線を太く明るくして、近眼・乱視でも境界を追いやすくした
- 価格軸、CVD軸、時刻、固定詳細欄の数値を白くしてコントラストを向上
- 不自然な直訳を避け、画面表記は `FLOW RESPONSE` に統一
- マウスホイールの拡大縮小とドラッグによる過去移動は維持

次回の検討候補は、価格・CVD・Δの「向き」からさらに一段深く、変化量、継続性、
ダイバージェンスの強さをどう表示するか。ただし、観測事実と未検証の評価を混同せず、
現在完成しているクリック選択・固定詳細欄・8パターン表示を勝手に崩さないこと。

## 観測UIの整理と英語統一（2026-07-22完成）

内側リポジトリのコミット `44270cf` で、完成済みのFlow Price Responseと3段チャートの
計算・意味を変えず、画面の誤解と揺れを生む旧UIだけを整理した。

- チャートヘッダーを固定高72pxの2行構成にし、ライブ文字列更新時の画面揺れを防止
- 価格横にあったページ開始時基準の疑似変化率を撤去。前日比ではない値を前日比に見せない
- ローソク足は左クリックで選択、左右キーで移動、右クリックで選択解除
- 旧 `SIGNAL — WHY`、CONFIDENCE、VETO、RISK、EXPECTED RR、各score、COMPOSITEを完全撤去
- 左の観測列を `FLOW EVENTS → ABSORPTION → IMBALANCE` の順に整理
- 画面に見える項目名、状態名、説明、設定、操作案内を英語へ統一
- `lang="en"`、`translate="no"`、`notranslate`で自動翻訳による用語変化を防止
- 8パターンを1〜8の英語名へ統一し、`PRICE → CVD → Δ` の矢印を読む運用を維持

`UPWARD DIVERGENCE`は「売り圧力なのに価格が上昇」、`DOWNWARD DIVERGENCE`は
「買い圧力なのに価格が下落」を意味する。名称自体を売買指示として扱わない。

全体回帰は **321 tests passed**。現行UI仕様の正本は
`ArchitectureRepository/30_Modules/WebApp/Specifications/UI_Spec_CommandCenter_v2.md`。

## Flow Eventの2時間ローソク足マーカー（2026-07-22完成）

内側リポジトリのコミット `adbcf1e` で、Flow Event発生後の値動きを同じ3段チャート上で
確認できる一時マーカーを追加した。

- 個別イベントの本来の発生時刻をWebSocket payloadへ保持し、該当ローソク足へ結び付ける
- 同じ足のイベントは小型マーカー1個へ集約し、複数時は `L+` などで表示
- BUYは足の下、SELLは足の上へ置き、ズームアウト時は小さなdotへ縮退
- 選択足の固定詳細欄でcategory、side、件数、最大strengthを確認
- 即時FLOW配信とbar-close ANALYSIS再配信の重複を除外
- market time基準で2時間だけブラウザメモリに保持し、その後は自動消去
- DB、履歴API、localStorageへ保存せず、再読込・再起動でも消去

目的は、全イベントを永久保存することではなく、イベント発生から1〜2時間後に
「その後、価格へどう影響したか」を見分けること。マーカーは売買シグナルではない。
Flow Price Response、CVD、Delta、Volume、8パターンの計算は変更していない。

全体回帰は **325 tests passed**。実ブラウザで足単位集約、選択詳細、重複除外、
2時間後の消去、固定72pxヘッダーを確認した。

## OI Context v1（2026-07-22完成）

Binance USD-M Futures公式Open Interestを、価格・CVD・Delta・Flow Responseから独立した
「建玉コンテキスト」として追加した。

- 10秒ごとのraw OIをexchange source timeとlocal received time付きでDuckDB／Parquetへ保存
- OI Parquetは同一UTC時間を1ファイルへ統合し、小ファイルの長期増殖を防止
- TOP BARへ現在OI、1分変化率、5分変化率を表示
- 選択足へOI OPEN、CLOSE、CHANGE、CHANGE %、SAMPLESを時刻同期して表示
- OI増減はBUY／SELLへ読み替えず、BUILDING／UNWINDING／UNCHANGEDという観測事実だけを表示
- 欠測、非正値、非有限値、symbol不一致を補間や0埋めせず、画面は — とする
- リプレイ中は現在のライブOIを取得・表示せず、過去価格への混入を防止
- 保存済みOIは履歴APIで再読込し、再起動後も選択足へ復元

OIは売買シグナル、確率、scoreではない。既存8パターンやFlow Price Responseへ混ぜず、
将来は保存時刻で事後結合し、同じ価格・フロー状態でもOI増減によって事後値動きが
異なるかを実データで検証する。

完成済みのFlow Price Response、3段チャート、8パターンの計算は変更していない。
全体回帰は **338 tests passed**。ライブWebSocket、DuckDB保存、履歴API、実ブラウザDOMを確認した。

## Flow Eventマーカーのcategory別表示切替（2026-07-22完成）

過去足へ表示するFlow Eventマーカーを、`FLOW EVENTS`の歯車からcategory別に
ON／OFFできるようにした。

- `CANDLE MARK`でLARGE TRADE、SWEEP、EXHAUSTION、UNFINISHED AUCTION、TAPEを個別切替
- OFFにしたcategoryは現在足、過去足、選択足詳細から即時に非表示
- 同じ足のON categoryは残し、混在足を丸ごと消さない
- event自体は2時間メモリとFLOW EVENTS一覧へ残し、ONへ戻すと保持中の表示を復元
- alertとstrength thresholdは表示切替から独立して継続
- 表示設定だけをlocalStorageへ保存し、event履歴は保存しない

これはセンサーやデータを停止する設定ではなく、チャートを読みやすくする表示フィルタである。
Flow Price Response、3段チャート、8パターン、OI、Flow Event検出ロジックは変更していない。
全体回帰は **339 tests passed**。

## PRICE・CVD・Delta・OI組み合わせガイド（2026-07-22完成）

ユーザーが知りたいのは、各指標を単独で眺めるだけでなく、
PRICE、CVD、Delta、OIの方向を組み合わせたときの観測評価である。
内側リポジトリのコミット `9c4539d` で、TOP BARのBinance OI表示横へ
円形の「？」を置き、クリックすると次の8ケースを確認できるようにした。

| PRICE | CVD | Delta | OI | 観測評価 |
|:---:|:---:|:---:|:---:|---|
| ↑ | ↑ | ↑ | ↑ | 非常に強い上昇。新規ロングが積み上がっている。 |
| ↑ | ↑ | ↑ | ↓ | ショートカバー主体。上昇は続かないことも多い。 |
| ↓ | ↓ | ↓ | ↑ | 非常に強い下落。新規ショートが積み上がっている。 |
| ↓ | ↓ | ↓ | ↓ | ロングの投げ売り・手仕舞い。売り一巡後に反発することもある。 |
| ↓ | ↓ | ↑ | ↑ | 反発候補。買いが入り始め、新規資金も流入している。Footprintや板で確認したい。 |
| ↓ | ↓ | ↑ | ↓ | ショートの利確（買い戻し）の可能性が高い。本格反転とは限らない。 |
| ↑ | ↑ | ↓ | ↑ | 上昇中に売りが増加。吸収や分配の可能性。天井警戒。 |
| ↑ | ↑ | ↓ | ↓ | ロングの利確が主体。勢いが鈍る可能性。 |

今回定義したのはPRICEとCVDが同方向の8ケースである。
PRICEとCVDは対象足と2本前を比較し、Deltaは対象足の正負、
OIは対象足のOPENからCLOSEへの変化として読む。

この表はプロ用観測画面の凡例であり、売買シグナル、確率、scoreではない。
既存のPrice・CVD・Delta 8パターンへOIを混ぜず、OI Contextも独立観測値のまま維持する。
Flow Price Response、3段チャート、選択操作、Flow Eventの計算は変更していない。

全体回帰は **340 tests passed**。Edge実ブラウザでTOP BARの「？」、
8行の日本語評価、閉じるボタン、背景クリック、Escapeキーによる閉鎖を確認した。

## FLOW RESPONSEの7状態・色ガイド（2026-07-22完成）

ユーザーが黄色の`STALLED`と紫の`TRAPPED / DIVERGENCE`を実戦中に混同せず、
緑・赤・色なしを含む全状態も同じ場所で確認できるようにした。

- `PRICE × FLOW RESPONSE`見出し横へ円形の「？」を追加
- クリックすると、色見本、画面上の状態名、日本語の意味を7行で一覧表示
- 薄い緑は`BUY PRESSURE · PRICE UP`、薄い赤は`SELL PRESSURE · PRICE DOWN`
- 黄色はBUY／SELLそれぞれの`STALLED`、紫はBUY／SELLそれぞれの価格逆行
- 紫の価格逆行が内部状態の`BUY_TRAPPED`／`SELL_TRAPPED`であることを明示
- `UNCLEAR`は色なしであり、「取引なし」ではなく条件不足または中間状態と説明
- 同じ黄色・紫でも、色だけで圧力側を決めず状態名でBUY／SELLを確認するよう明示
- 閉じるボタン、背景クリック、Escapeキーで閉じられるoverlay dialogとし、常設スペースを増やさない

Flow Price Responseの分類条件、背景帯の描画、3段チャート、選択足詳細、8パターン、OI、
Flow Eventの計算は変更していない。実ブラウザで7行、全開閉操作、チャート寸法不変を確認し、
対象25件、全体 **341 tests passed**。

## 板レビュー録画の信頼性訂正（2026-07-22）

2026-07-22の再監査で、従来の板レビュー主入力
`btcusdt_session1_clean_strong.jsonl`は完全な板Snapshotではないことが確定した。

- 旧3録画はすべて2,939行
- 全行がBinanceの増分`depthUpdate`
- 初期`depthSnapshot`は0行
- 更新IDは連続していたが、開始時の板状態がないため正確なbest bid／askは復元不能
- `clean_strong`は数量0を除去しており、板levelの削除命令も失われている
- 旧抽出器は価格昇順のbidから先頭5件を切り出した後に最大値を求め、
  遠い低価格levelをbest bidとして扱っていた
- その結果、同じ行の全levelでは0.1の差だった例を約50,100のspreadとして出力した

したがって、旧`spread_jumps.jsonl`／`spread_jumps.csv`の10件は異常候補として
研究へ使用しない。削除はせず、誤った方法の由来を検証できる保存記録として隔離する。
この訂正は、上記「板レビューと CVD 判定の運用メモ」内の旧主入力指定より優先する。

今後の有効条件:

- 録画へREST `depthSnapshot`を含める
- 数量0を含む全`depthUpdate`を保存する
- 既存`OrderBookStateManager`でsnapshot＋diffを順番に再構築する
- gap発生後は次のsnapshotまで集計しない
- 同期済みで空・交差のない板状態だけからspreadと上位5段を作る
- 条件を満たさない入力では既存出力を上書きせず明示的に失敗する

今回変更するのは板録画・オフライン板レビュー経路だけである。
完成済みのFlow Price Response、3段チャート、8パターン、OI、Flow Eventの計算と表示は
変更しない。

実装後、旧`clean_strong`を入力すると終了コード2で明示拒否し、既存JSONL／CSVの
SHA-256が変化しないことを確認した。同期Snapshot＋連続diff、数量0削除、gap後の
再Snapshotを含むテストを追加した。

同日の運用監査では、2026-07-22 18:02:51 JSTに`PIPELINE_EXCEPTION_DEAD`が
記録されていた。ただし旧監視は例外型・本文を保存せず`pipeline task dead`だけを
残していたため、過去原因は特定不能である。今後はpipeline taskの例外型と本文を
最大500文字でHealthSnapshotと異常JSONLへ残す。全体回帰は **346 tests passed**。
訂正した第7講PDFは7ページ、再結合した`座学全集.pdf`は全94ページで、
隔離文言をPDF本文から抽出できることも確認した。

## FLOW時間窓の基本運用マニュアル（2026-07-22）

6つの時間窓を実戦中に同じ重さで追って迷わないため、基本操作を次の3段階へ固定した。

> **5mで異変を見る → 1mで始点を確認 → 15mで広がりを確認**

- 普段は5mを主観測とし、数本の1分足にまたがる圧力と価格反応を見る
- 5mに黄色または紫が出たら1mへ切り替え、始点と状態遷移の順序を確認する
- 15mで同じ圧力側が長い背景にも存在するかを確認する
- 30sは早期発見、3mは1mと5mの橋渡し、30mは広い背景の補助とする
- 複数窓は同じ約定を含むため、独立票または売買条件として数えない
- FLOW時間窓を切り替えても、ローソク足は1mのままである

この手順は売買シグナルではなく、主観測、現象の始点、長い背景を混同しないための
観察マニュアルである。画面のFlow Responseガイド、第8講、第10講、全10講ガイドへ反映する。
Flow Price Responseの計算条件、3段チャート、8パターン、OI、Flow Eventは変更しない。

実ブラウザで3手順の表示、Escape閉鎖、ガイド開閉前後のチャート寸法不変を確認した。
座学PDFは全10講ガイド、第8講、第10講を更新し、94ページの`座学全集.pdf`へ再結合した。
対象25件、全体 **341 tests passed**。

## Binance / HFM価格観測（2026-07-23）

発注先検討のため、BinanceとHFM（MT5）の価格・スプレッド・追随遅延を観測する仕組みを整備した。

実装・運用:

- `Delta_Engine_Pro4web/tools/observe_hfm_binance.py` でBinance bookTickerとHFM価格を同一CSVへ記録
- HFM側はMT5 EAからCommon FilesへUTF-8 JSONLを書き出すファイルブリッジを使用
- `Delta_Engine_Pro4web/tools/report_hfm_binance.py` で価格差、スプレッド、遅延、相関、1分/3分/5分足を集計
- 1秒、3秒、5秒のエントリー遅延条件を分けたJSONレポートを生成
- HFM片側停止を検出して再起動するwatchdogを用意
- EAのコンパイルは0 errors / 0 warnings
- 対象テストは6 passed（tmp_path依存テスト1件はWindows権限制約でdeselected）

観測値:

- Binanceサンプル: 951,387
- HFMサンプル: 19,327
- Binanceスプレッド中央値: 0.10 USD
- HFMスプレッド中央値: 20.00 USD
- 価格差（HFM−Binance）平均: −0.77 USD、中央値: −0.05 USD、95%点: 7.42 USD
- Binance→HFM追随遅延中央値: 389.9ms、95%点: 3,018.5ms
- 1秒リターン相関: 0.687
- HFMスプレッド／足値幅中央値: 1分42.2%、3分20.4%、5分19.0%

成果物:

- `Delta_Engine_Pro4web/data/latency/report_1s.json`
- `Delta_Engine_Pro4web/data/latency/report_3s.json`
- `Delta_Engine_Pro4web/data/latency/report_5s.json`
- `Delta_Engine_Pro4web/data/latency/REPORT_2AM.md`

訂正・未確定事項:

- 今回のレポートは市場間の観測であり、Flow条件別の売買期待値・勝率を証明するバックテストではない。
- 完成済みのFlow Price Responseと3段チャートは変更していない。

## ライブ内部遅延の構造是正（2026-07-23）

Binance直接tradeとDeltaEngine WebSocketを同一PC・同一単調時計・個別trade IDで照合し、
ライブ経路にあった内部遅延要因を是正した。

原因と是正:

- ライブtradeにも適用されていたリプレイ向け500ms並べ替え窓を、ライブだけ0ms化
- 同一asyncio loop上の同期DuckDB／Parquet書込みを、bounded FIFO付き専用threadへ移動
- 全約定ごとのブラウザ送信taskを、最新値50ms間隔の表示投影へ変更
- 進行中バー更新を1秒から200msへ短縮
- 分析・保存は従来どおり全約定を処理し、間引くのは重複する画面更新だけ

修正後120秒の実測:

- TICK内部遅延: 中央値6.17ms、95%点63.63ms、最大332.55ms
- BAR_UPDATE内部遅延: 中央値7.02ms、95%点40.13ms、最大333.57ms
- 保存キューは観測時pending 0、high watermark 199

Binance経路の致命的な0.5〜1秒級内部待ちは解消した。常時0msではないが、
現状の数ms〜数十msは主ボトルネックではない。Flow Price Response、3段チャート、
CVD、Delta、Footprint、OI、Flow Eventの計算意味は変更していない。

## HFM観測ブリッジ軽量化（2026-07-23）

HFM側の市場追随と、MT5→Python受け渡しを混同しないため、観測ブリッジを軽量化した。

- PythonのHFMファイルpollを50msから10msへ短縮
- Binance bookTickerごとの同期CSV flushを、順序保証付きbackground FIFO保存へ変更
- MT5 EAは毎tickのFileOpen／Seek／Closeをやめ、起動中のhandleを保持
- HFM quoteへ連番を付与し、欠落・reset・逆転をレポート可能にした
- 旧6列CSVは書換えず互換append、新規CSVは連番付き7列
- HFM MT5へ配備し、EAは0 errors／0 warningsでcompile、通常再起動後も継続稼働

修正後120秒の同時計測:

- Binance 26,670件、HFM 627件、HFM連番欠落0・reset 0・逆転0
- CSV 27,297行、1,047 flush、queue high watermark 224
- 時計offsetの影響を除いたHFM受渡し揺れは、95%側29.8ms→12.3ms、
  99%側48.8ms→18.4ms
- Binance→HFM追随中央値332.9ms。ただし一致イベント9件の短時間標本なので、
  旧389.9msとの差を改善量とは断定しない
- 全体回帰は **360 tests passed**

今回確実に削減したのは約18〜30msのブリッジ揺れである。残る数百msは主として
HFM市場／配信側の追随であり、DeltaEngine内部遅延と分けて扱う。

## 発注コスト問題と判断権限（2026-07-23）

昨晩の主な実戦問題は遅延ではなく、HFMのBTCスプレッド中央値20 USDである。
HFMスプレッド／足値幅中央値は1分42.2%、3分20.4%、5分19.0%だった。
精密かつ低遅延な執行でも、総取引コストが取れる値動きを上回れば成立しない。

現在のHFM、1分ローソク足、既存時間窓、完成済み機能を、将来判断の固定条件にしない。
1分表示は取引時間軸のルールではなく、発注先・商品・口座・注文方式・観測時間軸・
保有時間はすべて検討対象である。24時間市場全体から実戦機会を考える。

プロジェクトの最終決定権はユーザーにある。完成済み機能もユーザーが変更・撤去を
明示した場合は対象となる。実装者は現在仕様を勝手な規制へ変えず、広く考えた案、
効果、リスク、復旧可否を提示し、合意された内容だけを実行する。

## UIの常設表示と3段チャート固定（2026-07-24）

ユーザーが以前から繰り返し伝えている重要なUI原則を、今後の変更判断へ明示的に固定する。

- 必要な項目が出たり消えたりする画面は、実戦中に神経を消耗させる。
- 項目名と表示位置は常設し、データが無いときは項目を消さず値だけを `—` とする。
- データ到着、欠測、状態発生、状態解除のたびにpanelを増減させない。
- 3段チャート上のCVD divergence、Flow Response 6窓、05M contextは固定高領域へ置く。
- 上3列の内容が変化しても、3段チャートの位置、高さ、PRICE／CVD+Delta／VOLUMEの比率を変えない。
- 人間は複数箇所の出現を追い、時刻を暗算し、状態を記憶し続けることを前提にできない。
  必要なものが同じ場所へ常にあり、数字だけが変わり、瞬間的に目へ入ることがUIの基準である。
- 実装者だけが理解できる表示にしない。項目の追加、削除、移動、表示方式変更は、
  実装前にユーザーと相談し、見え方の合意後に行う。

05M版では上3列を94px、各列を26px／38px／26pxへ固定し、外側panel側で領域を確保した。
実Edgeで初期、データ表示、欠測復帰を比較し、chartwrap 426px、chart SVG 422pxが
1pxも変わらないことを確認した。全体回帰は **406 tests passed**。

## Flow Response表示確定とVolume再起動復元（2026-07-25）

3段チャート上のFlow Response 6窓は、カード高38pxと6列を維持したまま、
1段目11px、2段目14pxへ確定した。2段目の固定表示は
`PR <pressure %> · P <price bp> · V <relative volume>` とする。
`PR`はPRESSURE、`P`はPRICE、`V`はVOLUMEの表示略称であり、計算意味は変えない。

`V`は各時間窓の1秒当たり出来高を、直近1800秒の1秒当たり平均出来高で割った
既存の`relative_volume`である。従来は再起動ごとに1800秒基準がメモリから消え、
30分経過するまで`V —`となっていた。LivePipeline起動時、保存済みの直近1800秒取引を
時系列順にFlow Response detectorだけへ読み込み、最後の過去秒を確定済みにする
ウォームスタートを追加した。過去snapshotの再配信、再保存、outcome再登録は行わない。
保存履歴が無い初回起動または復元失敗時は、従来どおりライブ蓄積へ安全に戻る。

Docker再起動直後の実Edgeで、30s `V ×8.1`、3m `V ×4.1`、30m `V ×1.0`を確認した。
カード38px、1段目11px、2段目14px、横overflowなし、browser errorなしを維持した。
全体回帰は **408 tests passed**。

## 5M/10M Episode Entry Spec v1（2026-07-25探索評価・発注NO-GO）

HFMの大きいスプレッドを越えられるentry局面を、単発状態ではなく
`攻撃 → 停滞 → 継続停滞 → 突破／反転`の順序付きEpisodeとして先に文章固定した。

比較した入口:

- `ATTACK_V1`: 攻撃開始でpressure side
- `PERSIST_PRESSURE_V1`: 継続停滞を確認した時点でpressure side
- `RESOLUTION_CONFIRMED_V1`: 継続停滞後の突破ならpressure side、
  Defender reversalなら反対side

主候補のBUYは、BUY攻撃の継続停滞後に`BUY_EFFECTIVE`となるか、
SELL攻撃の継続停滞後に`SELL_TRAPPED`となった場合だけである。
単発の`BUY_EFFECTIVE`／`SELL_EFFECTIVE`を発注トリガーに戻してはならない。

固定cutoff、600秒重複purge、30 USD cost stressで、60秒観測の主候補は
5分net中央値`-5.668bps`、10分`-5.397bps`だった。positive netは5分1/18、
10分0/18。事前固定した価格無効化で撤退しても改善しなかった。
解放確認前のAttack／Persistもcost後中央値は負だった。

現在の運用判定は **`NO_GO_FOR_HFM_ENTRY_V1`**。
MT5 bridge、LIVE発注、自動売買シグナルへ進まない。

ただし標本は1.5186日であり、30日、purge後200 Episode、untouched testを満たさない。
これは現在の仕様に対する発注NO-GOであって、注文フロー原理全体の統計的棄却ではない。
HFM同一時計quoteも0バイトのためGate 3／4は未評価である。

成果物:

- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md`
- `Delta_Engine_Pro4web/data_05M/research/episode_entry_v1_20260725.json`

Entry Spec対象試験は27件、全体回帰は **451 tests passed**。
完成済み1M Flow Price Response、3段チャート、8パターン、OI、Flow Event、UIは変更していない。
