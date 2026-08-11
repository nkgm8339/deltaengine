# 指示書: Phase 2-3 Stage 2 実装ロードマップ + Task 1 調査
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3
前提: ソース衛生完了(HEAD bf95126、Delta_Engine_Pro4web/ tracked dirty 0、773 passed)。Stage 1調査 I1-I8 完了。
段階: 本指示のパート2(Task 1調査)は調査のみ。実装・変更・新規ソース生成を行わない。

---

## パート1: Stage 2 実装ロードマップ(統括の計画。Codexは把握のみ、実装しない)

### 目標
Canvas 2D 動的フレームレンダリング + recording駆動動的スクロール + p95 16ms per-frameバジェット監視。

### Stage 1調査からの確定制約
- 純Python PNG生成は実時間不適(Task 4実証、Full total_ms p95=21264ms)。動的描画はブラウザCanvas 2Dで行う。
- index.htmlにheatmap Canvas基盤が既存(presentation gate=false でoff)。`H:index.html:754-781,969,2323-2333`
- サーバ→ブラウザはWebSocket。book payloadは既存経路。
- フレーム列(時間方向1列送り)を切り出す既存APIは無い(I3)。新規frame_sourceが要る。
- per-frame計測の仕組みは既存に無い(I5)。新規計測が要る。
- カラーマッピング確定値(ln→p1-p99クリップ、bid青(0,0,i)/ask赤(i,0,0)、レイヤー混合禁止、gap黒)はrender_static.pyに実装済み。Canvas経路でも同一値を再現する。

### タスク分割(各Taskは 調査→実装→統括検証→承認 の順。保護接触Taskは着手前に統括の明示承認)
- **Task 1(本指示で調査着手)**: frame_source。recordingのsample列/gridから、時間方向に1フレーム分を順次供給するイテレータ。src/heatmap新規モジュール。保護ファイル非接触。単体テスト付き。
- **Task 2(保護接触)**: Canvas 2D 動的スクロール描画。index.htmlのgate有効化 or orderbook_heatmap.js拡張。カラーマッピング確定値を再現。着手前に統括承認。
- **Task 3**: 16ms per-frameバジェット計測。1フレームのtransform→描画時間をp95で評価。
- **Task 4(保護接触の可能性)**: recording駆動統合(replay/WebSocket経路)。main.py route要否はTask 4着手時に確定。

### 規律(Stage 2全体)
- float禁止(例外transform.pyの最終ピクセル座標のみ)。Decimalネイティブ。
- 独立5指標を合成しない。カラーマッピングはbid/ask別チャンネル、混合禁止。
- ADR-003(asyncio単一ループ)、ADR-011(全量記録)。Replay/Live同一applyコア。
- 保護4ファイル変更は明示承認後のみ。

---

## パート2: Task 1 調査(frame_source設計材料)

### 規律
- 調査のみ。src/heatmap・保護ファイル・git・stagingを変更するな。読み取りのみ。
- 全回答に ファイル:行番号 を併記。設計判定を書くな。事実と論点の提示のみ。

### 調査項目

#### J1. sample_states 戻り値の実体
- `DepthReconstructor.sample_states`が返す `tuple[int, OrderBookSnapshot]` の int(時刻)の単位と意味、OrderBookSnapshotのbid/ask構造(価格→数量)を ファイル:行番号 で示せ。
- `H:src/orderflow/orderbook.py` のOrderBookSnapshot定義と、`src/heatmap/reconstruct.py`のsample_states実装を参照。

#### J2. HeatmapGrid の時間列構造
- `HeatmapGrid`の `sample_times_ms`, `bid_quantities`, `ask_quantities`, `gap_columns` が、時間列×価格ビンをどう保持するか(配列の次元・順序)を `src/heatmap/binner.py` の ファイル:行番号 で示せ。
- 1時間列(1フレーム相当)を取り出すのに必要なインデックス構造を事実として示せ。

#### J3. 既存Canvas描画APIの入力形状
- `H:webapp/static/orderbook_heatmap.js` が描画に用いるデータ形状(1列/1フレーム分の入力)を ファイル:行番号 で示せ。
- `ingestBook`/描画関数が期待する payload 構造を特定せよ。

#### J4. 動的スクロールの設計論点(事実ベースで論点列挙、判定不要)
- 1フレームで進める時間列数、可視ウィンドウの列幅、スクロール時の再描画範囲について、既存コード(render_static.py, orderbook_heatmap.js, transform.py)が示唆する制約を ファイル:行番号 付きで列挙せよ。
- gap列(gap_columns)を動的スクロールでどう扱うか、既存のgap黒レンダリング実装(render_static.py)の該当箇所を示せ。

#### J5. per-frame計測点の候補
- 1フレームのtransform→描画時間を計測する挿入点の候補を、frame_source(新規)と描画境界の観点で ファイル:行番号 の候補として示せ。既存のRenderReport(render_static.py:37-51)の計測パターンを参照。

### 提出物
- J1-J5 の調査結果(ファイル:行番号併記)
- 参照ファイルのHEAD時点SHA-256とbyte/LF/CR
- `git rev-parse HEAD`(bf95126), `git status --porcelain -- Delta_Engine_Pro4web/`(coreにM追加なし), `git diff --cached --name-only`(空)

### 禁止事項
- 実装・変更・新規ソース生成。
- 設計の是非判定・GO/NO-GO記載。

以上。Task 1調査提出後、統括がframe_sourceの実装仕様(1フレーム定義・イテレータIF・計測点)を確定し、Task 1実装指示書を発行する。
