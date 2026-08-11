# Phase 2-3 Stage 2 Task 2 Web担当引き継ぎ

発行日: 2026-08-01  
目的: Task 1を保全し、Task 2を起動設定込みで実際に動く状態まで一貫して完了させる。

## 1. 基準状態

最後に確認された基準HEADは `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`。Task 1の `heatmap_frame_source.py` とテストはこのコミットに含まれるため、巻き戻し対象に含めない。

## 2. 安全な整理

新しいセッションで先に読み取り確認を行う。

```powershell
git rev-parse HEAD
git status --porcelain -- Delta_Engine_Pro4web/
git diff --name-only -- Delta_Engine_Pro4web/
git diff --cached --name-only
```

Task 2の未確定差分が次の4パスだけであることを確認する。

```text
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/static/index.html
Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
```

確認後、この4パスだけを基準HEADへ戻す。`phase0c_storage_sizing_20260728/` 等の未追跡データ、Task 1の2ファイル、HEATMAP文書は触らない。整理後に意図しない差分が残っていないことを確認する。

## 3. 再実装で成立させる経路

```text
depth_history_raw
 -> iter_book_projections
 -> heatmap_replay_loop
 -> broker.on_book_update
 -> WebSocket BOOK_UPDATE
 -> index.html handle/onBookUpdate
 -> HEATMAP_UI.ingestBook
 -> HeatmapBookStore / Canvas
```

`HEATMAP_REPLAY_ENABLED=true` のときはreplay taskを起動し、liveの`book_projection_pump`は起動しない。falseのときは既存live pumpを維持する。両方からBOOK_UPDATEを流さない。

## 4. 起動設定を必ず揃える

`index.html:969` のゲートをtrueにするだけでは未完成である。`main.py:138` の `HEATMAP_REPLAY_ENABLED` は既定値falseなので、実起動環境でtrueにしなければ画面だけ表示され、BookProjectionは流れない。

実装完了条件は次の4点とする。

1. UIゲートを有効化する。
2. 起動環境で `HEATMAP_REPLAY_ENABLED=true` を設定する。
3. `DEPTH_HISTORY_ROOT` が実在する `depth_history_raw` を指すことを確認する。
4. replay時とlive時のbook channel排他をテストする。

Compose等に環境変数を設定しない場合は、UI gate trueでも供給なしのため完了扱いにしない。

## 5. 検証条件

- replay loopの全projection送信、send例外の隔離、CancelledError再送出、待機間隔を検証する。
- recording directory、sample interval、depth levels、symbolの引き渡しを検証する。
- replay有効時にlive book projection taskが起動しないことを検証する。
- gate有効状態に対応したUI guard testを更新する。
- WebSocket受信からCanvas描画までを確認する。
- 既知failure以外の新規pytest failureがないことを確認する。

## 6. コミット前ゲート

- Task 1のファイルを変更・stageしない。
- `main.py` と `index.html` は承認済みアンカー以外を変更しない。
- 新規ファイルのSHA、byte、LF、CRを記録する。
- 新規Task 2範囲で `float(` を使用しない。
- `git diff --cached --name-only` が承認済み対象だけになる。
- `HEATMAP_REPLAY_ENABLED=true` とrecording rootを実起動条件で検証する。

安全な巻き戻しは後退ではなく、Task 1を保全した基準状態からUIゲート・供給task・起動環境・テストを同じ仕様で再構成するための同期操作である。第七コミットは、コード差分だけでなく実起動条件まで確認してから確定する。

