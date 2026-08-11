# 指示書: 第二コミット push_broker.py + test_book_update.py(HEAD不整合是正)
Version: 1.1
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
改訂理由: v1.0のS1停止条件「ファイル全体でfloat( 0件」が過剰だった。既存コードのfloat(interval_sec)(push_broker.py:84,111、今回差分外)とコメント文字列(:3)を検出して停止した。Codexの停止はv1.0に忠実で正しい。本v1.1でS1を「今回の差分追加行にfloat(が無いこと」に訂正する。他手順はv1.0と同一。
前提: 第一コミット完了(HEAD 6c5a8b25)。push_broker.pyはbook識別子/absorption/persistentがHunk2/6で行レベル物理混在、hunk分割不能のためファイル単位でcommitする。
統括の承認: 統括はpush_broker.py全差分・test_book_update.py差分(追加のみ)を検証済み。差分追加行にfloat()なし(84,111は既存・差分外)。on_absorption_stateは独立指標配信で独立指標原則に適合、persistent appendはNoneガード付き。保護ファイルtest_book_update.pyの変更を承認する。

---

## 1. 絶対規律
- 下記2パスのみをaddせよ。ワイルドカード・ディレクトリadd・部分ステージを禁ずる(混在のため全体add)。
- 他ファイルを一切addするな。ソースを一切変更するな。

## 2. commit対象(この2パスのみ)
```
Delta_Engine_Pro4web/webapp/push_broker.py
Delta_Engine_Pro4web/tests/webapp/test_book_update.py
```

## 3. 手順

### S1. commit前 float走査(差分追加行のみ)
今回のHEADからの差分のうち、追加行(先頭`+`)に限定してfloat(を走査せよ。
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/webapp/push_broker.py | grep -nE "^\+" | grep -n "float("
```
ヒット0件を確認せよ。1件でもあれば停止し、その行を報告(commitへ進むな)。
補足: 既存行(:84,:111のfloat(interval_sec))とコメント(:3)は差分に現れないため、本走査では拾われない。これらは既存負債として別途扱い、本コミットの対象外。

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
push_broker.pyとtest_book_update.pyがMから消え、残りのM群がMのまま残ることを確認せよ。

### S6. pytest
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ行・FAILED行を提出。773 passed維持・既知failure(test_dom_tape_fusion_ui.py)のみを確認。book_sequence連続性・stream再起動テストの通過を含む。

## 4. 提出物
- S1 差分float走査結果(0件)
- S3 diff --cached --name-only
- S5 show --stat・新HEAD・status --porcelain
- S6 pytestサマリ・FAILED行
- push_broker.py と test_book_update.py のcommit後SHA-256

## 5. 禁止事項
- 2パス以外のadd、部分ステージ、ソース変更。
- commitメッセージ改変。
- S1で差分追加行にfloat(が出た場合のcommit続行。

以上。正常完了後、統括が第三コミット(Absorption realtime)の指示書を発行する。
