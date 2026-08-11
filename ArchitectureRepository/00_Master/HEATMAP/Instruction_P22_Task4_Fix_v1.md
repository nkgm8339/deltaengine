# 指示書: Phase 2-2 Task 4 是正(タイムアウト対処)
**作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md / 実行指示書: Instruction_Phase2-2_Renderer_v1.2 / 前指示: Approval_P22_Task3_Go_Task4 / 承認者: お館様**

---

## 0. 背景と統括の指示是正

- Task 4のCLIが606秒でタイムアウト(分類②処理の重さ)。Codexの停止判断は統制通りで正しい。
- **原因は統括の検証条件設定の誤り**。純PythonのPNG生成(struct/zlib/binascii、Task 3で承認)は
  ピクセルをPythonループで処理するため、viewport 1800×1600(288万px)×20回=5760万px演算で破綻する。
  Task 3の純Python実装は正しい(依存衝突回避)。誤りは、その実装特性に対しTask 4で
  大解像度×20回を課した点にある。
- **測定対象の取り違えも是正する**。p95 16ms予算は本来、Phase 3のリアルタイム逐次描画
  (Canvas 2D、ブラウザ側)フレームに対する監視である。静的PNG生成器(オフライン検証用)を
  16msで測ること自体が対象違い。よってp95 16ms評価はTask 4から外し、Phase 2-3へ移す。

## 1. Task 4の目的を再定義

Task 4の本来の目的は「実データ(検証録画34セグメント)が全経路
(iter_records → sample_states → bin_samples → render_heatmap)を通り、正しい絵が1枚出ること」の確認。
**描画1回で十分**。20回×大解像度は不要だった。

## 2. 是正内容(render_check.pyの修正)

対象: `ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py`
(既知値 SHA-256 `4228869FD7499B4D8345026DAB7FB650E02B3BBB2E8D679F13102EA67F849C75` を修正)

1. **既定描画回数を20回→1回**にする。フルサイズ描画は1枚生成で成果確認とする。
2. **既定viewportを縮小**する。1800×1600は純Python生成には過大。
   検証目的(全経路疎通+目視で板の濃淡が見える)に足る解像度として、
   **時間軸=サンプル列数(約300)に対し1列2〜3px、価格軸=価格ビン数に応じ目視可能な高さ**を
   目安とする。具体値の目安: **width 600〜900 × height 400〜600**。
   Codexは実際の価格ビン数を確認し、この範囲でviewportを定めて報告する
   (範囲外が妥当と判断する場合は理由を添えて報告し停止)。
3. **p95・20回計測ロジックは残置してよいが、既定では実行しない**
   (回数=1で1回のtotal_msを記録)。オプション引数で多数回計測を将来可能にするのは可だが、
   既定経路はタイムアウトしないこと。
4. **単発描画の時間ログ**(RenderReportのtransform_ms/render_ms/total_ms)は従来通り出力。
   16ms予算との比較は行わない(対象違いのため。Phase 2-3で評価する旨をログにコメント)。

## 3. 実行と検証

1. 是正後CLIを1回実行し、以下を出力・報告:
   - 生成PNGのパスとbyte数、width×height
   - グリッド寸法(価格ビン数 × サンプル列数)、gap列数
   - RenderReport(transform_ms/render_ms/total_ms、単発)
   - 実行がタイムアウトせず完了すること(所要秒を報告)
2. **PNGは成果物として保存**し、統括が目視確認できるよう提出対象に含める
   (板の濃淡・bids青/asks赤・gap列黒が視認できること)。
3. 全pytest実行(`Delta_Engine_Pro4web/`から):
   ```
   python -m pytest -q -p no:cacheprovider
   ```
   承認基準: **新規fail 0**。ベースライン 1 failed / 737 passed / 1 skipped、
   既知fail は `tests/webapp/test_dom_tape_fusion_ui.py` のみ。heatmap系追加でpassedは増える。

## 4. 統制
- render_check.pyのみ修正(新規または既存tools_p22内の修正)。他の既存ファイル・保護対象4件禁止。
- ライブ接続禁止・git変更操作禁止・`float()`原則禁止。
- 是正後CLIが再度タイムアウトした場合は再実行せず停止し、viewport寸法と所要時間を報告。
- Task 4完了で停止。Task 5へ進まない。

## 5. 報告フォーマット
- [完了/失敗/停止] Phase 2-2 Task 4 是正
- CLI実行結果(viewport寸法、グリッド寸法、gap列数、total_ms、所要秒)
- 生成PNGの識別値(パス/byte/SHA-256)
- 全pytest結果(既知fail以外のfail 0であること)
- 変更該当 ファイル:行番号
- 次のアクション案(実行はしない)
