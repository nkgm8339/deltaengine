# DeltaEngine プロジェクト記憶

最終更新: 2026-07-26

## 最重要の記憶

### クライアントであるユーザーの意向が最優先

このプロジェクトのクライアント、目的決定者、完成条件の決定者、最終採否の決定者は
ユーザーである。ユーザーの最新の明示意向は、過去文書、過去policy、エージェントの都合、
実装しやすさ、試験しやすさより常に優先する。

ユーザーの趣旨を勝手に狭める、一部だけ実装して全体を完成扱いする、求められた最終目的を
実装者に都合のよいproxy問題へ置き換える、過去文書を使って最新指示を無効化することを
絶対に行わない。曖昧さが目的・完成条件を変える場合は、原文を引用してユーザーへ確認し、
勝手に方向を決めない。

テスト件数、コード量、処理時間は目的達成の証拠ではない。ユーザーが求めた成果へ
実際につながっているかを完成判断の基準とする。確認済み事実、未確認事項、検討候補を分け、
未確認の内容を完成・成功・有効と断定しない。

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


## 分析正確性・entry時点正確性のゼロスプレッド評価（2026-07-25）

本プロジェクトで最初に明らかにする対象を、次の二つへ明示的に分離した。

1. 観測時点の分析方向が、その後の実価格方向と一致したか
2. 同じ分析内容でも、最初に架空entryする時点が正しかったか

この段階ではspread、手数料、slippage、TP／SL、動的決済を一切使わない。
10／20／30／45／60分後の固定価格だけで評価する。従来のHFM spreadを理由にした
`NO_GO_FOR_HFM_ENTRY_V1`は、cost込みの当該Episode仕様にだけ有効であり、
分析またはentry時点が不正確という結論へ拡張してはならない。
spread適用は、分析とentry時点の正確性を確認した後の別工程である。

重要な入力訂正:

- 「HFM同一時計quote 0 bytes」はworkspace内bind targetをhost sourceと誤認した結果だった
- 実データはMT5 Common Filesに63MB以上あり、MT5 history APIも利用可能だった
- HFM server clockは保存済み対応点199件とlive sample 20件でUTCとの差+10,800秒を確認
- HFM実tick 594,229件をsnapshot化。期間は
  `2026-07-23T16:55:00.183Z`〜`2026-07-25T07:55:04.962Z`、120秒超gap 0
- Binanceローカル生約定とローカル1分足には収録停止区間があったため、正確率の分母へ混ぜない
- BinanceはFlow eventに保存済みのsignal実約定価格をentryに使い、公式Futures公開APIの
  確定1分足2,341本をfixed exitとMFE／MAEへ使用。missing 0、duplicate 0、gap 0
- signal実価格6,234観測は、すべて公式同時刻OHLC範囲内だった

固定cutoff `2026-07-25T06:55:00Z` の結果:

- Flow direction decision 9,208
- 全decision outcome 92,080（rolling重複を含み、独立取引数ではない）
- 非重複entry outcome 9,704（Binance 4,852、HFM有効4,651）
- 同一decisionの市場間方向結果一致は、全decision 95.83%、非重複entry 95.94%
- signed return相関は全decision 0.993651、非重複entry 0.992723
- 注文送信0

分析内容とentry時点を分けた主要結果:

- `TRAPPED_REVERSAL` 10分は、状態が続く全更新を数えると
  Binance 46.64%／HFM 46.26%
- 同じ`TRAPPED_REVERSAL`を最初の非重複entryに限定すると
  Binance 57.31%（n=260、中央値+1.101bps）／
  HFM 55.95%（n=252、中央値+1.162bps）
- `EFFECTIVE_CONTINUATION`の最初の非重複entryは30分で
  Binance 54.36%（n=287、中央値+1.185bps）／
  HFM 54.26%（n=282、中央値+1.825bps）
- STALLEDのpressure／reversalは方向確定ではなく対照probeである。45分のpressure側は
  Binance 56.16%／HFM 55.07%だったが、探索後に良い側だけを確定仕様へ採用しない

この結果は、全状態を常時entryに使えるという意味ではない。むしろ、同じ分析ラベルでも
継続中の全更新と最初のentryでは正確率が変わり、entry時点の選別が独立して必要だと確認した。
30s TRAPPED 10／20分、60s EFFECTIVE 30分など両市場で同方向の高い探索値もあるが、
約39時間の同一期間から見つけた候補なのでproduction仕様へ凍結しない。期間外データで
事前固定した条件を追試し、正しい／不正確を判定する。

成果物:

- `ArchitectureRepository/00_Master/ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_CHECKPOINT_20260725.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_DETAILED_REPORT_20260725.md`
  - 目的から結論まで24段階に分けた人間向け説明書
  - 用語、1件の判定例、重複除外、分母、lag、全aggregate、期間外追試の意味を含む
- `ArchitectureRepository/00_Master/ORDERFLOW_ANALYSIS_ENTRY_CORRECTNESS_EVALUATION_20260725.md`
- `Delta_Engine_Pro4web/data_05M/research/analysis_entry_correctness_20260725.json`
- `Delta_Engine_Pro4web/data_05M/research/analysis_entry_correctness_20260725.parquet`
- `Delta_Engine_Pro4web/data_05M/research/binance_futures_1m_20260725.parquet`
- `Delta_Engine_Pro4web/data_05M/research/hfm_mt5_ticks_20260725.parquet`

新規対象試験13件、全体回帰 **464 tests passed**。
完成済み1M Flow Price Response、3段チャート、8パターン、OI、Flow Event、UIは変更していない。

## 統合ENTRY GO未完成とFlow単体発注の撤回（2026-07-26）

2026-07-26、Flow Price Response単体の初回状態遷移をBUY/SELLへ変換し、HFM発注へ
接続するsidecarを実装した。しかしこれはCVD、divergence、Footprint、Imbalance、
Absorption、Flow Event、Liquidation、8パターン、OI、native 5m/10m分析を
発注根拠へ使用していなかった。

コード監査で確認済みの事実:

- `src/orderflow/signal.py`の`SignalEngine`はretired composite engineのcompatibility shellで、
  `evaluate()`は固定`WAIT / confidence 0 / NO_INPUT`
- `src/ai/analysis.py`の`AnalysisEngine.evaluate()`は固定`NEUTRAL / confidence 0`
- `src/pipeline.py`は独立指標設計により`CVD / Footprint / Imbalance`のscoreを明示的に
  `None`として旧SignalEngineから外している
- 各分析器は計算・保存・表示されるが、説明可能な現象別ENTRYトリガーへ統合する層は存在しない

したがって「分析から自動発注まで完成」という報告は撤回する。
Flow単体sidecarはENTRYロジックとして採用禁止。execution plumbing、audit、dashboard部品は、
将来ユーザーが承認した統合GOへ接続するときの再利用候補にすぎない。

2026-07-26 01:24 JSTの確認済み状態:

- Flow単体check sidecar停止
- port 18081停止
- HFM position 0
- HFM pending order 0
- MT5 algorithmic trading OFF
- LIVE注文0件

次セッションは実装や大量テストから始めない。まず、相場現象ごとにENTRYトリガーを
何種類へ分けるべきかを、既存moduleの意味、event time、保存済み実データから真剣に設計し、
主発火条件、confirmation、反対根拠、hard reject、expiry、duplicate、re-arm、
entry時刻を詳細に報告する。「5つか6つ」は例であり、数を先に固定しない。

詳細引継ぎ:

- `ArchitectureRepository/00_Master/ORDERFLOW_ENTRY_TRIGGER_DESIGN_HANDOFF_20260726.md`

## Step 2 trigger outcome集計と第一関門（2026-07-26）

Flow Response単体の方向仮説を、保存済み新05M 44,529 outcome、旧1M 46,492 outcome、
合計91,021 outcomeとHFM 553件でread-only集計した。

- 新旧期間のcell一致率相関は`-0.025`で、一貫した再現性を確認できなかった
- HFM net中央値は確認した全cellで負だったが、spreadを含むため分析方向の正確性と分ける
- OI、native flowには局所差があったが、context間で一貫した改善は確認できなかった
- Absorption、Large Trade、Sweep、Liquidationなどは当時の永続履歴がなく、
  統合confluenceの事後検証は未実施
- この結果はFlow Price Response観測機能の否定ではなく、Flow状態単体をENTRYへ変換する仕様の
  production採用根拠が無いという第一関門判定である
- LIVE注文0件

raw authoritative snapshot 459件、115.10 MiBは削除せずlocal research evidenceとして保持する。
Gitには最終CSV 9件とinput manifestだけを保存し、DuckDB／WALのSHA-256は
`ORDERFLOW_TRIGGER_OUTCOME_STEP2_CHECKPOINT_20260726.md`へ記録した。

## Flow単体execution prototypeの強制停止境界（2026-07-26）

Flow単体sidecarの履歴と将来再利用可能なMT5 gateway部品は保存するが、誤起動を防ぐため
`FlowExecutionController`は`live`を例外拒否し、CLIも`observe / check`だけを受理する。
Flow単体mappingから`order_send`へ到達するLIVE経路はfail closedである。

将来、ユーザーが承認した説明可能な統合ENTRY GOが完成した場合だけ、独立した
`Mt5MarketOrderGateway`をその統合層へ接続する。prototypeの存在を発注承認と解釈しない。

## Hook Stage 2A append-only観測基盤（2026-07-26完成）

板、約定、清算、OI、価格構造などを将来の統合triggerとして検証できるよう、
発注から独立したHook観測基盤のStage 2Aを実装した。

- 共通Hook契約と88種のregistryを追加
- threshold未較正、hash不一致、quality不成立ではfail closed
- raw market eventを順序付きXZ segmentへappend-only収録
- segment summary、SHA-256、sequence、session validityをreplayで検証
- Hook専用storageを既存DB／Parquetから分離
- `LivePipeline`のoptional raw tapとして接続し、tap失敗時も市場pipelineを継続
- `/api/stats`へcapture状態を追加
- 既存Flow Price Response、3段チャート、8パターン、OI、Flow Eventの計算・表示は変更なし
- playbook発火、Flow単体発注、LIVE注文への接続なし
- 対象回帰36件合格

Stage 2Aはデータ収録と共通契約の完成であり、統合ENTRY GOの完成ではない。
A/C/D/E/F/G detector、閾値較正、playbook選抜、期間外成績、check／LIVE移行は別段階である。
Stage 2Bは2026-07-26に完了した。詳細は次節と
`ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_STAGE2B_COMPLETION_REPORT_20260726.md`
を正本とする。

## Hook Stage 2B耐障害化・自動復旧・detector基礎（2026-07-26完成）

Hook観測基盤を、PC再起動やprocess不意停止を含めて継続運用できる状態へ更新し、
A/C/D/E/F/Gの較正前detectorを実装した。

- XZを最大1秒の独立frameへ分割し、data fsync後にmanifestの`FRAME_COMMIT`をfsync
- summaryなしcrash sessionでもcommit済みframeのhash、件数、sequenceを検証して回収
- 未commit tailは削除せず明示除外
- coverageと停止延長をappend-only台帳へ記録し、original deadlineを改変しない
- Windows Scheduled TaskからDocker、Compose、health、同一campaignを1コマンドで自動復旧
- 二度目の実機再起動でTask結果0、GREEN、新session、durable増加を人手起動なしで確認
- boot前full session 126,707件、6,406 frameを全件replayし、tail 0 byte
- DOM／interaction／Flow transition／liquidation／OI／価格構造の56 Hook候補を実装
- stale、DOM gap、crossed book、future-dataをcandidate生成前に拒否
- r3 image内DOM benchmarkはp99 4.314ms、max 12.733ms
- 全体回帰 **516 tests passed**
- 完成済みFlow Price Response、3段チャート、8パターン、UIの変更なし

全thresholdは`UNCALIBRATED`、HookEvent発火0、Playbookは`OBSERVE`、
`execution_enabled: false`である。Stage 2B完成は統合ENTRY GOや自動発注の完成ではない。
収録完了、較正、HookEvent解禁、Playbook選抜、期間外評価、Stage 2C、check／LIVE移行は
別工程であり、ユーザー確認前に進めない。

## Hook Stage 2C着手承認と2C-1待機境界（2026-07-26）

ユーザーは2026-07-26にStage 2B完了を確認し、Stage 2C着手を承認した。
正本承認書は
`ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_STAGE2C_START_APPROVAL_20260726.md`。

Stage 2Cは、収録完了判定、gate合格Hookのthreshold較正、replay発火頻度検証、
ユーザー承認後のobserve発火解禁を順番に行う。fullとliquidationは期限が異なるため、
2C-1を個別に報告する。

- full current effective deadline: 2026-07-29 13:34:16.402489 JST
- liquidation current effective deadline: 2026-08-09 13:34:16.408828 JST
- DOM期限到達時にC:実消費量を報告し、残り8GB以上を安全基準とする
- liquidation標本gate未達時はE01-E06／C09を`UNCALIBRATED`のまま報告する
- full側でgate合格した他Hookはliquidation不足だけを理由に止めない
- 各工程完了後、次工程へ進む前にユーザー承認を得る

Stage 2C着手時点では実装作業は発生しない。thresholdは空、全Hookは`UNCALIBRATED`、
Playbookは`OBSERVE`、`execution_enabled: false`のまま維持する。
Playbook選抜、check移行、LIVE注文、既存Flow Price Response／3段チャート／8パターンの変更、
収録データの削除・修正・truncateは禁止する。

次の再開位置は、full effective deadline到達後のread-only 2C-1判定である。
詳細checkpointは
`ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_STAGE2C_CHECKPOINT_20260726.md`。

## Hook実市場妥当性・Trigger検証・継続PDCAの追加要件（2026-07-26）

ユーザーは、現行の収録、detector実装、threshold較正、発火頻度確認だけでは本質的に不足し、
88 Hookが生データ上で主張する現象を正しく捉えるか、そのHookが市場条件をまたいで耐えるか、
検証済みHookをどのTrigger条件で意思決定へ接続するかを継続的に検証できる必要があると指示した。

この指示を受け、次の承認案を作成した。

`ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_TRIGGER_VALIDATION_PDCA_SPEC_V1_20260726.md`

同仕様は、88 HookとT01-T50を完成品でなく版管理された仮説として扱い、raw journalからの
独立reference照合、検出例と見逃し・反例・near miss、市場条件別耐性、untouched holdout、
Triggerの時系列・confirmation・veto・expiry・重複・re-arm、旧版／新版shadow比較、drift、
rollbackを必須にする。Hookの妥当性、threshold較正、observe昇格は別statusで管理する。

仕様は2026-07-26 20:10 JST時点でユーザー承認待ちであり、実装承認ではない。
収録と2C-1 read-only判定は継続するが、Hook独立照合と実市場耐性gateを通る前の
threshold較正は禁止する。source code、config、runtime、UI、収録データの変更は行っていない。

## Strategy Engineの本質とHook定義（2026-07-26ユーザー確定）

DeltaEngineは端的に**自動発注システム**である。分析、Hook、Strategy Engine、検証、画面は、
正しい発注判断を作り、HFMへ自動発注し、約定後まで管理するために存在する。

ユーザーが確定したHookの意味:

- Hookは「検出イベント＝素材」そのものではない。
- Hookは注文フロー分析の至る所へ置いた罠であり、相場の変化が引っかかった瞬間に
  Strategy Engineを呼び出す装置である。
- Hook一個につきStrategy一個ではない。HookとStrategyは多対多である。
- Hook発火の都度、Engineは関係する複数Strategyを取り出し、その時点の注文フロー要素で
  各Strategyの条件を埋める。
- 条件の充足水準から、entryする／しない、いつentryする、何枚発注するかを決める。
- entry後もHookがEngineを呼び、追加、縮小、決済、反転候補を再評価する。
- 最終的に注文を出す条件がOrder Triggerであり、Hookとは別である。

今後Hookを単なる観測素材、Detector、最終Triggerとして説明しない。Hookから直接BUY／SELLまたは
`order_send`へ接続せず、必ずStrategy Engineの多対多評価、Condition Fill、充足水準、時機、枚数を通す。

ユーザーは「何をStrategyにするかが肝中の肝」と明示した。schemaや基盤の完成をStrategy完成と
取り違えず、実際に載せるStrategyの市場仮説、条件、競合、反証、時機、枚数、保有後管理を最優先する。

世界実務資料をこの定義で再照合し、初期候補を次の6系統へ具体化した。

1. BREAKOUT_ACCEPTANCE
2. FAILED_AUCTION_RECLAIM
3. ABSORPTION_DEFENSE
4. ABSORPTION_FAILURE
5. PULLBACK_CONTINUATION
6. MOMENTUM_EXHAUSTION

正本候補:

- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STRATEGY_METHOD_CONSTITUTION_OPERATIONAL_DRAFT_V0_3_20260726.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STRATEGY_CANDIDATE_SET_V0_1_20260726.md`

v0.2は同一version上書きせず保存した。v0.3とCandidate SetはユーザーGOを受けた設計文書だが、
Strategyのproduction採用、threshold較正、observe解禁、LIVE発注の承認ではない。
source code、runtime、config、UI、raw dataの変更は行っていない。

## 世界資料由来Condition Universe（2026-07-26）

ユーザーはConditionSetをローカル既存項目から自己参照で考えず、世界の実トレーダー、教育者、
取引所資料、市場微細構造研究から学んで作るよう指示した。

DeepLOB、Multi-Level OFI、Order Book Events、Queue Imbalance、LOB Resiliency、LOB-Bench、CME、
Nasdaq、Binance Futures API、Jigsaw、Axia、SMBを照合し、初版Condition Dictionaryを作成した。

- 全体Condition Universe: **560件、16group**
- raw LOB: 10段bid/ask価格・数量40件
- static book shape、multi-level imbalance、book add/cancel/refresh/pull/stack
- aggressive tape、Flow Price Response、Delta/CVD/Footprint、profile/auction
- derivatives positioning、cross-venue、execution/risk、position lifecycle
- absorption-like、fade、breakout follow-through/failure、pullback stall、momentum fade等の合成状態48件
- 各Conditionにstable ID、key、type、window、source、定義、independence lineageを付与

全体辞書は多いほどcoverageが広がるが、一Strategyが全560件を同時加点してはならない。
HookがEngineを起動し、Strategy仮説に必要なsubsetだけを埋める。window違い、同source派生、
合成状態とその材料は独立票にせず、一現象の重複加点を禁止する。最終Order Triggerは少数の
因果的hard condition、独立確認、反証不在、execution gateで構成する。

正本候補:

`ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`

これは未較正の条件宇宙であり、Strategy採用、threshold確定、HookEvent解禁、発注許可ではない。

## Strategyをnamed状態遷移として扱う確定事項（2026-07-27ユーザー訂正）

ユーザーは、Strategyを同時点のCondition集合やscoreとして扱う設計を明確に訂正した。
分足分析と異なる中心は、Hook後に注文フローの**状態変化を順番に観察すること**である。

```text
Hook
  -> named Strategy Family
       -> named Pattern
            -> Observation Instance
                 -> ordered State Transition
                      -> Order Trigger
```

- Hookが発火した時点ではentryを確定しない。
- Strategyは、1が出た後に2へ遷移したかを観察するstate machineである。
- 同じConditionが最終snapshotで同時成立しても、所定順序を通ったことにはならない。
- 各Patternは開始、順序、分岐、反証、expiry、re-arm、terminalを持つ。
- Patternの数と正確さ、業界常識に沿った遷移経路のcoverageが勝敗の鍵である。
- 560 Condition Dictionaryはstate判定の材料辞書であり、Strategy本体ではない。
- 先に作成したCondition subset CSVは材料索引へ降格し、Strategy正本としない。

ユーザーは、状態観察へ先にStrategy名を付け、どのStrategyが遷移したかをlogと後日の検証で
識別可能にするよう指示した。初期Family名は次の10件である。

1. CVD Divergence
2. Absorption Reversal
3. Exhaustion Reversal
4. Stacked Imbalance Continuation
5. Iceberg Breakout
6. Liquidity Sweep
7. Failed Auction
8. Pulling / Stacking Strategy
9. Delta Flip
10. Book Imbalance

Family名だけでなく、具体経路には不変`pattern_id`と完全な`pattern_name`を与える。
遷移logは最低限、family、pattern、version、observation instance、from/to state、根拠event、
exchange time、反証、expiry、結果をappend-onlyで残す。

ユーザー提示例は次のnamed Patternとして登録した。

`PAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001`

```text
bearish CVD divergence
  -> bid-side absorption
  -> buy wall failure
  -> fresh OI unwind
  -> SELL ready
```

世界資料の時系列記述をJigsaw、Axia、ATAS、Bookmapから再抽出し、初版として10 Family x 5件、
計50 named Patternを登録した。49件は`WORLD_DERIVED`、上記1件は`USER_DEFINED`で区別した。
50 Patternは256 advance、50 terminal、50 invalidation、50 expiry、計406 edgeのFSM台帳へ展開した。
native MBOを持たないBinanceでiceberg／stop identityを直接観測と偽装せず、観測区分を`DIRECT`、`HYBRID`、`INFERRED`、`LIMITED`に分ける。OI必須経路は10秒poll制約のため`OI_LAGGED`とする。

正本候補:

- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_WORLD_NAMED_PATTERN_CATALOG_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_WORLD_NAMED_PATTERN_REGISTRY_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_WORLD_NAMED_PATTERN_FSM_V0_1_20260727.csv`

これらは名称、出典、観察順序の設計台帳であり、threshold較正、production採用、HookEvent解禁、
発注許可ではない。完成済みFlow Price Response、3段チャート、8パターン、OI、UI、runtime、raw dataは変更していない。
## 50原型から365 named variantsへの展開（2026-07-27）

50個のsource-grounded原型を、意味が成立する方向とlocationへ束縛し、365個の
DeltaEngine derived named variantへ展開した。これは365個の世界通称を発見したという意味ではない。
世界由来49原型とユーザー定義1原型から作った、replay検証前の観察候補である。

- 方向は原型が許す場合だけLONG／SHORTへ展開し、BUY／SELL固定原型を反対方向へmirrorしない。
- locationは560 Condition Dictionaryに実在する9分類だけを使用する。
- `active range boundary`と`round number`は専用Conditionがないため作らない。
- confirmation順序は全365件で`BASE_CANONICAL_ONLY`とし、無根拠な確認条件の直積を行わない。
- 365 variantを1,876 ADVANCE、365 LOCATION_ARM、365 TERMINAL、365 INVALIDATE、
  365 EXPIRE、計3,336 edgeへ展開した。
- terminalは`LONG_READY`／`SHORT_READY`であり、直接注文ではない。
- `POST_EVENT_BALANCE`の4件は`EXT_CALENDAR_REQUIRED`で、calendar未接続中はarm不可。
- 365件すべて`UNVALIDATED`。threshold、timeout、枚数、execution gateは未較正。

ユーザー提示経路のlocation束縛例:

`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

```text
Hook arm
  -> Visible Bid Wall context confirmed
  -> bearish divergence
  -> bid-side absorption
  -> buy wall failure
  -> fresh OI decrease
  -> SHORT_READY
```

正本候補:

- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_DERIVED_PATTERN_VARIANT_POLICY_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANTS_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANT_FSM_V0_1_20260727.csv`

横断検証は0 error。variant ID／name 365件一意、50原型coverage、560 Condition ID、
26 source ID、固定方向17原型、各variantのarm／terminal／invalidation／expiryを確認した。
次は各stateへCondition材料を`required / contradiction / invalidation`として接続し、
Hookがどのvariantをarm／update／expireするかを定義する。
## State-Condition bindingとHook多対多routing（2026-07-27）

365 named variantsの3,336 edgeすべてを、state単位の観察述語と560 Condition Dictionaryへ接続した。
StrategyはCondition snapshotではなく、直前遷移より後のfresh evidenceでのみ次stateへ進む。

- Predicate Class 37件。
- Observation Predicate 236件。
- Invalidation Predicate 50件。
- Predicate合計286件。
- Variant State Binding 3,336件。edge過不足0。
- 同じsource eventを複数stateの成立証拠へ再利用しない。
- Condition IDは候補材料routeであり、全IDの同時PASSや独立加点を意味しない。
- 24 ADVANCEはpause／別eventを扱う`TEMPORAL_SEQUENCE`で、市場Conditionなしを仕様とする。
- TERMINALは`LONG_READY / SHORT_READY`をrisk／execution gateへ渡すだけで直接注文しない。

Hookの定義も固定した。Hookはstate成立を断定するDetectorではなく、関連source更新により
Strategy Engineを呼び、該当Predicateを再評価させる装置である。

- 既存Hook 88件へ`asserted_event_classes`と`capability_predicate_classes`を分けて付与。
- 84 Hookから365 variantすべてへ25,664件のdesign routeを作成。
- Hook↔variantは多対多。direction hintはreversalを消さないようhard filterにしない。
- route roleはlocation arm候補、first-state wake、active update、invalidation recheck、
  context refreshへ分離する。
- runtime enabled 0、direct order authority 0。
- G07/G08はVWAP variant locationなし、G10はround-number Conditionなし、
  G11はactive-range-edge variant locationなしのためrouteを作らない。
- suspected/context-only Hookはhard stateを単独advanceしない。

ユーザー提示variantは78 eligible Hook routeを持ち、CVD divergenceのfirst-state wake候補28件、
Visible Book Wall location候補9件、active update／recheck候補74件、invalidation recheck候補38件、
global context refresh 4件である。これは同時成立数ではなく、Engineが現在stateとfreshnessで絞る
再評価候補数である。

正本候補:

- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_OBSERVATION_PREDICATE_CLASS_REGISTRY_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_OBSERVATION_PREDICATE_REGISTRY_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_HOOK_PREDICATE_CAPABILITY_REGISTRY_V0_1_20260727.csv`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_HOOK_VARIANT_OBSERVATION_ROUTING_V0_1_20260727.csv`

これらは全件`UNVALIDATED`のdesign台帳である。次はreplay契約とnegative testを作り、
順序逆転、同一event再利用、timeout、途中反証、context-only hard advance、
Hookからの直接注文を拒否する。

## P3-C price／book／wall材料契約の解決（2026-07-27）

Strategy Engineへ渡すTier A材料のうち、時刻、price response履歴、book event履歴、
wall距離の曖昧さを、停止理由のまま残さず個別契約へ分解して解決した。

- engine clockとsource UTC epochを分離し、Strategy snapshotの評価境界をbar開始時刻でなく、
  snapshot生成を起こした最後の受理normalized event時刻へ固定
- normalized tradeをauthoritative price sourceとして300秒＋境界直前sampleを保持
- G09既存100ms／1s／5s／30sのupward／downward price progressをDecimal ticksで生成
- applied depth DIFFと`ApplyResult`からG07 Book Event Flow全48 keyをsource-time集計
- gap、snapshot、resyncでbook履歴を破棄し、新window完成までfail closed
- wallをtop10最大数量のthreshold-free candidateとし、同量時はbestに最も近いlevelを選択
- wall concentrationとdistanceを同一candidateへ結び、距離をticksへ固定
- 空／locked／crossed bookとoff-grid distanceをfail closed

正本契約:

- `ArchitectureRepository/00_Master/トリガー作成指示書群/PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md`

Strategy Engine対象43件、pipeline／book境界79件、全回帰 **590 passed, 1 skipped**。
完成済みFlow Price Response、3段チャート、8パターン、OI、UIの計算・表示は変更していない。
runtime有効化、発注権限、G16 composite、CalibrationBook thresholdは別工程であり未承認のまま。
