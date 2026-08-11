# 承認通知: Phase 2-2 Task 3 承認 / Task 4 着手指示
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 / 承認者: お館様**

---

## 1. Task 3 承認

Task 3(静的描画器)を承認する。統括が実物で独立検算した。

- SHA-256照合(完全一致):
  - render_static.py `AB9E040BCBAFD4E2D55A3B30AEEF728486E9A55366E35829BFB3F2234608A3AD`
    / 8,470 byte / LF 264
  - test_render_static.py `EBF5A077786867F2A0AE648A76F88160D0DF7F73BA55DFDA3BB9693949C3205C`
    / 7,221 byte / LF 258
- 検算確定事項:
  - 条件A達成: viewport引数の矩形塗り(:60/:86/:99/:229)、1セル1ピクセル固定でない
    (テスト出力22×15 :108)。Task 2座標変換を使用。
  - 継ぎ目検証が実効的: 非割り切りviewport width=7/height=5で隣接right==next.left(:207)、
    bottom==next.top(:223)、pixel重複禁止(:230)、coverage完全一致(:237)。
    Task 2申し送り(ROUND_HALF_UP由来の重複/隙間)解消。
  - 色マッピング(ln1p :172、p1/p99 :184、p1=p99→255 :202、bid青/ask赤別チャネル :229)
  - gap列黒スキップ(:119)とpixel assert(:140)、標準ライブラリPNG(:10/:246)、`float(` 0件
  - RenderReport全11フィールド定義(:38)+ログ出力(:158)、条件B充足

## 2. Task 4への申し送り(承認を妨げない)

- Task 3の描画時間実測はwidth=22×15の極小データ。**p95予算16msの監視はまだ効いていない**。
  Task 4のフルサイズ(検証録画300サンプル)で初めてp95を評価する。
- p95が16msを超過した場合、指示書v1.2のダウンサンプリング(価格ビン粗化・時間列削減)で対処し、
  効果を計測して報告する(自動調整でなく報告)。

## 3. Task 4 着手指示(実データ確認CLI+全pytest)

指示書v1.2 §3 Task 4 の規定通り、以下を実装・実行せよ。

- 新規: `ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py`
  - 入力: 検証録画
    `data_05M/phase2_0_d2_validation/20260730T043059/depth_history_raw/symbol=BTCUSDT/`
  - 経路: `DepthHistoryReader(dir).iter_records()` → `sample_states(records, interval_ms)` →
    `bin_samples(...)`(binner) → `render_heatmap(grid, viewport, out_path)`(render_static)。
  - **viewportは目視可能な解像度**を与える(1セル複数ピクセル)。具体寸法はCLI内で定義し報告。
  - フルサイズ描画1枚を生成し、描画時間(RenderReportのtransform_ms/render_ms/total_ms)、
    グリッド寸法(価格ビン数×サンプル列数)、gap列数を出力。
  - **p95評価**: 複数回(例 20回)描画し、total_msのp95を算出・報告する。
    16ms超過時はダウンサンプリング効果を計測して報告(§2)。
  - フルサイズ描画は本CLIのみ(テストは価格ビン50×時間100以下の統制を維持)。
- 全pytest実行(`Delta_Engine_Pro4web/`から):
  ```
  python -m pytest -q -p no:cacheprovider
  ```
  - 承認基準: **新規fail 0**。ベースライン 1 failed / 737 passed / 1 skipped、
    既知fail は `tests/webapp/test_dom_tape_fusion_ui.py` のみ。
    heatmap系4テストファイル(test_binner/test_transform/test_render_static + 既存)が
    加わるため、passed数は増える。fail数がベースラインから増えないことを確認。

## 4. 統制
- render_check.pyは新規ファイル。既存ファイル変更禁止・保護対象4ファイル禁止。
- ライブ接続禁止(入力は録画のみ)。git変更操作禁止。`float()`原則禁止。
- Task 4完了で停止し報告。Task 5へ勝手に進まない。
- 同一テスト失敗2回連続で停止。タイムアウトは3分類報告。
- p95が16msを大幅超過し、ダウンサンプリングでも収まらない場合は停止して設計を報告。

## 5. 報告フォーマット
- [完了/失敗/停止] Phase 2-2 Task 4
- render_check.py実行結果(viewport寸法、グリッド寸法、gap列数、total_ms p95、
  必要ならダウンサンプリング効果)
- 全pytest結果(failed/passed/skipped、既知fail以外のfail 0であること)
- 変更該当 ファイル:行番号
- 次のアクション案(実行はしない)
