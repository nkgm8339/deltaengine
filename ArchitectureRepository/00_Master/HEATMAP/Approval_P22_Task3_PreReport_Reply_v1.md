# 承認通知: Phase 2-2 Task 3 事前報告への回答(条件付き承認)
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 / 承認者: お館様**

---

## 0. 総括

Task 3事前報告のうち、**色マッピング案と継ぎ目検証案は承認**。
**依存方式案とRenderReport定義に是正・確定を求める**。下記2条件を満たしたうえで
render_static.py / test_render_static.py の実装に着手してよい。

## 1. 承認する項目

### 色マッピング案 — 承認
統括推奨案を正しく具体化している。以下をそのまま採用してよい。
- bids/asks別々に全時間・全価格範囲でスケール算出、列単位正規化なし
- ゼロ数量をpercentile母集団から除外、正数量へ`(Decimal("1")+quantity).ln()`
- 各レイヤーp1〜p99クリップ、percentileはDecimal線形補間、p1=p99なら全正数量を最大強度
- 正数量の強度32..255、ゼロは0
- bids青ランプ`(0,0,i)` / asks赤ランプ`(i,0,0)`、同一セルはRGBチャネル別合成(数量加算しない)
- gap_columns=True は黒`(0,0,0)`で板数量を描画しない、通常ゼロ背景も黒

補足確認: 同一セル合成でbid強度とask強度が別チャネルに入り数量を混ぜない方式は、
v1.6哲学「各値は独立・混合しない」に合致する。承認。

### 継ぎ目検証案 — 承認
Task 2申し送り(ROUND_HALF_UP由来の1px重複/隙間)への対応として的確。以下を採用。
- 整数割り切れしないviewport幅・高さを使用
- 隣接列 `right == 次列left`、隣接行 `bottom == 次行top`
- 最初と最後のセルがviewport両端に一致
- 半開区間で各pixelがちょうど1回だけ所属

## 2. 是正・確定を求める項目(着手ブロック条件)

### 条件A: 出力解像度 — 「1セル1ピクセル」を是正
- 問題: 「出力寸法=time_count × price_count、1セル1ピクセル」では、
  検証録画(300サンプル)が300×価格ビン数の極小画像になり、板の濃淡を目視できない。
  かつTask 2 transform.pyの`PixelViewport`(セル=複数ピクセルの矩形)を実質迂回し、
  ラスタ境界(transform.py:189/214)とTask 2の座標変換成果を捨てることになる。
- 是正: **1セル=複数ピクセルの矩形塗りを基本**とする。
  `PixelViewport`を与え、`grid_cell_raster_bounds()`が返す整数矩形を塗る方式にする。
  セルの縦横ピクセル数はviewport寸法から決まる(1セル1ピクセルに固定しない)。
- テスト・フルサイズCLIの解像度: テストは価格ビン50×時間100以下(統制)。
  render_check.py(Task 4)でのフルサイズは、目視可能な解像度のviewportを与える
  (具体値はTask 4指示で定める。本Taskではviewportを引数として受ける設計にしておく)。
- 半開区間・継ぎ目防止は§1継ぎ目検証案の通り維持する(矩形塗りでも各pixel 1回所属)。

### 条件B: RenderReport定義 — 全項目を確定して報告
- 報告が「aggregation_ms: 入力が既にHeatmapGridのため」で途切れている。
  指示書v1.2は「全体+行程別(集約/変換/描画)のms」を要求。以下を確定し、実装前に定義を報告:
  - `aggregation_ms`: 入力が既にHeatmapGridなら0または該当なしと明記
  - `transform_ms`: 座標変換(grid→ラスタ境界算出)の経過
  - `render_ms`: ピクセル塗り+PNGエンコードの経過
  - `total_ms`: 全体
  - 計測は`perf_counter_ns()`、floatを経由せずDecimalミリ秒へ(報告の方式でよい)
- 描画時間ログは`RenderReport`とログ双方へ出す(指示書要求)。

## 3. 着手許可

条件A・条件Bを満たす設計であれば、以下の新規2ファイルのみ実装してよい。実装後は停止して報告。
- `Delta_Engine_Pro4web/src/heatmap/render_static.py`
- `Delta_Engine_Pro4web/tests/heatmap/test_render_static.py`

実装内容(§1承認事項+条件A/B+指示書v1.2 Task 3):
- `render_heatmap(grid, viewport, out_path) → RenderReport`(viewportを引数に取る。条件A)
- 標準ライブラリのみ(struct/zlib/binascii)でRGB PNG生成、外部依存追加なし、requirements.txt不変
- 座標はtransform.pyの`grid_cell_raster_bounds()`のみ使用(新規座標計算を作らない)
- 色は§1色マッピング案、gap列は黒
- test: 価格ビン50×時間100以下。出力生成・寸法・ギャップ非塗り潰し・継ぎ目連続性(§1)を検証

## 4. 統制
- 条件A/Bを満たさない実装(1セル1ピクセル固定・RenderReport項目欠落)は統制違反。着手前に再報告。
- 既存ファイル変更禁止・保護対象4ファイル禁止・ライブ接続禁止・git変更操作禁止。
- `float()`は原則禁止。PNGエンコードでバイト列を扱う変換は整数演算で行う。
  やむを得ずライブラリAPIが型を要求する箇所があれば行番号を報告。
- Task 3完了で停止。Task 4へ進まない。同一テスト失敗2回連続で停止。

## 5. 報告フォーマット
- [完了/失敗/停止] Phase 2-2 Task 3
- RenderReport定義(§条件B)、実行コマンドと結果(pytest、描画時間)
- 変更該当 ファイル:行番号
- 次のアクション案(実行はしない)
