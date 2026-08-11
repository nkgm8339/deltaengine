# INSTR Stage2 Task2 Recovery and Completion v1.0

- 発行: 2026-08-01
- 対象リポジトリ: DeltaEngine05M(`C:\Users\user\Desktop\DeltaEngine05M`)
- 基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`(branch: feature/footprint-dom-tape)
- 参照(不可侵・SHA固定): `INSTR_Stage2_Task2_Implementation_v1.0.md`(SHA-256 `27a1e161beadaa3ed3dec233844d093a62fe2aa831d08769657a0bbbc7611f7d`)
- 位置づけ: 本書は上記 v1.0 実装指示を変更しない。基準HEADへ同期(安全巻き戻し)した上で v1.0 の D1-D6 をそのまま適用し、供給網羅性と二経路起動検証を追加要件として重ねる復旧・完了指示である。

本書は2段階フォーマットに従う。§3 は実装、§4 に停止条件(調査→承認→実装)を明記する。Codex の自己申告完了は承認根拠にしない。全成果物は実物受領後に統括が独立検証する。

---

## 1. 目的

Task 1(`heatmap_frame_source.py`、第六コミット `2fea7ef` に確定済)を保全したまま、散在する Task 2 未確定差分を基準へ同期し、v1.0 指示に沿って Task 2 を再構成する。完了の定義は「recording駆動の動的ヒートマップが実際にCanvasへ描画されること」を二経路(live通常 / replay override)で実証することとする。compose 既定は false のままとし、恒久的な出荷既定は変更しない。observe フェーズ・発注ゼロを維持する。

---

## 2. 安全な巻き戻し(必須3安全弁)

破壊的操作である。次の順序を厳守し、各ステップの出力を報告に含める。

### 2-1. 破棄前の差分退避(安全弁A: 捕獲してから捨てる)

reset の前に未確定差分を復元可能な形で必ず保全する。

```powershell
git rev-parse HEAD
git status --porcelain -- Delta_Engine_Pro4web/
git diff --name-only -- Delta_Engine_Pro4web/
git diff --cached --name-only
git stash push -u -m "task2_predrop_20260801" -- Delta_Engine_Pro4web/
git stash list
git rev-parse "stash@{0}"
```

stash が使えない構成の場合は代替として `git diff -- Delta_Engine_Pro4web/ > task2_predrop_20260801.patch` と `git diff --cached -- Delta_Engine_Pro4web/ > task2_predrop_cached_20260801.patch` を保存し、両ファイルのバイト数と SHA-256 を報告する。捕獲物の識別子(stash ref または patch の SHA-256)を報告に必須で記載する。

### 2-2. 汚染範囲の確認(安全弁B: 4パス限定)

退避前の dirty が次の4パスだけであったことを 2-1 の `git status --porcelain` / `git diff --name-only` 出力で確認する。5パス目が1つでも存在したら停止・報告。

```text
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/static/index.html
Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
```

Task 1 の2ファイル(`heatmap_frame_source.py`、そのテスト)、`phase0c_storage_sizing_20260728/` 等の未追跡データ、HEATMAP文書は触らない。

### 2-3. 基準一致の確認(安全弁C: 2fea7ef バイト一致)

退避後、保護ファイルを基準へ戻し、基準に対する差分が空であることを確認する。

```powershell
git checkout 2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4 -- Delta_Engine_Pro4web/webapp/main.py Delta_Engine_Pro4web/webapp/static/index.html
git rm -f --ignore-unmatch Delta_Engine_Pro4web/webapp/heatmap_replay_task.py Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
git diff 2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4 -- Delta_Engine_Pro4web/webapp/main.py Delta_Engine_Pro4web/webapp/static/index.html
```

最後の `git diff` 出力が空(main.py / index.html が基準とバイト一致)であること、新規2ファイルが作業ツリーから消えていること、Task 1 の2ファイルが無傷であることを確認する。1つでも外れたら停止・報告。

---

## 3. 再実装(v1.0 の D1-D6 をそのまま適用)

参照 v1.0 指示(SHA `27a1e161...`)の D1-D6 をアンカー文字列ベースで適用する。行番号ベース不可。概要は次の通り(正は v1.0 の該当条文)。

- 新規 `Delta_Engine_Pro4web/webapp/heatmap_replay_task.py`
  - `heatmap_replay_loop(send, *, recording_dir, interval_ms, sample_interval_ms, depth_levels, symbol, sleep=asyncio.sleep)`。
  - `iter_book_projections` を同期 for で回し各 projection を `await send`。間隔待機は `delay_sec = interval_ms / 1000` を用い、`float()` を書かない。send 失敗は isolate、CancelledError は再送出、再生は1回。
- 新規 `Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py`。
- `main.py` D1-D5(import / env解決 / book_projection_pump排他化 / heatmap_replay_task生成 / tasks登録)。
- `index.html` D6(UI gate `ORDER_BOOK_HEATMAP_ENABLED` を false→true)。
- env: `HEATMAP_REPLAY_ENABLED`(既定 false)、`HEATMAP_REPLAY_DIR`(既定 `DEPTH_HISTORY_ROOT/symbol=<symbol>`)、`HEATMAP_REPLAY_INTERVAL_MS`(100)、`HEATMAP_REPLAY_SAMPLE_INTERVAL_MS`(1000)。docker-compose は変更しない(既定 false 据え置き)。

### 3-1. 供給網羅性 不変条件(本書の追加要件・必須)

UI gate が true のとき、book チャネルの BOOK_UPDATE 供給者は常に「ちょうど一つ」稼働していなければならない。gate=true かつ供給なしの起動経路を残してはならない。

分岐は `HEATMAP_REPLAY_ENABLED` を鍵とする全域的 if/else とする(第三の状態を作らない)。

```text
if HEATMAP_REPLAY_ENABLED:
    replay task を起動し、live book_projection_pump は起動しない
else:
    live book_projection_pump を起動し、replay task は起動しない
```

「どちらも起動しない」経路、および「両方起動する」経路を実装上作らないこと。v1.0 の D3(排他化)/ D4(生成)がこの全域 if/else を成すことを確認しながら適用する。

### 3-2. 空供給ガード(本書の追加要件・必須)

`HEATMAP_REPLAY_ENABLED=true` かつ `HEATMAP_REPLAY_DIR`(未指定時は `DEPTH_HISTORY_ROOT/symbol=<symbol>`)が実在しない、または depth_history_raw のサンプルを1件も含まない場合、起動時に明示的エラーで停止(raise + ログ)すること。gate=true のまま空Canvasで沈黙起動する経路を作らない。この判定は replay を選んだ else 側では評価しない(live通常起動に影響を与えない)。

---

## 4. 停止条件(調査→承認→実装)

§3-1 / §3-2 を v1.0 の D1-D6 アンカー範囲内(特に D4 のreplay task生成領域)で表現できる場合はそのまま適用してよい。もし空供給ガード(§3-2)が v1.0 の既存アンカー編集の内側で表現できず、新規アンカーによる保護ファイル追記が必要になる場合は、実装を進めず停止し、追加するアンカーの before/after 差分案を報告して統括承認を待つこと。保護ファイルへのアンカー追加は承認前に適用しない。

---

## 5. 二経路の起動検証(compose既定 false のまま、別々に実施)

### 5-1. 経路A: live通常起動

既定(`HEATMAP_REPLAY_ENABLED` 未設定=false、gate=true)で起動する。

- 期待: live `book_projection_pump` が稼働、replay task は非稼働。
- BOOK_UPDATE が live book から流れ、ブラウザで Heatmap Canvas が動的描画されることを目視。
- ログで「供給者はちょうど一つ(live)」を確認。二重供給がないこと。

### 5-2. 経路B: replay override起動

env override で `HEATMAP_REPLAY_ENABLED=true`、`DEPTH_HISTORY_ROOT` を実在の `depth_history_raw` に向けて起動する(compose には書かない)。

- 期待: replay task が稼働、live `book_projection_pump` は非稼働。
- recording から BOOK_UPDATE が流れ、Canvas の動的スクロール描画を目視(depth_history_raw → iter_book_projections → heatmap_replay_loop → broker.on_book_update → WebSocket BOOK_UPDATE → index.html onBookUpdate → HEATMAP_UI.ingestBook → Canvas)。
- ログで「供給者はちょうど一つ(replay)」を確認。

### 5-3. 経路B負例: 空供給ガードの発火

`HEATMAP_REPLAY_ENABLED=true` かつ存在しない/空の recording root で起動し、§3-2 のとおり明示的エラーで停止すること(gate=true のまま空Canvasで起動しないこと)を確認する。

---

## 6. 検証条件(テスト)

- replay loop の全 projection 送信、send 例外の隔離、CancelledError 再送出、待機間隔を検証。
- recording directory / sample interval / depth levels / symbol の引き渡しを検証。
- `HEATMAP_REPLAY_ENABLED=true` 時に live book projection task が起動しないこと、false 時に replay task が起動しないことを検証(全域 if/else の両側)。
- 空供給ガード(§3-2)の発火を検証。
- gate 有効状態に対応した UI guard test を更新。
- 既知1件以外の新規 pytest failure がないこと(`python -m pytest -q -p no:cacheprovider` を `Delta_Engine_Pro4web/` から実行)。

---

## 7. コミット前ゲート(第七コミット、全て満たすこと)

1. Task 1 の2ファイルを変更・stage しない。
2. `main.py` / `index.html` は承認済みアンカー(D1-D6、§4承認分を含む)以外を変更しない。staged diff がアンカー範囲のみであることを精査。
3. 新規2ファイルの SHA-256 / byte / LF / CR を記録。
4. Task 2 新規範囲で `float(` を使用しない(間隔秒は `interval_ms/1000`)。
5. `git diff --cached --name-only` が承認済み4対象だけになる。
6. 供給網羅性: gate=true で供給なしの起動経路が存在しないこと(全域 if/else + 空供給ガードをテストと経路B負例で実証)。
7. 二経路検証(経路A / 経路B)が両方成功。二重供給なし。
8. 既知failure以外の新規 pytest failure なし。

いずれか1つでも外れたら commit せず停止・報告。`git add` は統括の独立検証合格後に限る。

---

## 8. 報告物(統括の独立検証用・実物で提出)

- §2-1〜2-3 の全コマンド出力(退避識別子=stash ref または patch の SHA-256/byte を含む)。
- 巻き戻し後の `git diff 2fea7ef -- main.py index.html` が空である出力、新規2ファイル消滅の確認、Task 1 無傷の確認。
- 再実装後の新規2ファイルの全文。
- 新規2ファイルの SHA-256 / byte / LF / CR。
- `main.py` / `index.html` の git diff(D1-D6)。
- `float(` 走査結果(Task 2 範囲 0件)。
- pytest 出力(既知1 fail、新規 fail なし)。
- 経路A / 経路B / 経路B負例の起動ログと Canvas 描画の確認記録。
- `git diff --cached --name-only`(承認済み対象のみ)。

以上。
