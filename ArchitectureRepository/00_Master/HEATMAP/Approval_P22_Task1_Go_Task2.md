# 承認通知: Phase 2-2 Task 1 承認 / Task 2 着手指示
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 / 承認者: お館様**

---

## 1. Task 1 承認

Task 1(ビナー実装、セグメント境界保持是正込み)を承認する。統括が是正後実物で独立再検算した。

- SHA-256照合(完全一致):
  - binner.py `15F41C721F41B680F7946714C4614C585E6D40F3783C0D8585030A4F8266F4C7`
    / 9,299 byte / LF 255
  - test_binner.py `22A5D568D1BF1ECD06FD0AB1DC0C220DF17FD6580E9A6A70964D020829FAA5E5`
    / 6,521 byte / LF 237
- 検算確定事項:
  - 跨いだフラグ伝播の除去(旧`_propagate_gaps` 0件、境界列フラグ直接保持 binner.py:89)
  - セグメント独立間引き(各start/end内でのみ間引き binner.py:197、床除算維持 binner.py:162)
  - 差し替えテストが実効的(計6列=各セグメント3列を検証 test_binner.py:147、
    連結一致・先頭末尾・境界列Trueをassert test_binner.py:136-146)
  - 既存適合の非退行(Decimal規律・入力順序非依存・bool/float拒否 test_binner.py:35/150/209/218)

## 2. Phase 2-3 アンカー確定(記録)

`HeatmapGrid`フィールド構成を確定事実として記録する(binner.py:20)。
Phase 2-3指示書の確定待ちアンカー1件目はこれで充足。

```
price_bin: Decimal
price_bins: tuple[Decimal, ...]
sample_times_ms: tuple[int, ...]
bid_quantities: tuple[tuple[Decimal, ...], ...]
ask_quantities: tuple[tuple[Decimal, ...], ...]
gap_columns: tuple[bool, ...]
```

## 3. Task 2 着手指示(座標変換モジュール)

指示書v1.2 §3 Task 2 の規定通り、以下を新規実装せよ。x座標-185.25pxバグ再発防止が本Taskの核。

- 新規: `Delta_Engine_Pro4web/src/heatmap/transform.py`
  - グリッド座標(ビンindex, 時間index)⇔ ピクセル座標の**純関数**。
  - Decimal→描画座標の変換をこのモジュールに**一元化**する(他所での座標計算を作らない)。
  - 入力に用いるグリッド軸はTask 1の`HeatmapGrid`(price_bins昇順、sample_times_ms昇順)を前提とする。
- 新規: `tests/heatmap/test_transform.py`
  - 往復変換の恒等性(grid→pixel→grid が元に戻る)
  - 端点の厳密一致(左端/右端/上端/下端が期待ピクセルに一致)
  - **負座標が発生しないこと**(x座標オフセット誤りを検出するテストを必ず含める)
  - 数値で検証(float混入を避け、ピクセル最終変換のみtransform.py内でint/固定小数へ)

## 4. 統制(再掲)
- Task 2完了で停止し報告。Task 3へ勝手に進まない。
- 既存ファイル変更禁止・保護対象4ファイル禁止・ライブ接続禁止・git変更操作禁止。
- `float()`はtransform.py内のピクセル最終変換点に限定し、テストで固定。それ以外は禁止。
- 同一テスト失敗2回連続で停止。タイムアウトは3分類報告。

## 5. 報告フォーマット
- [完了/失敗/停止] Phase 2-2 Task 2
- 実行コマンドと結果(要点、pytest)
- 変更該当 ファイル:行番号
- 次のアクション案(実行はしない)
