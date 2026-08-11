# 指示書: Phase 2-3 Stage 2 Task 2 アンカー確定材料
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3 Stage 2
前提: 起動モデル承認済み(bookチャネル排他: HEATMAP_REPLAY_ENABLED時はframe_source供給task、elseは既存live pump。gate有効化)。実装はframe_source供給ループを新規モジュール webapp/heatmap_replay_task.py に閉じ込め、main.py接触を最小差分に絞る。アンカー文字列ベース差分のため、該当領域の実テキストを取得する。
段階: 材料収集。変更・実装・新規ソース生成を行わない。読み取りのみ。

---

## 規律
- 変更するな。読み取り(sed/grep)のみ。全回答は実テキストを無編集で提出(要約・整形禁止)。行番号を付けて提出せよ。

## 収集タスク(main.py の実テキストを行番号付きで提出)

### A1. import領域
```
sed -n '30,56p' Delta_Engine_Pro4web/webapp/main.py
```

### A2. lifespan設定領域(recording/persistent writer/depth history解決の周辺)
```
sed -n '118,140p' Delta_Engine_Pro4web/webapp/main.py
```

### A3. live pump構築とbook_projection_pump定義
```
sed -n '228,240p' Delta_Engine_Pro4web/webapp/main.py
```

### A4. replay/live task分岐(book_projection_task=None と live task起動)
```
sed -n '368,392p' Delta_Engine_Pro4web/webapp/main.py
```

### A5. task登録とshutdown
```
sed -n '566,600p' Delta_Engine_Pro4web/webapp/main.py
```

### A6. LatestBookProjectionPump のインターフェース(run/register/send callback契約)
```
sed -n '220,300p' Delta_Engine_Pro4web/webapp/book_projection.py
```

### A7. hfm_quote_tail_loop の駆動パターン(参照実装、非同期forとawait dispatchとsleep)
```
sed -n '60,136p' Delta_Engine_Pro4web/webapp/hfm_quote_tailer.py
```

### A8. broker.on_book_update のシグネチャ(await対象)
```
sed -n '250,300p' Delta_Engine_Pro4web/webapp/push_broker.py
```

### A9. index.html gate定義行の実テキスト(前後含む)
```
sed -n '965,972p' Delta_Engine_Pro4web/webapp/static/index.html
```

### A10. config env読み取りの既存パターン(os.getenv でflag/root/int を読む箇所)
```
grep -n "os.getenv" Delta_Engine_Pro4web/webapp/main.py
```

## 提出物
- A1-A10 の実テキスト(行番号付き、無編集)
- 参照ファイルのHEAD SHA-256(main.py, book_projection.py, hfm_quote_tailer.py, push_broker.py, index.html)
- `git rev-parse HEAD`(2fea7ef), `git status --porcelain -- Delta_Engine_Pro4web/`, `git diff --cached --name-only`(空)

## 禁止事項
- 実装・変更・新規ソース生成。判定・GO/NO-GO記載。テキストの要約・省略。

以上。提出後、統括がheatmap_replay_task.py(新規)の完全実装仕様と、main.py/index.htmlのアンカー文字列ベースbefore/after差分を確定し、Task 2実装指示書を発行する。
