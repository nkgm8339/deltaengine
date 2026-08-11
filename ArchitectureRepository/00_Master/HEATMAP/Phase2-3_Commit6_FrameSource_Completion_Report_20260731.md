# Phase 2-3 第六コミット frame_source（Task 1成果）完了報告

- 実施日: 2026-07-31
- 実施前HEAD: `bf9512635d7a6f4d67a14d67d128fc528f6b6707`
- 実施後HEAD: `2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`
- 結果: 完了
- commit対象: 下記新規2パスのみ
  - `Delta_Engine_Pro4web/webapp/heatmap_frame_source.py`
  - `Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py`
- Task 2（供給経路、stream_id/sequence、WebSocket、gate有効化）: 未着手

## 事前確認

実施前HEAD:

```text
bf9512635d7a6f4d67a14d67d128fc528f6b6707
```

対象2ファイルの実施前status:

```text
?? Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
?? Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
```

実施前のstagingは空だった。

対象2ファイルの事前SHA-256:

```text
15C8DAC80B0AF5DD0DFB497325CA2B236D7892C5D767CECA9DB15B05633E8B7F  Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
4BCCD018D0E5D3E48BEEEED575068887E00950D94FE26AF5E49A53D6706F1450  Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
```

統括申告値と完全一致した。

## S1. add（2パス明示）

実行対象:

```powershell
git -C <root> add -- `
  Delta_Engine_Pro4web/webapp/heatmap_frame_source.py `
  Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
```

ワイルドカード、ディレクトリadd、`git add .`、`git add -A`は使用していない。

Gitから次の改行警告が出たが、add自体は成功した。

```text
warning: in the working copy of 'Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py', LF will be replaced by CRLF the next time Git touches it
warning: in the working copy of 'Delta_Engine_Pro4web/webapp/heatmap_frame_source.py', LF will be replaced by CRLF the next time Git touches it
```

## S2. commit前staging確認

### git diff --cached --name-only

```text
Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
```

指定2パスと集合として完全一致し、過不足0件。`git diff --cached --check`もPASSした。

## S3. commit

固定commitメッセージ:

```text
feat(heatmap): add recording-backed book projection source

SnapshotBookStateAdapter wraps reconstructed OrderBookSnapshots through
build_book_projection to yield BookProjection streams from depth-history
recordings, sharing the live projection core (ADR replay/live parity).
Producer wiring (stream_id/sequence, WebSocket, gate) is deferred to Task 2.
```

commit生出力:

```text
[feature/footprint-dom-tape 2fea7ef] feat(heatmap): add recording-backed book projection source
 2 files changed, 250 insertions(+)
 create mode 100644 Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
 create mode 100644 Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
```

## S4. commit後証跡

### git show --stat HEAD

```text
commit 2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4
Author: unknown <ksckk0126@gmailcom>
Date:   Fri Jul 31 23:19:22 2026 +0900

    feat(heatmap): add recording-backed book projection source
    
    SnapshotBookStateAdapter wraps reconstructed OrderBookSnapshots through
    build_book_projection to yield BookProjection streams from depth-history
    recordings, sharing the live projection core (ADR replay/live parity).
    Producer wiring (stream_id/sequence, WebSocket, gate) is deferred to Task 2.

 .../tests/webapp/test_heatmap_frame_source.py      | 184 +++++++++++++++++++++
 .../webapp/heatmap_frame_source.py                 |  66 ++++++++
 2 files changed, 250 insertions(+)
```

### git rev-parse HEAD

```text
2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4
```

### commit対象パス

```text
Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
```

### git status --porcelain -- Delta_Engine_Pro4web/

```text
?? Delta_Engine_Pro4web/phase0c_storage_sizing_20260728/
```

対象2ファイルは`??`から消えた。`Delta_Engine_Pro4web/`配下に残るstatusは、開始前から存在する未追跡データディレクトリ`phase0c_storage_sizing_20260728/`だけである。tracked dirtyは0件。

commit直後およびpytest後のstagingは空だった。

## S5. pytest

実行コマンド:

```powershell
cd Delta_Engine_Pro4web
python -m pytest -q -p no:cacheprovider
```

FAILED行とサマリの生出力:

```text
FAILED tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
1 failed, 780 passed, 1 skipped in 128.00s (0:02:08)
```

failureは既知のHeatmap layout selectorと旧testの不一致1件のみ。新規failureは0件で、`780 passed`を維持した。

## commit後SHA-256

```text
15C8DAC80B0AF5DD0DFB497325CA2B236D7892C5D767CECA9DB15B05633E8B7F  Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
4BCCD018D0E5D3E48BEEEED575068887E00950D94FE26AF5E49A53D6706F1450  Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
```

両SHA-256は統括申告値と完全一致し、pytest後も不変だった。

## 最終状態と次の境界

- 第六コミットは指定2パスだけで完了した。
- 新HEADは`2fea7efebbe64b86b3a62bf1645ffcf3d3946dd4`。
- 対象2ファイル以外をaddしていない。
- 既存ファイルを変更していない。
- Task 2には着手していない。
- Task 2は保護ファイル接触を含むため、統括の明示承認と調査指示書を待つ。
