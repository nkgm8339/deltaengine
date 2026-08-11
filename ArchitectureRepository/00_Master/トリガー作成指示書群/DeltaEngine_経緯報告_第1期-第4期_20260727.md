# DeltaEngine プロジェクト経緯報告: 第1期〜第4期

作成日: 2026-07-27 JST
作成: Claude(検証担当)
根拠: 過去セッション記録および本日受領のCodex報告群。過去期の記述はセッション記録に基づき、現物ファイル未検証の項目は日付・数値をセッション記録のまま転記している。
訂正履歴: 初版の「全push済み」「D5〜D8未決裁」等6点をお館様の指摘(2026-07-27)により訂正済み。git状態・決裁状態は本文の記載を正とする。

---

## 第1期: 観測基盤の構築と複合スコアの撤去(〜2026-07-20頃)

### 何を作ったか

Binance Futures BTCUSDT永続先物のリアルタイムオーダーフロー分析基盤。

- 生DOM(板)・歩み値・清算ストリームの受信と正規化
- 吸収検出・Imbalance検出・Footprint集計・CVD
- 決定論リプレイ(同じ入力から同じ結果を再現できる仕組み)
- Decimal精度(float禁止)、単一ループ非同期モデル(ADR-003)
- Docker配備のブラウザUI

### 何を捨てたか

当初、CVD・Footprint・Imbalance等を±100の共通スケールへ正規化し加重平均する**複合スコア方式**が載っていた。これを「各指標は独立変数であり、混合は設計上の欺瞞」と断定し、**5指標独立化リファクタリング**で全撤去した。

- 実施順: CVD → Footprint → Imbalance → Absorption → Flow → 一括撤去
- 撤去対象: composite / confidence / market_state / confluence / signal枠 / absorption veto / flow平均化 / score_*共通スケール部品 / trend_filter
- 各指標はネイティブ単位の独立表示へ移行(「60は60、80は80」)
- この期の終了時ベースライン: **349 passed**(v3.6.9)

### この期に確立した原則

- 数値は圧縮しない。正規化・混合・加重平均の禁止
- すべての主張にファイル:行番号の根拠。根拠なき断定の禁止
- 実装順序は厳密シーケンシャル(1指標1指示書、検証後に次へ)

---

## 第2期: 単独シグナルの実データ検証と棄却(〜2026-07-26頃)

### 何をやったか

複合を捨てた後、flow_response(価格反応)単独でのシグナル有効性を実データで検証した。

### 結果

**相関 -0.025。再現性なし。棄却。**

これにより正本境界が確定した。

- ENTRYロジック採用禁止
- LIVE起動禁止
- 実発注は一度も行っていない(checkモード13件のみ)

### 意味

「複合はダメ、単独もダメ」が実測で確定した期。観測基盤は本物だが、そこから発注判断を導く方法が白紙に戻った。

---

## 第3期: Strategy Engine(FSM方式)への転換(2026-07-26〜27)

### 方式転換

同時snapshotの複合判定ではなく、**stateごとの述語(predicate)を、前state成立後の新しい証拠だけで段階的に進めるFSM(有限状態機械)** へ転換した。Hookは起こすだけで断定せず、TERMINALはLONG_READY/SHORT_READYの受け渡しのみで直接発注しない。

### 規模

- 365 named variants / 3,336 edges / 25,664 routes / 286 predicates(37 class)
- 全件UNVALIDATED・runtime有効化0・発注権限0(fail-closed)
- 代表1型: `VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

### 実装完了(ローカルcommitのみ。**push未実施**、最新commit a8182a9)

| 工程 | コミット |
|---|---|
| Replay契約拒否試験(R1〜R8) | aa1f43e |
| Strategy Engine本体骨格(ContractEnforcer合成方式) | 28d5229 |
| 実Predicate Evaluator骨格(9 class、CalibrationBook注入) | cf00f2e |
| Ingestion Adapter骨格(Tier A condition写像) | e001031 |
| Codex引き継ぎ書 | d795dec |

この期の終了時ベースライン: **574 passed / 1 skipped**

### 設計判断(承認済み)

- 閾値ハードコード禁止。CalibrationBook経由、空book→UNVALIDATED→拒否
- Tier A(生/派生数値・単一ストリーム窓計算) / Tier B(合成FLAG)の2層
- 条件はcondition snapshot疎結合(mapで供給)

### 並行して開始したもの

- Hook Stage 2A/2B append-only収録が稼働開始(停止禁止)
- DOM収録終了予定: 7/29 13:19 JST
- 清算収録終了予定: 8/9 13:19 JST(標本gate: 4,000件以上・side別1,000件以上)
- 全88 Hook UNCALIBRATED・発火禁止

---

## 第4期: G16の壁とProducer先行の決定(2026-07-27未明)

### 発覚した問題

Composite Synthesis層(Tier B合成FLAG)の実装検証で、**G16の13件すべてが合成式UNDEFINED**と判明。

- 正本(Condition Dictionary:665-736)には自然言語定義のみ。入力key・論理式・閾値・時間窓が無い
- 正本自身が「G16の採否・threshold・windowは検証でvariant別に決める契約」と明記(:729-736)
- さらに、合成の材料となるTier A keyの大半をProducerが未生成(当時の固定出力9 keyのみ。aggression量・price progress・book refresh/pull等が全欠)

### 決定

3案(A: 式を先に定義 / B: Producerを先に作る / C: スコープ縮小)から**選択肢B「Producer先行」を採択**。

これがP工程の起点となった。

- P1: SnapshotProducer(検出器出力の収集・正規化)
- P2: pipeline配線(Live/Replay供給)
- P3: Tier A契約の確定(P3-a、P3-b E02を経て、P3-cが本日)

E98(INVALIDATION_RECHECK)への反証key追加もこの期に草案化された(failure=candidate、follow-through=contradiction)。

---

## 本日(2026-07-27、第4期の続き): P3-c

第4期の詳細は既報`P3-C_状況報告_実施済み_現在地_今後_20260727.md`のとおり。要点のみ。

- 議題書検証でバグ・矛盾5件を特定(価格履歴欠如、key上書き規則、時刻系二重ほか)
- Codexが解決、**590 passed / 1 skipped**が現行ベースライン。
  590 passed, 1 skipped in 92.88s(600秒変更後の実測)
- G16較正はholdout未成立を確定(データ3.7日/必要7日、正解label無し)
- 価格履歴保持期間を**600秒に決裁**。実装済み・全回帰合格(590 passed / 1 skipped)だが**未コミット**。
  2026-07-27時点のgit状態は以下の2件である。

   M Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py
  ?? ArchitectureRepository/00_Master/トリガー作成指示書群/DeltaEngine_経緯報告_第1期-第4期_20260727.md

  すなわち未コミットは600秒変更(snapshot_producer.py)のみではなく、本経緯報告書自体も未追跡である。
- **D5〜D8は決裁済み**。未完了は決裁後の実測threshold較正・holdout検証
- 未解決: 契約書の300秒記載(PRICE_RESPONSE_HISTORY_CONTRACT_V0_1:26,50)と実装600秒の不整合
- 未完了: cvd_change_5sの責任境界・定義の整理(Adapter側とProducer側の双方に出力箇所があるが、Producer側はsetdefaultで上書きしないため実害は未発生。どちらの定義を正とするかの整理が残る)
- G16: 13件の自然言語定義は未確定。ただし代表variantのE01/E02/E03/E98はRealPredicateEvaluator・CalibrationBook注入構造・テスト用較正値が存在する。production runtimeは引き続き未較正・無効
- git: **push未実施**。最新ローカルcommit a8182a9、600秒変更ほかが未コミットで滞留

---

## 一本道の要約

```
第1期  複合スコアを作った → 欺瞞と断定し全撤去。5指標を独立化
第2期  単独シグナルを実データ検証 → 相関-0.025で棄却。発注封印
第3期  FSM方式(Strategy Engine)へ転換。骨格完成、全件fail-closed。収録開始
第4期  G16合成式が全部未定義と判明 → 材料(Tier A)を先に作る決定 → P工程
本日   P3-cでTier A契約の土台バグを潰し、較正は収録充足待ちと確定
```

次の律速は**収録**である。DOM収録終了(7/29)と清算収録終了(8/9)の後、閾値較正(分布パーセンタイル方式)→代表1型リプレイ発火検証→他variant一般化→observe並走→型選抜→check→最小ロットlive(封印中)、の順で進む。

以上。
