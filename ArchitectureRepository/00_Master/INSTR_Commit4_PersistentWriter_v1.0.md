# 指示書: 第四コミット Persistent depth writer
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第三コミット完了(HEAD 052d6e3)。main.pyのabsorption hunkはcommit済み。main.pyの052d6e3からの残差分はpersistent hunkのみ(import PersistentDepthWriter / _build_broker persistent param / lifespan persistent生成 / broker=_build_broker(config,persistent_writer) / persistent_writer.close)。よってmain.py全体addで足りる。
統括の承認: 統括はmain.py persistent差分を検証済み。env gate(PERSISTENT_DEPTH_HISTORY_ENABLED, default false)でADR-011の全量記録に沿う。PersistentDepthWriter本体はHEAD既存、PushBroker persistent_writer paramは第二コミット済みで依存充足。保護ファイルmain.pyのpersistent変更を承認する。

---

## 1. 絶対規律
- main.pyのみをaddせよ(残差分はpersistentのみ)。
- docker-compose.yml, time_sales.js を混入させるな。
- ソースを変更するな。

## 2. commit対象(この1パスのみ)
```
Delta_Engine_Pro4web/webapp/main.py
```

## 3. 手順

### S1. main.py 差分追加行 float走査
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/webapp/main.py | grep -nE "^\+" | grep "float("
```
0件を確認(1件でも停止・報告)。

### S2. add
```
git -C <root> add Delta_Engine_Pro4web/webapp/main.py
```

### S3. staged検証(commit前、必ず提出)
```
git -C <root> diff --cached --name-only
git -C <root> diff --cached -- Delta_Engine_Pro4web/webapp/main.py | grep -nE "on_absorption_state"
git -C <root> diff --cached -- Delta_Engine_Pro4web/webapp/main.py | grep -nE "PersistentDepthWriter|persistent_writer|persistent_enabled"
```
判定(外れたら`git reset`で解除・停止・報告):
- name-onlyが `Delta_Engine_Pro4web/webapp/main.py` の1行のみ。
- staged に `on_absorption_state` が **0件**(第三でcommit済みのため差分に現れないはず)。
- staged に persistent系が **1件以上**。

### S4. commit(メッセージ固定)
```
git -C <root> commit -m "feat(webapp): add optional persistent depth history writer

Env-gated (PERSISTENT_DEPTH_HISTORY_ENABLED, default false) writer wired
through PushBroker and closed on lifespan shutdown. No-op unless enabled;
follows ADR-011 full-capture principle."
```

### S5. commit後証跡
```
git -C <root> show --stat HEAD
git -C <root> rev-parse HEAD
git -C <root> status --porcelain
```
- 新HEAD SHA提出。
- main.py がstatusから消えること。残るソースM/??は docker-compose.yml(空行)と time_sales.js(DOM Trade Pulse)のみになること。

### S6. pytest
```
cd Delta_Engine_Pro4web && python -m pytest -q -p no:cacheprovider
```
サマリ・FAILED行提出。773 passed維持・既知failureのみ。

## 4. 提出物
- S1 float走査
- S3 name-only + on_absorption_state grep(0件)+ persistent grep(1件以上)
- S5 show --stat・新HEAD・status
- S6 pytestサマリ・FAILED行
- main.py のcommit後SHA-256

## 5. 禁止事項
- main.py以外のadd、ソース変更。
- S3判定を外れたままのcommit続行。
- commitメッセージ改変。

以上。正常完了後、統括が残処理(time_sales.jsのDOM Trade Pulse片翼是正=第五、docker-compose空行の破棄可否)の指示を発行する。これらの完了でリポジトリ衛生が整い、Phase 2-3 Stage 2実装へ進む。
