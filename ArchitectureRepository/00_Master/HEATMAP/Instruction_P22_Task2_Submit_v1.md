# 指示書: Phase 2-2 Task 2 実物提出・統括検算
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 Task 2 / 承認者: お館様**

---

## 0. 目的
- Task 2(座標変換モジュール)を統括が実物で独立検算する材料を提出させる。
- 本Taskの核はx座標-185.25pxバグの再発防止。テストのpassだけでなく、
  回帰テストが実効的(実際に負座標を生む条件を再現)であることを実物で確認する。
- 本タスクは**提出のみ**。実装・変更・git操作は禁止(テスト再実行は可)。

## 1. 提出物
対象: `C:\Users\user\Desktop\DeltaEngine05M`

以下2ファイルの (a)SHA-256 (b)byte (c)LF行数 (d)全文 を提出(ASCIIファイル名併用)。

1. `Delta_Engine_Pro4web/src/heatmap/transform.py`
   (既知値: SHA-256 `0A076B1274F907241D3A68D3267AA0E2065C91D5EC7BC30C9CB5EFC76B113C39`
    / 6,766 byte / LF 240。不一致なら停止)
2. `Delta_Engine_Pro4web/tests/heatmap/test_transform.py`
   (既知値: SHA-256 `7C5AAAEFB66388C3E9C23DFD1DF842757262B64634C46B0D2B4E7573AD95F374`
    / 7,004 byte / LF 269。同上)

### 手順
```powershell
cd C:\Users\user\Desktop\DeltaEngine05M
Get-FileHash -Algorithm SHA256 Delta_Engine_Pro4web\src\heatmap\transform.py
Get-FileHash -Algorithm SHA256 Delta_Engine_Pro4web\tests\heatmap\test_transform.py
(Get-Item Delta_Engine_Pro4web\src\heatmap\transform.py).Length
(Get-Item Delta_Engine_Pro4web\tests\heatmap\test_transform.py).Length
git status --porcelain -- Delta_Engine_Pro4web/src/heatmap/transform.py Delta_Engine_Pro4web/tests/heatmap/test_transform.py
python -m pytest -q -p no:cacheprovider tests/heatmap/test_transform.py
```

## 2. 統括が検算する観点(該当 ファイル:行番号 を報告に併記)
1. **x回帰防止テストの実効性**(最重要): test_transform.py:99付近の回帰テストが、
   naiveな座標式なら負のx(例: -185.25px相当)を生む入力条件を実際に構成し、
   transform.py経由の結果が非負になることをassertしていること。
   テストが用いる具体的な入力値・期待値・assert式を報告に明記する。空通過でないこと。
2. **往復恒等性**: test_transform.py:26付近が grid→pixel→grid で元のindexに戻ることを
   具体値で比較していること。用いるindex範囲を報告。
3. **端点厳密一致**: 左端/右端/上端/下端の期待pixelがハードコード値でassertされていること
   (test_transform.py:54/77)。
4. **全座標非負**: test_transform.py:189付近が、想定入力域全体で負座標が出ないことを
   走査的にassertしていること。
5. **整数変換の一元化**: transform.py:214付近が整数(ピクセル)への変換の唯一点であり、
   他所にint()/round()/floor()等によるピクセル化が散在しないこと。散在があれば行番号を報告。
6. **float非使用**: `float(`の出現0件をコード検索で確認(報告に検索コマンドと件数)。
7. **grid軸前提**: 価格軸(price_bins昇順)を画面下→上、時間軸(sample_times_ms昇順)を左→右へ
   写像する箇所(transform.py:88付近)。Task 1のHeatmapGrid軸と整合していること。

## 3. 報告フォーマット(統制ルール準拠)
- [完了/失敗/停止] Phase 2-2 Task 2 実物提出
- SHA-256 / byte / LF / git status / pytest結果
- §2各観点の該当 ファイル:行番号。特に観点1のテスト入力値・期待値・assert式
- 次のアクション案(実行はしない)

## 4. 停止条件
- 既知値とSHA-256が不一致。
- pytest再実行結果が完了報告(9 passed)と食い違う。
- 同一コマンド失敗2回連続。
