# 指示書: Phase 2-3 Stage 2 Task 3 — Stage 1 調査
# 16ms per-frame バジェット実測のための現状調査

- バージョン: v1.0
- 作成: 2026-08-01
- 発行元: Claude(web / 統括)
- 宛先: Codex(実装担当)
- リポジトリ: DeltaEngine05M(`C:\Users\user\Desktop\DeltaEngine05M`)
- ブランチ: feature/footprint-dom-tape

---

## 目的

Task 3 は gate 有効化後の動的ヒートマップ描画で p95 レンダリング時間が 16ms 以内であることを実測・保証するタスクである。Stage 1 では実装に入る前に、計測インフラの現状と既存テストへの波及を調査する。

---

## 調査項目

以下の各項目について、該当するファイル名・行番号(アンカー文字列)・実物の内容を報告すること。

### S1-1. renderTimes 計測機構の現状

対象ファイル: `webapp/static/orderbook_heatmap.js`

報告内容:
- `renderTimes` 配列(または同等の計測バッファ)の宣言箇所。アンカー文字列と周辺5行。
- `renderTimes` にエントリを push している箇所(描画1フレームごとの計測開始・終了)。アンカー文字列と周辺5行。
- p95 の算出ロジック。アンカー文字列と全文。
- p95 の表示先(Canvas 上の overlay か、DOM 要素か、console か)。
- `renderTimes` のバッファサイズ上限(ある場合)。
- metrics API への送信箇所(ある場合)。エンドポイント URL とペイロード構造。

### S1-2. metrics API エンドポイント

対象ファイル: `webapp/main.py`

報告内容:
- `/api/metrics` または render 性能を受け取るエンドポイントの有無。ある場合はルート定義のアンカー文字列と全文。
- 該当エンドポイントがない場合は「なし」と明記。

### S1-3. gate の現状値

対象ファイル: `webapp/static/index.html`

報告内容:
- heatmap gate フラグの現在の値(Task 2 第七コミットで `true` に設定済みのはず)。該当行のアンカー文字列と行内容。

### S1-4. 動的フレーム供給経路の確認

Task 2 で確立した live 供給経路が gate 有効化後に Canvas まで到達することを確認する。

報告内容:
- `webapp/main.py` 内の `book_projection_pump` 起動箇所。アンカー文字列と周辺3行。
- `webapp/heatmap_frame_source.py` 内の `get_frame` または同等のフレーム取得メソッド。シグネチャと戻り値型。
- `webapp/push_broker.py` 内の heatmap ペイロード構築箇所(250-299行付近)。アンカー文字列と周辺5行。
- `webapp/static/orderbook_heatmap.js` 内の WebSocket/SSE メッセージ受信 → Canvas 描画の呼び出しチェーン。主要関数名を列挙。

### S1-5. 既存テストへの波及確認

Task 3 で変更が想定されるファイルは最小限(計測・表示の強化程度)だが、既存テストへの波及を事前に確認する。

対象: `tests/` 配下

報告内容:
- `renderTimes` または `p95` または `frame_budget` または `16ms` を参照している既存テストファイルの一覧。`grep -rn "renderTimes\|p95\|frame_budget\|16ms" tests/` の出力全文。
- `test_orderbook_heatmap_ui.py` の現在のテスト関数名一覧(`grep -n "def test_" tests/webapp/test_orderbook_heatmap_ui.py` の出力全文)。
- `test_heatmap_replay_task.py` の現在のテスト関数名一覧(`grep -n "def test_" tests/webapp/test_heatmap_replay_task.py` の出力全文)。

### S1-6. pytest ベースライン

報告内容:
- `cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider` の最終行(passed/failed/skipped サマリー)。
- failed がある場合は失敗テスト名を全件列挙。

---

## 提出物

以下をまとめて報告すること。

1. S1-1 ~ S1-6 の各項目への回答(上記フォーマットに従う)
2. `git log --oneline -3` の出力(HEAD 確認)
3. `git status --porcelain` の出力(working tree クリーン確認)

---

## 注意事項

- 本指示書は調査のみ。コードの変更・追加は一切行わないこと。
- 保護ファイル(`webapp/main.py`, `docker-compose.yml`, `tests/webapp/test_book_update.py`, `webapp/static/index.html`)および Task 1 成果物(`webapp/heatmap_frame_source.py`, そのテスト)、`src/heatmap/reconstruct.py` は参照のみ。変更禁止。
- 報告はファイルの実物から転記すること。記憶や推測で埋めない。

以上。
