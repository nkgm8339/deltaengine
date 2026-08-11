# 指示書: Phase 2-2 Task 3 実物提出・統括検算
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 Task 3 / 事前承認: Approval_P22_Task3_PreReport_Reply_v1 / 承認者: お館様**

---

## 0. 目的
- Task 3(静的描画器)を統括が実物で独立検算する材料を提出させる。
- 特に条件A(viewport矩形の複数ピクセル塗り=1セル1ピクセル固定でないこと)と、
  継ぎ目検証テストの実効性を実物で確認する。
- 本タスクは**提出のみ**。実装・変更・git操作は禁止(テスト再実行は可)。

## 1. 提出物
対象: `C:\Users\user\Desktop\DeltaEngine05M`

以下2ファイルの (a)SHA-256 (b)byte (c)LF行数 (d)全文 を提出(ASCIIファイル名併用)。

1. `Delta_Engine_Pro4web/src/heatmap/render_static.py`
   (既知値: SHA-256 `AB9E040BCBAFD4E2D55A3B30AEEF728486E9A55366E35829BFB3F2234608A3AD`
    / 8,470 byte / LF 264。不一致なら停止)
2. `Delta_Engine_Pro4web/tests/heatmap/test_render_static.py`
   (既知値: SHA-256 `EBF5A077786867F2A0AE648A76F88160D0DF7F73BA55DFDA3BB9693949C3205C`
    / 7,221 byte / LF 258。同上)

### 手順
```powershell
cd C:\Users\user\Desktop\DeltaEngine05M
Get-FileHash -Algorithm SHA256 Delta_Engine_Pro4web\src\heatmap\render_static.py
Get-FileHash -Algorithm SHA256 Delta_Engine_Pro4web\tests\heatmap\test_render_static.py
(Get-Item Delta_Engine_Pro4web\src\heatmap\render_static.py).Length
(Get-Item Delta_Engine_Pro4web\tests\heatmap\test_render_static.py).Length
git status --porcelain -- Delta_Engine_Pro4web/src/heatmap/render_static.py Delta_Engine_Pro4web/tests/heatmap/test_render_static.py
python -m pytest -q -p no:cacheprovider tests/heatmap/test_render_static.py
```

## 2. 統括が検算する観点(該当 ファイル:行番号 を報告に併記)
1. **条件A(viewport矩形塗り)**(最重要): `render_heatmap`がviewportを引数に取り、
   `grid_cell_raster_bounds()`が返す矩形を塗ること。1セル=複数ピクセルになり得る
   (1セル1ピクセル固定でない)こと。矩形塗りのループ該当行番号と、
   セルの縦横ピクセル数がviewport寸法から決まる箇所を示す。
2. **継ぎ目検証テストの実効性**: test_render_static.py:175/230付近が、
   **整数割り切れしないviewport幅・高さ**を使い、隣接列right==次列left・隣接行bottom==次行top、
   および各pixelがちょうど1回だけ所属することをassertしていること。
   用いるviewport寸法の具体値とassert式を報告。空通過でないこと。
3. **gap列黒**: gap_columns=Trueの列が黒(0,0,0)で塗られ板数量を描画しないこと
   (render_static.py:119付近)。テスト:140が実際にgap列のpixel値が黒であることをassert。
4. **色マッピング**: Decimal ln1p、p1〜p99クリップ、別レイヤースケール(render_static.py:172付近)。
   p1=p99フォールバック(全正数量を最大強度)の該当行。bid青(0,0,i)/ask赤(i,0,0)の
   別チャネル合成、数量加算しない箇所。
5. **PNG標準ライブラリ生成**: struct/zlib/binasciiのみ(render_static.py:242付近)、
   scanline filter=0固定。外部依存importが無いこと(importセクションの該当行)。
6. **float非使用**: `float(`両ファイル0件をコード検索で確認(検索式と件数を報告)。
7. **RenderReport**: 定義(render_static.py:38)の全フィールドと、
   transform_ms/render_ms/total_msの計測範囲が報告通りか。ログ出力箇所(:158)。

## 3. 報告フォーマット(統制ルール準拠)
- [完了/失敗/停止] Phase 2-2 Task 3 実物提出
- SHA-256 / byte / LF / git status / pytest結果
- §2各観点の該当 ファイル:行番号。特に観点1の矩形塗り、観点2のviewport寸法・assert式
- 次のアクション案(実行はしない)

## 4. 停止条件
- 既知値とSHA-256が不一致。
- pytest再実行結果が完了報告(3 passed)と食い違う。
- 条件A未達(1セル1ピクセル固定を検出)。
- 同一コマンド失敗2回連続。
