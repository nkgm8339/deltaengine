# Stage2 Task2 v3.2 実装停止報告

実施日: 2026-08-01  
基準HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`  
状態: **commit停止**

## 退避

- tracked差分stash: `22cd5fa5159b28a9654eb9243ddf336faaf6b5c2`
- untracked退避先: `C:\tmp\task2_predrop_untracked_20260801`
- `heatmap_replay_task.py`: SHA-256 `4ED34226A17F081BCAAB3B0302FF5FED49FE691E7CABB5737C907B4CCCA188B3`, 1273 bytes
- `test_heatmap_replay_task.py`: SHA-256 `2CD4933EFDF82A6A7F992C222BDBEA80112492E10ECF3AAD988CA730EEB3AF01`, 4219 bytes

退避後、基準との差分は空、`Delta_Engine_Pro4web/`配下の未追跡はphase0cのみとなることを確認した。その後v3.2実装を新規適用した。

## 実装済み差分

- `webapp/heatmap_replay_task.py`: precheck、0 projection raise、永続callback連携用loop
- `tests/webapp/test_heatmap_replay_task.py`: 8 tests
- `webapp/main.py`: D1/D2/D3/D4/D5、D7a-1/D7a-2/D7b
- `webapp/static/index.html`: gate true
- `tests/webapp/test_orderbook_heatmap_ui.py`: gate期待値とテスト名更新

対象新規ファイルの現行SHA/byte:

- `heatmap_replay_task.py`: SHA-256 `BB53DEBCBC4CB857ACC95A2BAAADB50FA8660F91D5B37A98A17CA9237D1FAE37`, 1853 bytes
- `test_heatmap_replay_task.py`: SHA-256 `2FE2139E06F9EFAF1396D45CECF8F3FB7C82BEEBC0D3246645185979265B8C24`, 5298 bytes

`float(`走査は0件。`git diff --check`は空。stagingは空。

## テスト

対象テスト:

```text
14 passed in 1.27s
```

全体pytest:

```text
4 failed, 785 passed, 1 skipped in 136.76s
```

失敗:

1. `tests/webapp/test_api.py::test_replay_does_not_start_live_oi_poller`
2. `tests/webapp/test_api.py::test_replay_does_not_start_live_book_projection`
3. `tests/webapp/test_api.py::test_replay_worker_callbacks_reach_websocket_with_market_time`
4. `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`（既知failure）

最初の3件は、v3.2で追加した `config.replay.enabled=true` かつ `HEATMAP_REPLAY_ENABLED=false` の起動時fail-fastにより発生した新規failureである。既存テストはreplay設定だけを有効にして起動を期待しているため、v3.2の承認設計と既存テスト期待値が衝突している。

指示書の「既知failure以外の新規failが出たら停止」に該当するため、git add/commitへ進めない。

## 現在のstatus

```text
 M Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
 M Delta_Engine_Pro4web/webapp/main.py
 M Delta_Engine_Pro4web/webapp/static/index.html
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
?? Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
```

`git diff --cached --name-only` は空。コミットは未実施。

## 次の承認が必要な事項

fail-fast仕様を維持するなら、上記3つの`tests/webapp/test_api.py`をflag必須の期待値へ更新する必要がある。しかしv3.2の第七コミット対象は5ファイルで、`test_api.py`は対象外である。

したがって、次のいずれかを統括承認するまで停止する。

- `test_api.py`を第6対象として更新する
- replayテスト起動時に`HEATMAP_REPLAY_ENABLED=true`を明示するテストfixture等を別途承認する
- fail-fast条件の実装範囲を再設計する
