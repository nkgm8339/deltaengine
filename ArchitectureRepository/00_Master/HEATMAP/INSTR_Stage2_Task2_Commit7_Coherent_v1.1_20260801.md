# INSTR Phase 2-3 Stage 2 Task 2 第七コミット Version 1.1

## 位置づけ

Task 2（recording供給経路＋Heatmap gate）と、gate有効化に伴う既存guard test更新を1コミットで確定する。

本書はworkspaceに存在しない外部補遺へ依存しない。test更新内容を本書に内包する。

前提HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`

## 1. コミット対象（5ファイルのみ）

```text
Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
Delta_Engine_Pro4web/webapp/main.py
Delta_Engine_Pro4web/webapp/static/index.html
Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
```

上記以外はstageしない。`phase0c_storage_sizing_20260728/`、Compose、報告書、その他全ファイルは対象外。

## 2. 実装済み部分と未完了部分

実装済み・未commitは、`heatmap_replay_task.py`、その新規test、`main.py` D1-D5、`index.html` D6である。`Delta_Engine_Pro4web/webapp/heatmap_replay_task.py:1-42`、`Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py:1-163`、`Delta_Engine_Pro4web/webapp/main.py:56`、`Delta_Engine_Pro4web/webapp/main.py:138-141`、`Delta_Engine_Pro4web/webapp/main.py:384-410`、`Delta_Engine_Pro4web/webapp/main.py:598-599`、`Delta_Engine_Pro4web/webapp/static/index.html:969`

未完了はguard test更新と5ファイルのstage／commitである。

## 3. guard test更新（本書に内包する補遺）

gateをfalseからtrueへ変更したため、test関数名と期待値を同時に更新する。関数名だけ古いまま残す1行更新にはしない。

対象: `Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:9-14`

変更前の2行:

```python
def test_heatmap_is_fail_closed_until_operational_activation():
    assert "const ORDER_BOOK_HEATMAP_ENABLED = false;" in source
```

変更後の2行:

```python
def test_heatmap_is_operationally_enabled():
    assert "const ORDER_BOOK_HEATMAP_ENABLED = true;" in source
```

`if(!ORDER_BOOK_HEATMAP_ENABLED)`、`heatmapButton.hidden=true`、`window.HEATMAP_UI=api`のassertは維持する。`Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py:12-14`

この更新の期待numstatは2 insertions / 2 deletionsである。1/1ではない。

## 4. runtime env契約

実装が読むenvは`HEATMAP_REPLAY_ENABLED`、`DEPTH_HISTORY_ROOT`、`HEATMAP_REPLAY_INTERVAL_MS`、`HEATMAP_REPLAY_SAMPLE_INTERVAL_MS`である。`Delta_Engine_Pro4web/webapp/main.py:138-141`

- `HEATMAP_REPLAY_ENABLED`のdefaultはfalse。`Delta_Engine_Pro4web/webapp/main.py:138`
- recording directoryは`DEPTH_HISTORY_ROOT/symbol=<market symbol>`。`Delta_Engine_Pro4web/webapp/main.py:139`
- `HEATMAP_REPLAY_DIR`というenvは使用しない。`Delta_Engine_Pro4web/webapp/main.py:138-141`
- false時はgateがtrueでもreplay taskは起動しない。`Delta_Engine_Pro4web/webapp/main.py:398-410`
- 現行ComposeにはHeatmap replay envがない。`Delta_Engine_Pro4web/docker-compose.yml:20-31`
- 本コミットではComposeを変更しない。runtimeでreplay供給を動かす場合のenv設定は別deployment手順で扱う。

到達点は「gate有効化」と「env有効時の供給経路接続」であり、env未設定runtimeでの供給稼働を意味しない。発注は行わず、observe／可視化のみとする。

## 5. commit前必須条件

次をすべて満たすまでstage／commitしない。

1. 新規2ファイルのSHA、byte、LF、CRが承認値と一致する。
2. 新規2ファイルとguard testの`float(`走査が0件である。
3. `main.py`差分がD1-D5のみ、`index.html`差分がD6の1行のみである。
4. guard test差分が関数名とassertの2行だけである。
5. 新規test単体がpassする。
6. 全pytestが`784 passed, 1 failed, 1 skipped`である。
7. 残るfailureが既知の`tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`だけである。

新規failure、numstat過不足、想定外path、float検出があればstage／commitせず停止する。

## 6. stage手順

```powershell
git add Delta_Engine_Pro4web/webapp/heatmap_replay_task.py
git add Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py
git add Delta_Engine_Pro4web/webapp/main.py
git add Delta_Engine_Pro4web/webapp/static/index.html
git add Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
```

期待cached pathはsection 1の5ファイルだけ。期待numstatは新規test `163 0`、guard test `2 2`、module `42 0`、main `27 1`、index `1 1`である。

## 7. commit直前ゲート

次の出力を取得する。

```powershell
git diff --cached --name-only
git diff --cached --numstat
git diff --cached --check
python -m pytest -q -p no:cacheprovider
rg -n -F "float(" Delta_Engine_Pro4web/webapp/heatmap_replay_task.py Delta_Engine_Pro4web/tests/webapp/test_heatmap_replay_task.py Delta_Engine_Pro4web/tests/webapp/test_orderbook_heatmap_ui.py
```

pytestは`784 passed, 1 failed, 1 skipped`、float走査は0件でなければcommitしない。

## 8. commitメッセージ

```text
feat(heatmap): recording-driven dynamic book supply + gate activation (Phase 2-3 Stage 2 Task 2)

- add heatmap_replay_task.heatmap_replay_loop: replay depth-history as BOOK_UPDATE projections once
- main.py: env-gated heatmap replay task, exclusive with live book_projection_pump (D1-D5)
- index.html: enable ORDER_BOOK_HEATMAP gate at GO-H6 operational activation (D6)
- update orderbook_heatmap_ui guard test to operational-activated gate state
```

## 9. commit後確認

`git show --stat HEAD`、`git rev-parse HEAD`、`git status --porcelain -- Delta_Engine_Pro4web/`、`git diff --cached --name-only`を取得する。HEADの変更が5ファイルだけ、stagingが空、既存phase0c untracked以外の想定外statusがないことを確認する。commit後pytestも`784 passed, 1 failed, 1 skipped`と既知failure 1件を維持する。

## 10. この改訂で解消した点

- workspaceに存在しない`INSTR_Stage2_Task2_Addendum_GateTest_v1.0.md`への依存を除去した。
- 実装に存在しない`HEATMAP_REPLAY_DIR`を参照せず、実際の`DEPTH_HISTORY_ROOT`を契約化した。
- gate有効化後も古いtest名が残る問題を修正対象へ含めた。
- Compose未設定時はgateだけ有効で、replay taskは起動しない条件を明記した。
- guard test更新のnumstatを1/1から意味整合する2/2へ訂正した。
