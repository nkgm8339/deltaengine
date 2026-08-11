# 指示書: 第三コミット Absorption realtime
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第二コミット完了(HEAD 3be272c)。確定事項:
- pipeline.pyの差分はabsorption純粋(全hunk absorption、差分float0、on_accepted_traderはHEAD既存で行シフトのみ)。
- test_absorption_realtime_display.pyはtime_sales.js非依存(onAcceptedTrades×, time_sales×)。依存は_observe_absorption_state(pipeline)とPushBroker(commit済)。
- index.htmlの差分はabsorptionのみ(DOM Trade Pulse配線2431/1095はHEAD既存=差分外)。
- time_sales.jsはDOM Trade Pulse機能で本コミット対象外(第五で別途)。
統括の承認: 統括はpipeline.py全差分・main.py absorption hunk・index.html差分・test全文を検証済み。独立指標原則(absorptionネイティブ配信、合成なし)適合。保護ファイルmain.py/index.htmlのabsorption変更を承認する。

---

## 1. 絶対規律
- 対象4ファイルのみ。うちmain.pyはabsorption hunkのみを部分stageせよ。他ファイルは全体add。
- time_sales.js, docker-compose.yml, pipeline.pyのpersistent部分(該当なし)等を混入させるな。
- ソースを変更するな(git add -p の 'e' で行を書き換えるな。既存行の選択のみ)。

## 2. commit対象
全体add(3ファイル):
```
Delta_Engine_Pro4web/src/pipeline.py
Delta_Engine_Pro4web/webapp/static/index.html
Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py
```
部分add(1ファイル、absorption hunkのみ):
```
Delta_Engine_Pro4web/webapp/main.py
```

## 3. 手順

### S1. pipeline float再走査(差分追加行)
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/src/pipeline.py | grep -nE "^\+" | grep "float("
```
0件を確認(1件でも停止・報告)。

### S2. 全体add(3ファイル明示)
```
git -C <root> add \
  Delta_Engine_Pro4web/src/pipeline.py \
  Delta_Engine_Pro4web/webapp/static/index.html \
  Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py
```

### S3. main.py 部分add(absorption hunkのみ)
```
git -C <root> add -p Delta_Engine_Pro4web/webapp/main.py
```
各hunkの選択基準(判断は機械的に文字列で行え):
- hunkに `on_absorption_state_cb` または `pipeline.on_absorption_state` を含む → y(stageする)
- hunkに `PersistentDepthWriter` / `persistent_writer` / `persistent_enabled` を含む → n(除外)
- 上記どちらも含まないhunk → n(除外)
- 1つのhunkにabsorptionとpersistentが同居する場合のみ s で分割を試み、分割後も同居する行は e を使わず n とし、直ちに停止して報告せよ(統括が別途対応)。

### S4. staged内容の検証(commit前、必ず提出)
```
git -C <root> diff --cached --name-only
git -C <root> diff --cached -- Delta_Engine_Pro4web/webapp/main.py | grep -nE "PersistentDepthWriter|persistent_writer|persistent_enabled"
git -C <root> diff --cached -- Delta_Engine_Pro4web/webapp/main.py | grep -nE "on_absorption_state"
```
判定基準(いずれか外れたら`git reset`で全解除し停止・報告):
- name-onlyが対象4ファイル(pipeline.py, index.html, test_absorption_realtime_display.py, main.py)と完全一致。
- main.py staged に persistent系文字列が **0件**。
- main.py staged に `on_absorption_state` が **1件以上**。

### S5. commit(メッセージ固定)
```
git -C <root> commit -m "feat(webapp): wire tick-time absorption state to realtime display

pipeline emits on_absorption_state via _observe_absorption_state; main.py
bridges it to PushBroker.on_absorption_state; index.html renders the
ABSORPTION_STATE payload with analysis-fallback preserved. Adds
test_absorption_realtime_display.py. Persistent-writer hunks in main.py
are intentionally excluded (deferred to a later commit)."
```

### S6. commit後証跡
```
git -C <root> show --stat HEAD
git -C <root> rev-parse HEAD
git -C <root> status --porcelain
```
- 新HEAD SHA提出。
- pipeline.py, index.html, test_absorption_realtime_display.py がM/??から消えること。
- main.py が **Mのまま残る**こと(persistent hunk未commitのため)。time_sales.js, docker-compose.yml もMのまま。

### S7. pytest
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ・FAILED行提出。773 passed維持・既知failureのみ。test_absorption_realtime_display.pyの3テスト通過を含む。

## 4. 提出物
- S1 float走査
- S4 name-only + main.py staged の persistent/absorption grep(判定の生出力)
- S6 show --stat・新HEAD・status
- S7 pytestサマリ・FAILED行
- pipeline.py, index.html, test_absorption_realtime_display.py, main.py のcommit後SHA-256

## 5. 禁止事項
- 対象外ファイルのadd、main.pyへのpersistent hunk混入。
- git add -p の 'e'(手編集)によるソース改変。
- S4判定を外れたままのcommit続行。
- commitメッセージ改変。

以上。正常完了後、統括が第四コミット(persistent depth writer = main.py persistent hunk + docker-compose)の指示書を発行する。
