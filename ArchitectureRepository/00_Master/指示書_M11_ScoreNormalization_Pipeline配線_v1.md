この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_M11_ScoreNormalization_Pipeline配線_v1

**対象**: Order Flow Analysis Platform — M11（スコア正規化関数の実装 ＋ pipeline.py への Footprint/Imbalance/SignalEngine 配線 ＋ Signal Storage）
**参照正本**: SignalEngine_v3.1.md §4 / ParquetSchema_v3.1.md §4（Signal Schema） / DuckDBDDL_v3.1.md §3（signals）
**関連**: CVD_v3.2.md / Footprint_v3.0.md / Imbalance_v3.1.md / ErrorCodes_v3.1.md
**現状確認済み**（本セッションで実ファイルを取得し確認）:
- `src/pipeline.py`: `ReplayPipeline.run()` / `LivePipeline.run_async()` はいずれも `handle(normalized)` クロージャで `storage.add_trade(...)` → `cvd.process(normalized)` → bar確定時 `storage.add_candle(...)` を行う。**`CvdCalculator.process()` には `NormalizedTrade` をダックタイピングでそのまま渡している**（明示的な型変換なし）
- `src/database/schema.py`: `TRADES_SCHEMA`/`CANDLES_SCHEMA`/DDL/`trade_to_row`/`candle_to_row` のみ。`signals`/`ai_results` は「out of Phase5 scope」と明記されたコメントあり（本指示書で `signals` を追加する）
- `src/database/storage.py`: `StorageWriter.add_trade`/`add_candle`/`tick`/`flush`/`close`。`DuckDbWriter._insert` は `ON CONFLICT DO NOTHING`（trades/candlesはPRIMARY KEY持ち）
- `ArchitectureRepository/40_Reference/DuckDBDDL_v3.1.md` §3 `signals` テーブルは **PRIMARY KEY定義なし**（trades/candlesと異なる）
- `src/config.py`: `signal.cvd_slope_ref`（null）と `calibration.cvd_slope_ref`（null）の**重複キーが存在**（詳細は決定11）

---

## 0. 前提・スコープ

M7〜M10で作った4計算器（CVD/Footprint/Imbalance/SignalEngine）は単体では完成しているが、互いに配線されていない。M11では以下を行う:

1. 生出力（Candle・FootprintBar・ImbalanceResult）から SignalEngine 入力スコアへの正規化関数（純粋関数）
2. `ReplayPipeline` / `LivePipeline` への Footprint・Imbalance・SignalEngine 配線（bar確定ごとに評価）
3. Signal出力の Storage 永続化（`signals` テーブル。正本にスキーマが既に存在するため対象内）

**Footprint・Imbalanceの生データ自体（価格レベル別出来高テーブル等）はStorageに永続化しない**（正本にテーブル定義が無いままのため、M7の決定を維持）。中間データとして計算に使うのみ。

**Absorptionは配線しない**（M9未着手、板情報基盤も未整備のため）。`signal_engine.evaluate()` には `absorption_result=None` を渡す。

**Repository（docs）は無変更**。

---

## 1. 成果物

- 変更: `src/orderflow/signal.py`（スコア正規化関数3つを追加。`SignalEngine`/`SignalResult`/`AbsorptionResult` は既存のまま変更不要）
- 変更: `src/database/schema.py`（`SIGNALS_SCHEMA`/`SIGNALS_DDL`/`signal_to_row` を追加）
- 変更: `src/database/storage.py`（`StorageWriter.add_signal`、`DuckDbWriter.insert_signals`、`signals_written` カウンタを追加）
- 変更: `src/pipeline.py`（`ReplayPipeline.run()` と `LivePipeline.run_async()` の両方に Footprint・Imbalance・SignalEngine を配線。`ReplayStats`/`LiveStats` に `signals_stored: int` を追加）
- 新規: `tests/orderflow/test_signal_normalization.py`（スコア正規化関数の単体テスト）
- 変更: `tests/test_pipeline.py` および `tests/test_live_pipeline.py`（Signal配線の統合テスト追加）
- 変更: `tests/database/test_storage.py`（`add_signal`/`insert_signals` のテスト追加）

---

## 2. 仕様サマリ（SignalEngine_v3.1 §4.1 より）

```text
score_cvd = clamp( (CVD_slope / cvd_slope_ref) × 100, −100, +100 )
    CVD_slope = evaluation_window（デフォルト1 bar）内のCVD変化 = 確定Candleのdelta

score_fp  = clamp( ((BuyVol − SellVol) / (BuyVol + SellVol)) × 100, −100, +100 )
    BuyVol/SellVol = 確定FootprintBarの全価格レベル合計

score_imb = clamp( direction × min(stacked_count / stack_ref, 1) × 100, −100, +100 )
    正本は単一のstacked imbalanceを想定した式。複数（BUY/SELL混在含む）への一般化は決定10で確定する
```

§8 エラーハンドリング: 「Scoring failure（全出来高0によるゼロ除算等）→ モジュールスコアを0として扱い、warningログ」と明記されている。

---

## 3. 設計判断（正本に明記がないため、本指示書で確定する）

### 決定10: `score_imbalance` の複数stacked imbalance統合方法

`ImbalanceResult.stacked_imbalances` はBUY方向・SELL方向どちらも複数含みうるが、正本の式は単一のstacked imbalanceを前提にしている。以下のように一般化する:

```python
net = Σ(count for BUY方向のstacked) − Σ(count for SELL方向のstacked)
score_imb = clamp( sign(net) × min(|net| / stack_ref, 1) × 100, −100, +100 )
（net == 0 の場合は 0）
```

単一方向・単一stackのみの場合、正本の式と完全に一致する。

### 決定11: `cvd_slope_ref` の参照元は `signal.cvd_slope_ref` とする

`config.py` に `signal.cvd_slope_ref` と `calibration.cvd_slope_ref` の重複キーが存在する（両方null）。配線コードは **`config.signal.cvd_slope_ref`** を読む（SignalEngineの設定名前空間と一致するため）。`calibration.cvd_slope_ref` は重複として今回は触れない（削除・統合は別途整理タスクとし、本指示書のスコープ外）。

`cvd_slope_ref` が `None`（未較正、初期状態）の間、`score_cvd()` は `None` を返す。SignalEngine は M10 決定7により該当モジュールを分母からも除外して動作を継続する（CVDスコアが較正されるまで、SignalはFootprint+Imbalanceの2モジュールのみで合成される）。

### 決定12: `signals` テーブルは主キー無し・confidenceはDOUBLE

`DuckDBDDL_v3.1` §3 の `signals` テーブルは正本上PRIMARY KEY定義が無い（`trades`/`candles`と異なる）。よって `insert_signals` は `ON CONFLICT DO NOTHING` を使わず、**プレーンな `INSERT`** とする（存在しないPKへのON CONFLICT指定はDuckDBがエラーになるため）。`confidence` カラムは `DOUBLE` 型（`DECIMAL(20,8)`ではない）なので、`signal_to_row` で `float(signal_result.confidence)` に変換する。

---

## 4. インターフェース設計

### 4.1 スコア正規化関数（`src/orderflow/signal.py` に追加）

```python
def score_cvd(delta: Decimal, cvd_slope_ref: Optional[Decimal]) -> Optional[Decimal]:
    """確定Candle.delta と cvd_slope_ref からCVDスコアを算出。
    cvd_slope_ref が None または 0 の場合は None（決定11）。"""

def score_footprint(buy_volume: Decimal, sell_volume: Decimal) -> Decimal:
    """FootprintBar.levels の合計BUY/SELL出来高からFootprintスコアを算出。
    buy_volume + sell_volume == 0 の場合は 0（正本§8、決定不要・明記済み）。"""

def score_imbalance(imbalance_result: ImbalanceResult, stack_ref: int) -> Decimal:
    """ImbalanceResult.stacked_imbalances からImbalanceスコアを算出（決定10）。"""
```

呼び出し側（pipeline.py）が `FootprintBar.levels` を合計して `score_footprint` に渡す。

### 4.2 pipeline.py 配線

`handle(normalized)` クロージャを拡張する（Replay/Live共通パターン）:

```python
def handle(normalized) -> None:
    storage.add_trade(trade_to_row(normalized))
    cvd_result = cvd.process(normalized)
    fp_closed = footprint.process_trade(normalized)   # 同じダックタイピングで直接渡す

    if cvd_result.closed_candle is not None:
        storage.add_candle(candle_to_row(cvd_result.closed_candle))
        # cvd と footprint は同一の bar_start ロジック共有のため同時に確定する。
        # 万一片方のみ確定した場合は E9001 として警告ログを出し、Signal評価はスキップする。
        if fp_closed is None:
            logger.warning("E9001 footprint bar did not close with candle bar_time=%s", cvd_result.closed_candle.bar_time)
        else:
            imbalance_result = imbalance_detector.detect(fp_closed)
            buy_total = sum((lv.buy_volume for lv in fp_closed.levels), start=Decimal(0))
            sell_total = sum((lv.sell_volume for lv in fp_closed.levels), start=Decimal(0))

            cvd_score = score_cvd(cvd_result.closed_candle.delta, cvd_slope_ref)
            fp_score = score_footprint(buy_total, sell_total)
            imb_score = score_imbalance(imbalance_result, stack_ref)

            signal_result = signal_engine.evaluate(cvd_score, fp_score, imb_score, absorption_result=None)
            storage.add_signal(signal_to_row(cvd_result.closed_candle.bar_time, self.symbol, signal_result))
```

`footprint`（`FootprintCalculator`）・`imbalance_detector`（`ImbalanceDetector`）・`signal_engine`（`SignalEngine`）は `cvd` と同じ場所（関数/メソッド冒頭）でインスタンス化する。`ImbalanceDetector`/`SignalEngine` の構成パラメータは `config.imbalance.*` / `config.signal.*`（既存の `config.py` フィールドをそのまま使用。新規config項目は追加しない）。

`finalize()` 相当の終端処理（ReplayPipelineの末尾、LivePipelineの `finally` ブロック）でも、CVDの `finalize()` と対になる `footprint.finalize()` を呼び、最後の未確定バーを同様に処理すること（既存の `final_candle` 処理パターンに倣う）。

---

## 5. テストベクタ

正本にこの粒度のTVは存在しないため、以下は **本指示書で独自定義**する（TV番号なし、`test_` 関数名で明確に命名すること）。

### スコア正規化関数

- `test_score_cvd_positive`: delta=+5, cvd_slope_ref=10 → score=+50
- `test_score_cvd_clamped`: delta=+30, cvd_slope_ref=10 → score=+100（clamp上限）
- `test_score_cvd_none_when_unref`: cvd_slope_ref=None → score=None
- `test_score_footprint_all_buy`: buy=10, sell=0 → score=+100
- `test_score_footprint_zero_volume`: buy=0, sell=0 → score=0（正本§8準拠）
- `test_score_imbalance_single_buy_stack`: stacked=[BUY count=3], stack_ref=3 → score=+100
- `test_score_imbalance_net_mixed`: stacked=[BUY count=3, SELL count=1], stack_ref=3 → net=2 → score=+66.66...（Decimal精度は既存パターンに合わせる）
- `test_score_imbalance_no_stacks`: stacked=[] → score=0

### pipeline統合テスト

- `test_pipeline_emits_signal_on_bar_close`: 複数バーにまたがる取引を replay し、バー確定ごとに `signals` テーブルへ1行書き込まれることを確認
- `test_pipeline_signal_deterministic_replay`: 同一入力を2回replayし、`signals` テーブルの内容が完全一致すること
- `test_pipeline_cvd_slope_ref_none_degrades_gracefully`: `cvd_slope_ref=None` の設定で実行し、エラーにならず Footprint+Imbalance の2モジュールのみでSignalが出ること

---

## 6. 完了条件

- [ ] スコア正規化関数3つが全てDecimal演算（float不使用、`score_footprint`/`score_imbalance`の戻り値もDecimal）
- [ ] `signals` テーブルへの書き込みが `insert_trades`/`insert_candles` と同様に動作すること（PRIMARY KEY無しである点のみ異なる、決定12）
- [ ] ReplayPipeline・LivePipeline両方で配線されていること
- [ ] 上記テストベクタが全てgreen
- [ ] 既存 109 tests は無影響でgreenのまま
- [ ] `docs/`（Repository正本）は無変更
- [ ] Footprint/Imbalanceの生データはStorageに永続化しない（中間データのみ）
- [ ] Absorptionは配線しない（`absorption_result=None`固定）

---

## 7. 報告フォーマット

完了後、以下を報告すること:

- 新規テスト件数（旧109件 + 新規n件）
- §3 設計判断3点（決定10/11/12）について、実装上の逸脱があれば明記
- `cvd_slope_ref` が未較正（None）の状態でSignalが実際にどう出力されるか、実行結果を1つ添えること
- 残タスク: ①Absorption実体化（M9、板情報基盤含む）の着手可否、②`calibration.cvd_slope_ref`重複キーの整理要否、について一言ずつ
