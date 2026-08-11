# Phase 2-3 Stage 2 Task 2 第七コミット指示書レビュー

レビュー対象: `INSTR Phase 2-3 Stage 2 Task 2 第七コミット Version 1.0`

レビュー時HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`

## 結論

指示書のcommit対象・stage手順・numstat・commit直前pytest条件は、現在の作業ツリー構造と概ね一致する。ただし、補遺検証未完了のため、現時点ではcommit手順へ進めない。

## 整合している点

- 現在の変更は、指定された新規2ファイル、`main.py`、`index.html`だけである。`Delta_Engine_Pro4web/webapp/heatmap_replay_task.py:1-42`、`Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py:1-163`、`Delta_Engine_Pro4web/webapp/main.py:56`、`Delta_Engine_Pro4web/webapp/main.py:138-141`、`Delta_Engine_Pro4web/webapp/main.py:384-410`、`Delta_Engine_Pro4web/webapp/main.py:598-599`、`Delta_Engine_Pro4web/webapp/static/index.html:969`
- 新規2ファイルの実装報告記載SHAは現在のファイル値と一致する。`Delta_Engine_Pro4web/webapp/heatmap_replay_task.py:1-42`、`Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py:1-163`
- D1-D5のmain.py差分はimport、env解決、live book pump排他、replay task生成、task登録に限定されている。`Delta_Engine_Pro4web/webapp/main.py:56`、`Delta_Engine_Pro4web/webapp/main.py:138-141`、`Delta_Engine_Pro4web/webapp/main.py:384-410`、`Delta_Engine_Pro4web/webapp/main.py:598-599`
- D6は`ORDER_BOOK_HEATMAP_ENABLED`の1行変更である。`Delta_Engine_Pro4web/webapp/static/index.html:969`
- 現行guard testはfalseを要求しているため、D6のtrue化と直接衝突する。`Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:9-14`
- 新規test単体は4 passed、gate更新前の全pytestは783 passed、2 failed、1 skippedだった。`ArchitectureRepository/00_Master/HEATMAP/Phase2-3_Stage2_Task2_SupplyPath_Gate_Implementation_Report_20260801.md:296-336`

## 進行を止める未確認事項

### 1. 補遺ファイルをworkspaceで確認できない

指示書は`INSTR_Stage2_Task2_Addendum_GateTest_v1.0.md`とSHA `5f8208cd...`の独立検証を前提にしているが、現在の`ArchitectureRepository/00_Master/HEATMAP/`には該当ファイル名が存在しない。検索で確認できたTask 2関連ファイルは次のとおりで、指定された補遺そのものではない。`ArchitectureRepository/00_Master/HEATMAP: directory listing`

- `Phase2-3_Stage2_Task2_SupplyPath_Gate_Investigation_Report_20260731.md`
- `Phase2-3_Stage2_Task2_SupplyPath_Gate_Implementation_Report_20260801.md`
- `Phase2-3_Stage2_Task2_Anchor_Materials_20260801.md`
- `Instruction_P22_Task2_Submit_v1.md`
- `Approval_P22_Task2_Go_Task3.md`

したがって、指示書自身の前提2「補遺報告到着後に確認」は未充足である。

### 2. 実行時envと到達点の記述に条件がある

- replay taskは`HEATMAP_REPLAY_ENABLED`がtrueのときだけ生成される。defaultはfalse。`Delta_Engine_Pro4web/webapp/main.py:138`、`Delta_Engine_Pro4web/webapp/main.py:398-410`
- replay recording rootは`DEPTH_HISTORY_ROOT`から解決される。`Delta_Engine_Pro4web/webapp/main.py:139`
- 現在のComposeには`HEATMAP_REPLAY_ENABLED`、`HEATMAP_REPLAY_INTERVAL_MS`、`HEATMAP_REPLAY_SAMPLE_INTERVAL_MS`の指定がない。`Delta_Engine_Pro4web/docker-compose.yml:20-31`
- したがって、Composeの既存envだけではgateはtrueでもreplay供給taskは起動しない。`Delta_Engine_Pro4web/webapp/main.py:138-141`、`Delta_Engine_Pro4web/webapp/main.py:398-410`

指示書の残課題にある「`HEATMAP_REPLAY_DIR` env非読み取り疑義」は、実装上の変数名と一致しない。実装が読むのは`DEPTH_HISTORY_ROOT`であり、`HEATMAP_REPLAY_DIR`というenvは存在しない。`Delta_Engine_Pro4web/webapp/main.py:138-141`

このため、到達点の「gate有効化済、供給経路接続済」はコード経路については成立するが、runtime供給の実起動は`HEATMAP_REPLAY_ENABLED=true`の外部設定がある場合に限られる。`Delta_Engine_Pro4web/webapp/main.py:138-141`、`Delta_Engine_Pro4web/webapp/main.py:398-410`

### 3. pytest期待値784は補遺適用後にのみ確認可能

現在のgate guard testはfalseを要求する。`Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:9-14`

補遺でその1行をtrueへ更新すれば、現在の新規failure 1件が消え、783 passedから784 passedになる見込みだが、補遺実物と更新後の独立検証結果が未提示のため、現時点では実測済み事実ではない。`Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:11`

## 現在のGit状態

```text
HEAD 2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4

 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
```

stagingは空である。

## 必要な確認

1. 指示書で参照している補遺ファイル本体、またはその正本パスとSHAをworkspaceへ提示する。
2. 補遺適用後のtest差分が`test_orderbook_heatmap_ui.py`の1行だけであることを確認する。
3. 補遺適用後に全pytestが784 passed、1 failed、1 skippedとなることを実測する。
4. runtimeでreplay供給を使う場合、`HEATMAP_REPLAY_ENABLED=true`等の設定がどこから供給されるかを明記する。

上記確認が済むまで、5ファイルのstage・commit手順には進まない。
