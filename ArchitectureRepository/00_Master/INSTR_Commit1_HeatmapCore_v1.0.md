# 指示書: 第一コミット heatmapコア6本の単独commit
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 材料収集(Hygiene v1.0)のT2で、下記6ファイルがM群保護ファイルに一切依存しないことを確定。依存先は標準ライブラリ・pytest・HEAD既存OrderBookSnapshot・集合内相互importのみ。T4でpytest劣化なし(1 failed[既知]/773 passed/1 skipped)。
目的: Task 1-4成果を電源断耐性のあるgit確定状態にする。保護ファイルには一切触れない。

---

## 1. 絶対規律
- 下記6パスのみをaddせよ。ワイルドカード・ディレクトリ単位add(`git add .`, `git add -A`, `git add src/heatmap/` 等)を禁ずる。
- M群ファイル(docker-compose.yml, main.py, index.html, test_book_update.py, pipeline.py, push_broker.py, time_sales.js 他)を一切addするな。
- ソースを一切変更するな。add と commit のみ。

## 2. commit対象(この6パスのみ)
```
Delta_Engine_Pro4web/src/heatmap/binner.py
Delta_Engine_Pro4web/src/heatmap/render_static.py
Delta_Engine_Pro4web/src/heatmap/transform.py
Delta_Engine_Pro4web/tests/heatmap/test_binner.py
Delta_Engine_Pro4web/tests/heatmap/test_render_static.py
Delta_Engine_Pro4web/tests/heatmap/test_transform.py
```

## 3. 手順
### S1. add(6パス明示)
```
git -C <root> add \
  Delta_Engine_Pro4web/src/heatmap/binner.py \
  Delta_Engine_Pro4web/src/heatmap/render_static.py \
  Delta_Engine_Pro4web/src/heatmap/transform.py \
  Delta_Engine_Pro4web/tests/heatmap/test_binner.py \
  Delta_Engine_Pro4web/tests/heatmap/test_render_static.py \
  Delta_Engine_Pro4web/tests/heatmap/test_transform.py
```

### S2. staging内容の確認(commit前、必ず提出)
```
git -C <root> diff --cached --name-only
```
出力が上記6パスと完全一致することを確認せよ。1ファイルでも過不足があれば直ちに停止し、`git reset`(mixed)でstagingを空に戻して報告せよ。commitへ進むな。

### S3. commit
```
git -C <root> commit -m "feat(heatmap): add Phase 2-2 static renderer core and unit tests

binner, transform, render_static and their unit tests. No dependency on
in-flight webapp changes. Verified by Hygiene v1.0 T2/T4."
```

### S4. commit後の証跡(全て提出)
```
git -C <root> show --stat HEAD
git -C <root> rev-parse HEAD
git -C <root> status --porcelain
```
- 新HEADのSHAを提出せよ。
- status に、上記6ファイルが消え、M群と残りの未追跡がそのまま残っていることを確認せよ(保護ファイルは M のまま、未変更)。

### S5. pytest再確認
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ行とFAILED行を提出せよ。773 passed / 既知failure のみの維持を確認する。

---

## 4. 提出物
- S2の`diff --cached --name-only`生出力
- S4の`show --stat`・新HEAD・`status --porcelain`生出力
- S5のpytestサマリ・FAILED行
- 6ファイルのcommit後SHA-256(念のため、内容不変の証跡)

## 5. 禁止事項
- 6パス以外のadd、ワイルドカード/ディレクトリadd。
- ソース変更、保護ファイル接触。
- commitメッセージの改変(上記固定)。

以上。S2で過不足が出た場合はcommitせず報告。正常完了後、統括が第二コミット(HEAD不整合是正)の承認可否を返す。
