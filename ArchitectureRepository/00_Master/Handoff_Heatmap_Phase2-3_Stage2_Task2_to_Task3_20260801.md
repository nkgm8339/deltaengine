# 引き継ぎ書: DeltaEngine05M Heatmap Phase 2-3 Stage 2(Task 2 第七コミット直前 → Task 3)

- 作成: 2026-08-01
- 対象リポジトリ: DeltaEngine05M(`C:\Users\user\Desktop\DeltaEngine05M`)
- 基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`(branch: feature/footprint-dom-tape)
- 役割: Claude(web)=統括・検証・指示書作成、Codex=実装。

---

## 0. 再開手順(次に最初にやること)

**重要: Task 2 はまだ第七コミット未完了。「Task 3 の最初から」ではない。** Task 2 の最後の1テスト(本番 live 供給網羅の実挙動テスト)を通し、第七コミットで動的ヒートマップを git に確定させてから Task 3 に入る。順序:

1. Codex から実挙動テスト報告を受領。指示書 `INSTR_Stage2_Task2_LiveSupply_Runtime_Test_v1.0.md`(SHA-256 `74cfdc812df554bb2e0de881b40fb6e943a0f9369fce098a60d975c480a13a86`)発行済・Codex 未着手。受領物は追記後 `tests/webapp/test_heatmap_replay_task.py` 全文+SHA/byte/LF/CR、追加2テストの assert 行、pytest 全文、`git status --porcelain`。
2. 統括が独立検証: 追加2テストが `config.replay.enabled=false` の本番 live 経路で、flag=false→`book_projection_pump.run` が await・`heatmap_replay_loop` 非 await、flag=true→逆、を**実起動**で assert しているか。既知1件以外の新規 fail なし。変更が当該テストファイルのみで保護境界ゼロ。
3. 合格なら第七コミット指示書を発行(`git add` 5ファイル、commit、退避 stash `22cd5fa5159b28a9654eb9243ddf336faaf6b5c2` と `C:\tmp\task2_predrop_untracked_20260801` の後処理)。commit は検証合格後に限る。
4. commit 実行報告を検証 → **Task 2 完了(動的ヒートマップ確定)**。
5. その後 Task 3 着手。

---

## 1. Task 2 の現在地(v3.3 案C・第七コミット直前)

Phase 2-3 Stage 2 の中核。recording 駆動の動的ヒートマップ供給を live Canvas に繋ぐ。実装は working tree に適用済み・commit 未実施。検証パッケージ(SHA-256 `6aa93006d47287ac13bb429394a65c04b51094402140192a27d8533d0f0528da`)を統括が独立照合済み。結果は 1-1〜1-7 合格、1-8(本番 live 供給網羅)のみ実挙動テストで補強中(0章の残タスク)。

第七コミット対象5ファイル:
- `webapp/heatmap_replay_task.py`(新規, SHA `BB53DEBCBC4CB857ACC95A2BAAADB50FA8660F91D5B37A98A17CA9237D1FAE37`, 1853B, LF59)
- `tests/webapp/test_heatmap_replay_task.py`(新規, 実挙動テスト追記で SHA 更新。追記前 SHA `FDE3A6A0BE9A9881A52218DE3FE6188A68AD7C1762D32494E100A549DC1130E4`, 5914B, LF198)
- `webapp/main.py`(保護, D1/D2/D3/D4/D5, D7a-1/D7a-2/D7b)
- `webapp/static/index.html`(保護, D6 gate true 1行)
- `tests/webapp/test_orderbook_heatmap_ui.py`(gate 期待値 true・名称更新)

保護境界(Task 1 の `heatmap_frame_source.py`/その test、`src/heatmap/reconstruct.py`、docker-compose、`tests/webapp/test_book_update.py`)は差分ゼロを照合済み。pytest は 1 failed(既知 `test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_...`)/790 passed/1 skipped、新規 fail ゼロ。

---

## 2. Task 2 の設計経緯(v1.0 → v3.3・なぜ案Cか)

指示書は v1.0(承認済み・不可侵, SHA `27a1e161...`)を土台に、Stage 1/1b/1c 調査で判明した実物事実を解決して版を重ねた。主要な転換:

- fail-fast の撤去(案C): 当初「`config.replay.enabled=true` かつ `HEATMAP_REPLAY_ENABLED=false` は起動時 raise」で供給者ゼロを防ぐ設計(v3.2)だったが、Stage 1c で `config.replay.enabled=true`(pipeline replay 検証モード)は既存 `test_api.py` の複数テストが正当に使うモードと判明。fail-fast が無関係な回帰テスト3件(OI poller/book projection/tape・candle replay)を巻き添えにした。よって fail-fast を撤去し、pipeline replay モードの heatmap 空表示は「pipeline replay は板 heatmap を供給しない」仕様として許容。防御は「本番 live 経路(`config.replay.enabled=false`)で供給者ちょうど一つ」をテストで構造保証する方式へ移した。本番 live では flag=false→live pump、flag=true→replay task が必ず供給し沈黙しない。
- D7 永続フラグ方式: replay task 例外は `_health_loop` の毎周期上書きで消えるため、`app.state.heatmap_replay_failed`(bool, replay task 生成より前に初期化)を done callback が立て、`_health_loop` が毎周期評価して `/api/health` の state を RED 継続。`checks["heatmap_replay"]` はインライン dict(ヘルパー未使用)。`/health` は固定 ok のため対象外。
- 空 recording は A案: `.jsonl.part` は `_is_segment_path` の列挙候補だが manifest 検証を通過した segment のみ完了採用。`ensure_replay_source` は `DepthHistoryReader.segments()` の空判定で raise(手作業カウント禁止)。加えて `heatmap_replay_loop` は 0 projection で raise。`reconstruct.py` は不可侵で未変更。

版の SHA(記録): v3.2=`e1a273c1...`(GO せず・案Cで置換)、以降 v3.3 は指示書化せず案Cで実装が先行(お館様承認)。検証パッケージ指示書=`f9fd515f...`、実挙動テスト指示書=`74cfdc81...`。

---

## 3. Task 3 の内容(Task 2 完了後に着手)

16ms per-frame バジェットの実測。既存 `webapp/static/orderbook_heatmap.js` の `renderTimes`(p95 表示、metrics API)を使うため軽い。gate 有効化後の動的フレームの p95 を実測する。Task 3 完了で Stage 2 の機能到達(Bookmap 相当のリアルタイム動的ヒートマップ)。Phase 3(ライブ WebSocket 接続)はその先。

参照キー: 既存 Canvas `webapp/static/orderbook_heatmap.js`(store/buildBase/renderTimes p95)、gate `webapp/static/index.html:969`、live pump `webapp/main.py`、frame_source `webapp/heatmap_frame_source.py`、build_book_projection `webapp/book_projection.py`、broker payload `webapp/push_broker.py:250-299`、reconstruct/sample_states `src/heatmap/reconstruct.py`。

---

## 4. 検証規律(不可侵)

- Codex の自己申告完了は承認根拠にしない。実物受領→SHA-256/byte/LF/CR 独立照合→`float(` 走査→pytest 維持→内容検証。
- 実物はこの対話に運び込めるものは統括が照合し、運び込めない検証は指示書に手順として書き込み Codex 側で機械判定させる(お館様を実物運搬の伝書鳩にしない)。
- `float()` 禁止(例外は transform.py の最終ピクセル座標のみ)。時間間隔秒は `interval_ms/1000` で `float()` を書かない。
- 保護ファイル(`webapp/main.py`, `docker-compose.yml`, `tests/webapp/test_book_update.py`, `webapp/static/index.html`)は明示承認なしに変更禁止。加えて Task 1 の2ファイルと `src/heatmap/reconstruct.py` も本タスクでは不可侵。
- 指示書はアンカー文字列ベース before/after 差分(行番号ベース不可)。バージョン付き .md + SHA-256。既存指示書は不可侵・追記のみ。
- 2段階フォーマット(調査→承認→実装)。新仕様(fail-fast/gate/env 等)を入れる前に、その条件で起動・分岐する既存テスト(特に `tests/webapp/test_api.py`)への波及を Stage 1 調査に必ず含める(v3.2 の教訓)。
- 独立5指標を合成しない。カラーは bid 青/ask 赤別チャンネル・混合禁止・gap 黒。ADR-003(asyncio 単一ループ)、ADR-011(全量記録)、Replay/Live 同一 applyコア共有。

---

## 5. 退避物・保護・恒久情報

- tracked stash: `22cd5fa5159b28a9654eb9243ddf336faaf6b5c2`(main.py/index.html の旧 Task2 差分)。
- untracked 退避: `C:\tmp\task2_predrop_untracked_20260801`(旧 heatmap_replay_task.py SHA `4ED34226...`/1273B、旧 test SHA `2CD4933E...`/4219B)。
- 未追跡データ `Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/` はリポジトリ衛生の第二段として後日処理(Stage 2 をブロックしない)。
- 電源断リスク: `resume_hook_capture.ps1` が現行イメージ非対応。復旧後は `docker compose up -d` をプロジェクトルートから手動実行。
- 較正値(2026-07-20 適用済): stack_ref 3→5、min_volume 0.5→0.002、cvd_slope_ref 65.203 据え置き(26.5 推奨だが CVD 感度 2.46 倍のため様子見)。

---

## 6. 記録した別 issue(未処理・Stage 2 をブロックしない)

- 既存 float 負債: `push_broker.py` の `float(interval_sec)`(スケジューリング秒、価格精度と無関係)。
- `heatmap_replay_loop` の send 全失敗ケース: 全 projection の send が失敗しても `sent>0` のため 0 projection raise は発火せず health RED にならない(send 失敗 isolate 仕様の帰結)。今回スコープ外だが後日検討。
- ドキュメント整理: 指示書/報告書が `00_Master` 直下と `HEATMAP/` に混在。

以上。
