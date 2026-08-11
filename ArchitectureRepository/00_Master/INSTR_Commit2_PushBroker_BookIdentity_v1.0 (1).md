# 指示書: 第二コミット push_broker.py + test_book_update.py(HEAD不整合是正)
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第一コミット完了(HEAD 6c5a8b25)。push_broker.py差分材料(Diff Materials v1.0)で、book識別子/absorption/persistentがHunk2/6で行レベル物理混在と確定。hunk分割不能のためファイル単位でcommitする。
統括の承認: 統括はpush_broker.py全差分・test_book_update.py差分(追加のみ)を検証済み。on_absorption_stateは独立指標配信で独立指標原則に適合、persistent appendはNoneガード付き、float()なし。保護ファイルtest_book_update.pyの変更を承認する。Codexは本指示を実行せよ。

---

## 1. 絶対規律
- 下記2パスのみをaddせよ。ワイルドカード・ディレクトリadd・`git add -p`・部分ステージを禁ずる(混在のため全体add)。
- 他ファイル(main.py, index.html, docker-compose.yml, pipeline.py, time_sales.js 等)を一切addするな。
- ソースを一切変更するな。add と commit のみ。

## 2. commit対象(この2パスのみ)
```
Delta_Engine_Pro4web/webapp/push_broker.py
Delta_Engine_Pro4web/tests/webapp/test_book_update.py
```

## 3. 手順

### S1. commit前 float走査(push_broker.py)
```
grep -n "float(" Delta_Engine_Pro4web/webapp/push_broker.py
```
ヒット0件を確認せよ。1件でもあれば停止し報告(commitへ進むな)。

### S2. add(2パス明示)
```
git -C <root> add \
  Delta_Engine_Pro4web/webapp/push_broker.py \
  Delta_Engine_Pro4web/tests/webapp/test_book_update.py
```

### S3. staging確認(commit前、必ず提出)
```
git -C <root> diff --cached --name-only
```
出力が上記2パスと完全一致すること。過不足があれば`git reset`で空に戻し停止・報告。

### S4. commit(メッセージ固定)
```
git -C <root> commit -m "fix(webapp): emit book stream identity and sequence in BOOK_UPDATE

Producer side of the book_stream_id/book_sequence contract that HEAD's
orderbook_heatmap.js already validates, resolving the HEAD-only mismatch.

push_broker.py is inseparable at hunk level, so this commit also carries
the currently-unwired absorption-state method and persistent-writer hook
(both no-op until their callers are committed). test_book_update.py adds
sequence-contiguity and stream-restart tests."
```

### S5. commit後証跡(全提出)
```
git -C <root> show --stat HEAD
git -C <root> rev-parse HEAD
git -C <root> status --porcelain
```
- 新HEAD SHAを提出。
- statusで push_broker.py と test_book_update.py が M から消え、残りのM群(main.py, index.html, docker-compose.yml, pipeline.py, time_sales.js 等)がMのまま残ることを確認せよ。

### S6. pytest
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ行・FAILED行を提出。773 passed維持・既知failure(test_dom_tape_fusion_ui.py)のみを確認する。book_sequence連続性・stream再起動テストが新実装で通ることを含む。

## 4. 提出物
- S1 float走査結果
- S3 diff --cached --name-only 生出力
- S5 show --stat・新HEAD・status --porcelain 生出力
- S6 pytestサマリ・FAILED行
- push_broker.py と test_book_update.py のcommit後SHA-256

## 5. 禁止事項
- 2パス以外のadd、部分ステージ、ソース変更。
- commitメッセージ改変。
- S3過不足時のcommit続行。

以上。正常完了後、統括が第三コミット(Absorption realtime = main.py absorption hunk + index.html + test_absorption_realtime_display.py)の指示書を発行する。
