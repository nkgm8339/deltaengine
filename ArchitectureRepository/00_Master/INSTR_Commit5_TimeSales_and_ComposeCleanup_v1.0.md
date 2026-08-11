# 指示書: 第五コミット time_sales.js + docker-compose空行破棄
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第四コミット完了(HEAD f58f584)。残るソース未commitは docker-compose.yml(空行1行)と time_sales.js(DOM Trade Pulse onAcceptedTradesプロデューサ)のみ。
- time_sales.js: index.htmlのonAcceptedTapeTrades配線(HEAD既存)とtest_orderbook_heatmap_ui.py:58/test_dom_trade_pulse_ui.py:47(HEAD既存)が要求するプロデューサ。第二コミットと同型の片翼是正。
- docker-compose.yml: 末尾空行1行のみの無意味差分。破棄する。
統括の承認: 統括はtime_sales.js差分(onAcceptedTradesフック追加、absorption/book/tape非該当)を検証済み。docker-composeの空行破棄(HEADに戻すのみ、機能変更なし)を承認する。

---

## パートA: 第五コミット(time_sales.js)

### A0. 規律
- time_sales.jsのみをaddせよ。docker-compose.ymlをaddするな。
- ソースを変更するな。
- 注: time_sales.jsはJavaScriptのためPython float禁止規律の対象外。float走査は不要。

### A1. add
```
git -C <root> add Delta_Engine_Pro4web/webapp/static/time_sales.js
```

### A2. staged検証(commit前、提出)
```
git -C <root> diff --cached --name-only
git -C <root> diff --cached -- Delta_Engine_Pro4web/webapp/static/time_sales.js | grep -nE "onAcceptedTrades"
```
判定(外れたら`git reset`で解除・停止・報告):
- name-onlyが `Delta_Engine_Pro4web/webapp/static/time_sales.js` の1行のみ。
- staged に `onAcceptedTrades` が 1件以上。

### A3. commit(メッセージ固定)
```
git -C <root> commit -m "feat(webapp): emit accepted-trade notifications from time_sales store

Producer side of the onAcceptedTrades hook that index.html
(onAcceptedTapeTrades -> DOM Trade Pulse) and UI tests already consume,
resolving the HEAD-only mismatch."
```

### A4. commit後証跡(提出)
```
git -C <root> show --stat HEAD
git -C <root> rev-parse HEAD
```
新HEAD SHAとtime_sales.jsが対象であることを確認。

---

## パートB: docker-compose空行破棄

### B1. 破棄前に空行のみを確認(提出)
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/docker-compose.yml
```
差分が末尾空行1行の追加のみ(実体的な設定変更なし)であることを確認せよ。設定行の追加/削除/変更が1つでもあれば破棄せず停止・報告(統括判断)。

### B2. 破棄(空行のみ確認後)
```
git -C <root> checkout -- Delta_Engine_Pro4web/docker-compose.yml
```

### B3. 破棄後確認(提出)
```
git -C <root> status --porcelain -- Delta_Engine_Pro4web/docker-compose.yml
```
docker-compose.ymlがstatusから消えている(クリーン)ことを確認。

---

## パートC: 最終確認

### C1. ソース衛生の完了確認(提出)
```
git -C <root> status --porcelain -- Delta_Engine_Pro4web/
```
Delta_Engine_Pro4web/配下のソースに M が残らないこと(未追跡?? のデータ/ドキュメント類は対象外)を確認せよ。特に webapp/, src/, tests/webapp/ の .py/.js/.html/.yml に M が無いこと。

### C2. pytest
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ・FAILED行提出。773 passed維持・既知failureのみ。

## 提出物
- A2 staged検証、A4 show --stat・新HEAD
- B1 docker-compose差分、B3 破棄後status
- C1 ソース最終status、C2 pytest
- time_sales.js のcommit後SHA-256

## 禁止事項
- time_sales.js以外のadd(パートAで)、B1で空行以外の差分がある場合の破棄続行。
- commitメッセージ改変。

以上。完了・検証後、ソースのリポジトリ衛生が完了する。統括がPhase 2-3 Stage 2(Canvas 2D動的フレームレンダリング)実装指示書の作成に進む。
