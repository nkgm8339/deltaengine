# 指示書: Phase 2-2 Task 1 是正後 実物提出・統括再検算
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 / 是正指示: Instruction_P22_Task1_Fix_v1 / 承認者: お館様**

---

## 0. 目的
- Task 1是正(セグメント境界保持)の結果を統括が実物で独立再検算するための材料を提出させる。
- 本タスクは**提出のみ**。実装・変更・git操作は禁止(テスト再実行は可)。

## 1. 提出物
対象: `C:\Users\user\Desktop\DeltaEngine05M`

以下2ファイルの (a)SHA-256 (b)byte (c)LF行数 (d)全文 を提出する。
全文はファイル提出(ASCIIファイル名併用)。

1. `Delta_Engine_Pro4web/src/heatmap/binner.py`
   (是正後既知値: SHA-256 `15F41C721F41B680F7946714C4614C585E6D40F3783C0D8585030A4F8266F4C7`
    / 9,299 byte / LF 255。提出値がこれと一致することを確認。不一致なら停止)
2. `Delta_Engine_Pro4web/tests/heatmap/test_binner.py`
   (是正後既知値: SHA-256 `22A5D568D1BF1ECD06FD0AB1DC0C220DF17FD6580E9A6A70964D020829FAA5E5`
    / 6,521 byte / LF 237。同上)

### 手順
```powershell
cd C:\Users\user\Desktop\DeltaEngine05M
Get-FileHash -Algorithm SHA256 Delta_Engine_Pro4web\src\heatmap\binner.py
Get-FileHash -Algorithm SHA256 Delta_Engine_Pro4web\tests\heatmap\test_binner.py
(Get-Item Delta_Engine_Pro4web\src\heatmap\binner.py).Length
(Get-Item Delta_Engine_Pro4web\tests\heatmap\test_binner.py).Length
git status --porcelain -- Delta_Engine_Pro4web/src/heatmap/binner.py Delta_Engine_Pro4web/tests/heatmap/test_binner.py
python -m pytest -q -p no:cacheprovider tests/heatmap/test_binner.py
```

## 2. 統括が再検算する観点(該当 ファイル:行番号 を報告に併記)
1. **跨いだフラグ伝播の除去**: 旧実装のギャップフラグ伝播(旧binner.py:165/178相当)が
   除去され、セグメント境界でギャップ列が独立マーカーとして残る実装であること。該当行番号。
2. **セグメント分割の定義**: ギャップ境界直前で連続区間を分割する箇所(:167付近)の実コード。
3. **独立間引き**: 各セグメントへ独立に`max_time_cols`と床除算間引きを適用する箇所(:180付近)。
   セグメント間でindex選択が混ざらないこと。
4. **時系列連結**: 各セグメント結果+境界ギャップ列を時間順連結する箇所(:189付近)。
5. **床除算維持**: 間引き式が床除算のまま変更されていないこと(:156付近)。
6. **テストの実効性**: 差し替えたテスト(test_binner.py:108付近)が
   (a)各セグメント先頭末尾保持 (b)境界ギャップ列の出力残存
   (c)一方のセグメントの間引きが他方に影響しないこと、を実際にassertしており空通過でないこと。
   assert対象の変数と比較内容を報告に明記する。
7. **既存適合の非退行**: 入力順序非依存テスト・Decimal規律・bids/asks別レイヤーが
   是正で壊れていないこと(既存テストが引き続きpass)。

## 3. 報告フォーマット(統制ルール準拠)
- [完了/失敗/停止] Phase 2-2 Task 1 是正後 実物提出
- SHA-256 / byte / LF / git status / pytest結果
- §2各観点の該当 ファイル:行番号 と、観点6のassert内容
- 次のアクション案(実行はしない)

## 4. 停止条件
- 是正後既知値とSHA-256が不一致。
- pytest再実行結果が是正報告(12 passed)と食い違う。
- 同一コマンド失敗2回連続。
