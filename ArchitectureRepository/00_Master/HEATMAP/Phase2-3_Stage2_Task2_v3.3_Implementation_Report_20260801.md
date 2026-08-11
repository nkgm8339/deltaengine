# Stage2 Task2 v3.3 実装報告（案C）

実施日: 2026-08-01  
基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`  
commit: 未実施（統括独立検証待ち）

## 方針変更

Stage1cの実物調査に基づき、pipeline replay検証モードのHeatmap空表示は仕様として許容し、v3.2のfail-fastを撤去した。`config.replay.enabled=false` の本番live経路では、`HEATMAP_REPLAY_ENABLED=false` がlive pump、trueがreplay taskとなる排他構造を維持している。

## 変更対象

- `Delta_Engine_Pro4web/webapp/heatmap_replay_task.py`（新規）
- `Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py`（新規）
- `Delta_Engine_Pro4web/webapp/main.py`（D1/D2/D3/D4/D5/D7a-1/D7a-2/D7b。replay×false fail-fastは撤去）
- `Delta_Engine_Pro4web/webapp/static/index.html`（D6 gate true）
- `Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py`（gate期待値更新）

Task 1の2ファイル、`src/heatmap/reconstruct.py`、docker-compose、`tests/webapp/test_book_update.py`は変更していない。stagingも空。

## 退避

- tracked stash: `22cd5fa5159b28a9654eb9243ddf336faaf6b5c2`
- untracked退避先: `C:\tmp\task2_predrop_untracked_20260801`
- 旧`heatmap_replay_task.py`: SHA `4ED34226A17F081BCAAB3B0302FF5FED49FE691E7CABB5737C907B4CCCA188B3`, 1273 bytes
- 旧`test_heatmap_replay_task.py`: SHA `2CD4933EFDF82A6A7F992C222BDBEA80112492E10ECF3AAD988CA730EEB3AF01`, 4219 bytes

## 現行新規ファイル計測

- `heatmap_replay_task.py`: SHA `BB53DEBCBC4CB857ACC95A2BAAADB50FA8660F91D5B37A98A17CA9237D1FAE37`, 1853 bytes, LF 59, CR 0
- `test_heatmap_replay_task.py`: SHA `FDE3A6A0BE9A9881A52218DE3FE6188A68AD7C1762D32494E100A549DC1130E4`, 5914 bytes, LF 198, CR 0
- `float(`走査: 0件
- `git diff --check`: 空

## テスト

対象テスト:

```text
33 passed in 3.29s
```

全体pytest:

```text
1 failed, 790 passed, 1 skipped in 132.35s
```

唯一のfailure:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

これはv3.2以前からの既知failureで、新規failureは発生していない。

## 現行status

```text
 M Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
```

`git diff --cached --name-only`: 空。commitは未実施。

