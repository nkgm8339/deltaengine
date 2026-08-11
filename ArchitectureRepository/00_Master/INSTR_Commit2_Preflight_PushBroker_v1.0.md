# 指示書: 第二コミット着手前 push_broker.py 差分材料
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第一コミット完了(HEAD 6c5a8b25)。保護ファイル精査で、保護4ファイルのM変更に「HEAD不整合是正(book_stream_id/book_sequence)」「Absorption realtime」「Persistent depth writer」が混在と判明。第二コミットをHEAD不整合是正に純化するため、push_broker.pyの全差分とhunk内訳を要する。
段階: 材料収集。commit・add・変更を一切実行しない。

---

## 1. 絶対規律
- commit / git add / checkout / restore / stash / 変更を実行するな。読み取りとdiff出力のみ。
- 全回答に ファイル:行番号 を併記。判定を書くな。事実のみ。
- diffの要約・省略を禁ずる。生出力を全文提出。

## 2. 収集タスク

### T1. push_broker.py 全差分
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/webapp/push_broker.py
```
全文を無編集で提出せよ。

### T2. hunk単位の機能分類材料
push_broker.py の各hunk(`@@ ... @@`区切り)について、以下を機械的事実として列挙せよ(判定・是非は書くな)。
- hunk見出し行(`@@ -a,b +c,d @@`)と先頭コンテキスト行
- そのhunk内に `book_stream_id` または `book_sequence` の文字列が出現するか(○/×)
- そのhunk内に `absorption`(大小問わず)の文字列が出現するか(○/×)
- そのhunk内に上記いずれも出現しない場合は「その他」と記し、該当シンボル名を ファイル:行番号 で1つ挙げよ

### T3. on_absorption_state の所在
- `on_absorption_state` メソッドが push_broker.py に存在するか。存在するなら、それがHEAD既存か未commit差分で追加されたかを、`git -C <root> show HEAD:Delta_Engine_Pro4web/webapp/push_broker.py` へのgrepと作業ツリーへのgrepの両方の ファイル:行番号 で示せ。
```
git -C <root> show HEAD:Delta_Engine_Pro4web/webapp/push_broker.py | grep -n "def on_absorption_state" 
grep -n "def on_absorption_state" Delta_Engine_Pro4web/webapp/push_broker.py
```

### T4. book識別子生成箇所
- `book_stream_id` と `book_sequence` を生成・付与するコードが push_broker.py のどのメソッド内か、作業ツリーの ファイル:行番号 で示せ。
- それがHEADに存在するか(`git show HEAD:...` grep)を示せ。

## 3. 提出物
- T1 全差分生出力
- T2 hunk分類表(book識別子○×、absorption○×、その他シンボル行番号)
- T3 on_absorption_state のHEAD/作業ツリー両grep結果
- T4 book識別子生成箇所のHEAD/作業ツリー両grep結果
- 末尾: `git rev-parse HEAD`(6c5a8b25...), `git status --porcelain`(状態不変), `git diff --cached --name-only`(空)

## 4. 禁止事項
- commit / add / 変更 / 部分ステージの実行。
- 判定・GO/NO-GO・是非の記載。
- diffの省略。

以上。提出後、統括がpush_broker.pyのhunk分離可否を判定し、第二コミット実行指示書(push_broker該当hunk + test_book_update.py)を発行する。
