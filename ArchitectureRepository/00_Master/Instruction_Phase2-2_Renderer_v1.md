# 指示書: Phase 2-2 ヒートマップ静的描画器
**Version: 1.0 / 作成日: 2026-07-30 / 統制文書: HEATMAP_指示書_v1.6.md §8 / 承認者: お館様**

---

## 0. 目的と位置づけ

- Phase 2-1再構築器の出力(`sample_states`)から、価格×時間×指値厚みのヒートマップ静的画像を生成する描画器を実装する。
- 本Phaseは**静的描画のみ**。ライブ接続・リアルタイム配信(Phase 3)・UI統合は対象外。
- CLAUDE.md統制ルール(停止条件・Task単位停止・報告フォーマット)を全Taskに適用する。
  Task完了ごとに停止し、個別承認を待つ。

## 1. 禁止事項(最優先)

- ライブ接続(取引所API/WebSocket)の使用禁止。テストはfixture/録画のみ。
- 保護対象4ファイル(webapp/main.py、docker-compose.yml、tests/webapp/test_book_update.py、
  webapp/static/index.html)への変更禁止。触れる必要が生じたら停止・確認。
- 既存ファイルの変更禁止(本指示書の成果物はすべて新規ファイル)。例外が必要なら停止・確認。
- `float()`禁止(集約演算の内部はDecimal。描画座標への変換のみ§4の規定に従う)。
- push/branch/rebase/amend禁止。コミットは統括承認後の指示による。
- 常時記録の恒久有効化に触れない(未判断事項)。

## 2. 入力契約(v1.6 §8確定、実物SHA-256照合済み)

- records取得: `DepthHistoryReader(dir).iter_records()`(src/heatmap/reconstruct.py、
  SHA-256 `84639422635CC01678CFB1E622FA561DF0B51D733A3262DA4A2B3A25C16BEB0C`で確定)。
- サンプル列: `sample_states(records, interval_ms)` → `(sample_time_ms, OrderBookSnapshot)`。
  event-time基準で厳密単調増加。GAP/SYNC_FAILED跨ぎでサンプル時刻リセット
  (**欠損区間を描画で埋めない**。欠損はギャップとして可視化する)。
- **正規化必須**: 描画側は`OrderBookSnapshot`のbids/asksの並び順を仮定しない。
  ビナー入力段で必ず bids=価格降順 / asks=価格昇順 に自前ソートしてから処理する
  (Task 0で実物構造を確認するが、実装は並び順仮定に依存させない)。

## 3. Task分割

### Task 0: OrderBookSnapshot実物構造の確認・報告(読み取りのみ)

- `src/orderflow/orderbook.py`(SHA-256 `291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05`、
  byte 11,295 / LF 290、で照合してから読む。不一致なら停止)。
- 報告事項(すべて ファイル:行番号 付き):
  1. `OrderBookSnapshot`の定義位置・フィールド名・型
  2. bids/asksの格納形式(list/dict、要素型、価格・数量の型)と並び順の実装上の保証有無
  3. スナップショット取得メソッド(reconstruct.pyが返すsnapshotの生成箇所)
- 実装・変更は一切しない。報告のみで停止。

### Task 1: ビナー(集約器)実装

- 新規: `Delta_Engine_Pro4web/src/heatmap/binner.py`
- 契約: `bin_samples(samples, price_bin: Decimal, max_time_cols: int) → HeatmapGrid`
  - **価格ビン集約**: 価格を`price_bin`刻みのビンへ集約(ビン境界は`floor(price / price_bin) * price_bin`、
    Decimal演算)。ビン内数量はDecimal加算。
  - **時間間引き**: サンプル数が`max_time_cols`超過時は等間隔間引き。間引き規則を実装コメントと
    テストで固定する。
  - `HeatmapGrid`: 価格ビン軸(Decimal昇順)× 時間軸(sample_time_ms昇順)× 数量(Decimal)。
    bids/asksは別レイヤーで保持(混合しない)。ギャップ列は明示フラグで保持。
- 入力正規化(§2のソート)は本モジュールの入口で実施。
- 新規: `tests/heatmap/test_binner.py`。合成データで、ビン境界・Decimal保持・間引き規則・
  ギャップ保持・入力順序非依存(シャッフル入力で同一出力)を検証。

### Task 2: 座標変換モジュール実装(x座標-185.25pxバグの再発防止)

- 新規: `Delta_Engine_Pro4web/src/heatmap/transform.py`
- 契約: グリッド座標(ビンindex, 時間index)⇔ ピクセル座標の純関数。
  Decimal→描画座標の変換はこのモジュールに**一元化**し、他所での座標計算を禁止する。
- 新規: `tests/heatmap/test_transform.py`。往復変換の恒等性、端点(左端/右端/上端/下端)の
  厳密一致、負座標が発生しないこと、を数値で検証。**x座標のオフセット誤りを検出するテストを必ず含める**。

### Task 3: 静的描画器実装

- 新規: `Delta_Engine_Pro4web/src/heatmap/render_static.py`
- 契約: `render_heatmap(grid, out_path) → RenderReport`。出力はPNG。
  依存ライブラリを新規追加する場合は実装前に候補と理由を報告し承認を待つ(停止条件)。
- 数量→色強度のマッピング規則(スケール方式)は実装前に案を報告し承認を得る。
- **描画時間ログ必須**: 全体および行程別(集約/変換/描画)の経過msを`RenderReport`と
  ログに出力。p95予算16msは静的描画では参考値だが、計測値の報告は必須。
- ギャップ列は塗り潰さず空白(またはギャップ表示)でレンダリングする。
- 新規: `tests/heatmap/test_render_static.py`。**価格ビン50×時間100以下**の小規模データのみ。
  出力ファイル生成・寸法・ギャップ列の非塗り潰しを検証。フルサイズ描画はテストで行わない。

### Task 4: 実データ確認CLI+全pytest

- 新規: `ArchitectureRepository/00_Master/HEATMAP/tools_p22/render_check.py`
  - 検証録画`data_05M/phase2_0_d2_validation/20260730T043059/depth_history_raw/symbol=BTCUSDT/`
    を入力に、samples 300(Phase 2-1既知値)からフルサイズ描画1枚を生成し、
    描画時間・グリッド寸法・ギャップ数を出力する(フルサイズは本CLIのみ。統制ルール準拠)。
- 全pytest実行。承認基準: **新規fail 0**(ベースライン 1 failed / 737 passed / 1 skipped、
  既知failは`test_dom_tape_fusion_ui.py`のみ)。

### Task 5: 3点セット提出

- CompletionLog.mdエントリ(追記のみ)、成果物一式(生成PNG含む)、報告書。
  各ファイルのSHA-256 / byte / LF行数を添付。コミットは行わず停止(コミットは別途
  チェックポイント指示による)。

## 4. 数値規律

- 集約・数量はDecimal。文字列→Decimal変換のみ、`float()`禁止、bool偽装int拒否。
- ピクセル座標算出の最終段のみ、transform.py内で明示的にint/固定小数へ変換してよい。
  変換点はtransform.py内に限定し、テストで固定する。

## 5. 停止条件(統制ルールに追加)

- Task 0のSHA-256照合不一致。
- 依存ライブラリ追加・色スケール方式の承認前着手。
- 同一テスト失敗2回連続、タイムアウト(3分類報告)。
- 保護対象・既存ファイルへの変更が必要になった場合。

## 6. 報告フォーマット

- [完了/失敗/停止] Task名
- 実行コマンドと結果(要点のみ)
- 次のアクション案(実行はしない)
