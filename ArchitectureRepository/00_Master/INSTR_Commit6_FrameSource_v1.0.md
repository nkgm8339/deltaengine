# 指示書: 第六コミット frame_source(Task 1成果)
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: Task 1実装を統括が独立検証済み(frame_source SHA一致15c8dac、float0、build_book_projection再現でテスト7ケース期待値一致、pytest780)。保護ファイル非接触の新規2ファイル。HEAD bf95126。
統括の承認: webapp/heatmap_frame_source.py と tests/webapp/test_heatmap_frame_source.py の内容を承認。commitする。

---

## 1. 絶対規律
- 下記2パスのみをaddせよ。ワイルドカード・ディレクトリadd(`git add .`, `-A`)禁止。
- 既存ファイルを一切add/変更するな。

## 2. commit対象(この2パスのみ)
```
Delta_Engine_Pro4web/webapp/heatmap_frame_source.py
Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
```

## 3. 手順

### S1. add(2パス明示)
```
git -C <root> add \
  Delta_Engine_Pro4web/webapp/heatmap_frame_source.py \
  Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_source.py
```

### S2. staging確認(commit前、提出)
```
git -C <root> diff --cached --name-only
```
上記2パスと完全一致すること。過不足あれば`git reset`で解除・停止・報告。

### S3. commit(メッセージ固定)
```
git -C <root> commit -m "feat(heatmap): add recording-backed book projection source

SnapshotBookStateAdapter wraps reconstructed OrderBookSnapshots through
build_book_projection to yield BookProjection streams from depth-history
recordings, sharing the live projection core (ADR replay/live parity).
Producer wiring (stream_id/sequence, WebSocket, gate) is deferred to Task 2."
```

### S4. commit後証跡(提出)
```
git -C <root> show --stat HEAD
git -C <root> rev-parse HEAD
git -C <root> status --porcelain -- Delta_Engine_Pro4web/
```
- 新HEAD SHA提出。
- 2ファイルが`??`から消え、`Delta_Engine_Pro4web/`配下のtracked M/新規??が phase0c_storage_sizing_ の既存データのみになること。

### S5. pytest
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ・FAILED行提出。780 passed維持・既知failureのみ。

## 4. 提出物
- S2 diff --cached --name-only
- S4 show --stat・新HEAD・status
- S5 pytestサマリ・FAILED行
- 2ファイルのcommit後SHA-256(申告: frame_source=15C8DAC80B0AF5DD0DFB497325CA2B236D7892C5D767CECA9DB15B05633E8B7F、test=4BCCD018D0E5D3E48BEEEED575068887E00950D94FE26AF5E49A53D6706F1450)

## 5. 禁止事項
- 2パス以外のadd、既存ファイル変更。
- commitメッセージ改変。

以上。正常完了後、統括がTask 2(供給経路+WebSocket+gate有効化、保護ファイル接触)の調査指示書を発行する。Task 2は保護接触のため着手前に統括の明示承認を要する。
