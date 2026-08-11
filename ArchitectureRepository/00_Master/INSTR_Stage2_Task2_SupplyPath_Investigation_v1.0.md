# 指示書: Phase 2-3 Stage 2 Task 2 供給経路+gate 調査
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3 Stage 2
前提: 第六コミット完了(HEAD 2fea7ef)。frame_source(iter_book_projections)確定。Task 2はBookProjection列をbroker.on_book_update経由でWebSocket配信し、index.html gate(GO-H6)を有効化して既存Canvasに接続する。main.py/index.html接触のため、本調査で接触範囲と起動モデルを確定し統括承認を得てから実装する。
段階: 調査のみ。変更・実装・新規ソース生成を行わない。読み取りのみ。

---

## 規律
- 変更するな。読み取りのみ。全回答に ファイル:行番号 併記。設計の是非判定を書くな。事実と論点提示のみ。

## 調査項目

### M1. main.py の book projection 供給の起動/非起動条件
- live分岐で book_projection_pump / task を起動する箇所と条件を ファイル:行番号 で示せ(main.py:231-237,371-387付近)。
- replay分岐で book_projection_task=None とする箇所と、DISABLED_REPLAY 扱いの箇所を ファイル:行番号 で示せ。
- lifespan内で非同期taskを生成・登録・shutdownする既存パターン(asyncio.create_task, 終了時await/close)を ファイル:行番号 で列挙せよ。

### M2. config.replay 構造と recording dir 指定手段
- `config.replay` のフィールド(enabled, data_path等)を定義箇所の ファイル:行番号 で示せ。
- depth_history_raw directory(frame_source入力)を指すconfig/env項目が既存にあるか。DEPTH_HISTORY_ROOT/PERSISTENT_DEPTH_HISTORY_ROOT等の既存項目を ファイル:行番号 で示し、frame_sourceのrecording_dirに転用できる候補を事実として挙げよ(採否は書くな)。

### M3. index.html gate 有効化の最小変更範囲
- `ORDER_BOOK_HEATMAP_ENABLED = false`(index.html:969)と、setupがgate=falseで要素をhiddenにしてreturnする箇所(index.html:2370-2380付近)を ファイル:行番号 で示せ。
- gateをtrueにした場合に通る経路(HeatmapBookStore/Canvas生成、window.HEATMAP_UI設定、mode切替)の範囲を ファイル:行番号 で示せ。
- gate以外に有効化を妨げるフラグ(PHASE5_FUSION_ENABLED等)の依存関係を ファイル:行番号 で示せ。

### M4. broker.on_book_update を async taskから駆動する接続点
- live pump が project_once → send callback(broker.on_book_update)を呼ぶ流れを ファイル:行番号 で示せ(book_projection.py:267-280, main.py:231-237)。
- frame_source.iter_book_projections は同期generator。これを async task 内で回し `await broker.on_book_update(projection)` する場合の、既存の類似パターン(同期iterを非同期で回してbrokerへ流す箇所)が webapp/pipeline にあるか ファイル:行番号 で示せ。無ければ「該当なし」。
- 各BookProjection配信間の間隔制御(sleep/interval)の既存手段を ファイル:行番号 で示せ。

### M5. live bookとreplay heatmap bookの共存
- broker.on_book_update が BOOK_UPDATE を出すと、index.html の onBookUpdate → HEATMAP_UI.ingestBook に渡る経路を ファイル:行番号 で確定せよ(index.html:1085-1088付近)。
- book_stream_id が異なる BOOK_UPDATE を Canvas store がどう扱うか(stream restart処理、orderbook_heatmap.js:203-225)を ファイル:行番号 で示せ。
- observeフェーズで、replay heatmap供給時に live book供給が同時に走るか(replay分岐とlive分岐は排他か)を main.py の分岐構造の ファイル:行番号 で示せ。

### M6. gate有効化後のwebソケット→Canvas経路の完全確認
- WebSocket受信からindex.htmlのhandle→onBookUpdate→HEATMAP_UI.ingestBook→Canvas描画までを ファイル:行番号 で通し、gate=trueで欠落なく繋がるかを事実として示せ。

## 提出物
- M1-M6 の調査結果(ファイル:行番号併記)
- 保護ファイル接触の見込み一覧: main.py / index.html それぞれ、Task 2実装で変更が要る最小範囲を ファイル:行番号 で(この段階では変更しない)
- 参照ファイルのHEAD SHA-256とbyte/LF/CR
- `git rev-parse HEAD`(2fea7ef), `git status --porcelain -- Delta_Engine_Pro4web/`, `git diff --cached --name-only`(空)

## 禁止事項
- 実装・変更・新規ソース生成。判定・GO/NO-GO記載。

以上。提出後、統括がTask 2の起動モデル(config/endpoint、live/replay排他、配信間隔)と保護ファイル変更の最小範囲を確定し、明示承認の上でTask 2実装指示書を発行する。
