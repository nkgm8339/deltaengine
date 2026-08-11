# 指示書: Phase 2-3 Stage 2 Task 3 — コミット

- バージョン: v1.0
- 作成: 2026-08-01
- 発行元: Claude(web / 統括)
- 宛先: Codex(実装担当)
- リポジトリ: DeltaEngine05M(`C:\Users\user\Desktop\DeltaEngine05M`)
- ブランチ: feature/footprint-dom-tape
- 基準HEAD: `6ae3f15`

---

## 前提

Task 3 Stage 2 実装の統括検証が V1-V10 全項目 PASS で合格した。本指示書でコミットを実施する。

---

## 手順

### Step 1: staging 確認

```
cd C:\Users\user\Desktop\DeltaEngine05M
git diff --cached --name-only
```

出力が空であること(staging が空)を確認してから次へ進む。空でなければ停止し報告。

### Step 2: git add(2ファイルのみ)

```
git add Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
git add Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_budget.py
```

**注意:** ArchitectureRepository 配下の既存差分4件は Task 3 のスコープ外のため add しない。

### Step 3: staging 検証

```
git diff --cached --name-only
```

出力が以下の2行**のみ**であること:

```
Delta_Engine_Pro4web/tests/webapp/test_heatmap_frame_budget.py
Delta_Engine_Pro4web/webapp/static/orderbook_heatmap.js
```

3行以上あれば停止し報告。

### Step 4: commit

```
git commit -m "task3: add 16ms frame-budget pass/fail indicator to heatmap status"
```

### Step 5: 報告

以下を提出すること:

1. `git log --oneline -3` の出力
2. `git diff --cached --name-only` の出力(空であること)
3. `git status --porcelain` の出力
4. `git show --stat HEAD` の出力

---

## 禁止事項

- `git push` は実行しない。
- ArchitectureRepository 配下のファイルを staging に追加しない。
- commit message を変更しない。

以上。
