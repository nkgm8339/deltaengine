# 指示書: 第三コミット着手前 pipeline.py / time_sales.js 差分材料
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第二コミット完了(HEAD 3be272c、book識別子契約が整合)。第三コミット(Absorption realtime)の範囲確定に、main.pyの`pipeline.on_absorption_state=cb`を発火するpipeline.py側受け口と、time_sales.jsの機能帰属を要する。
段階: 材料収集。commit・add・変更を一切実行しない。読み取りとdiff/grepのみ。

---

## 1. 絶対規律
- commit / git add / checkout / restore / stash / 変更を実行するな。
- 全回答に ファイル:行番号 を併記。判定を書くな。事実のみ。diffの省略禁止。

## 2. 収集タスク

### T1. pipeline.py 全差分
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/src/pipeline.py
```
全文を無編集で提出せよ。

### T2. pipeline.py hunk分類
各hunk(`@@ ... @@`)について機械的事実を列挙(是非を書くな):
- hunk見出しと先頭コンテキスト行
- hunk内に `absorption`(大小問わず)が出現するか ○/×
- hunk内に `on_absorption_state` が出現するか ○/×
- 上記いずれも無い場合「その他」とし、該当シンボルを ファイル:行番号 で1つ挙げよ

### T3. absorption受け口の所在
- pipeline側で `on_absorption_state` コールバックを呼ぶ/保持するコードを、作業ツリーとHEADの両方でgrepし ファイル:行番号 を示せ。
```
git -C <root> show HEAD:Delta_Engine_Pro4web/src/pipeline.py | grep -n "on_absorption_state"
grep -n "on_absorption_state" Delta_Engine_Pro4web/src/pipeline.py
```
- `absorption_window_sec`(main.pyが参照)がpipelineに存在するか、作業ツリー/HEAD両grepで示せ。
```
git -C <root> show HEAD:Delta_Engine_Pro4web/src/pipeline.py | grep -n "absorption_window_sec"
grep -n "absorption_window_sec" Delta_Engine_Pro4web/src/pipeline.py
```

### T4. pipeline.py 差分追加行のfloat走査
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/src/pipeline.py | grep -nE "^\+" | grep "float("
```
ヒット行を全て提出(0件ならその旨)。既存行のfloatは対象外。

### T5. time_sales.js 全差分と機能帰属
```
git -C <root> diff HEAD -- Delta_Engine_Pro4web/webapp/static/time_sales.js
```
全文提出。加えて差分追加行に対する文字列走査結果を示せ:
- `absorption` 出現 ○/×
- `book_stream_id`|`book_sequence` 出現 ○/×
- `tape`|`TAPE` 出現 ○/×
- 上記いずれも無い主要シンボルがあれば ファイル:行番号 で挙げよ

## 3. 提出物
- T1 pipeline.py全差分
- T2 hunk分類表
- T3 on_absorption_state / absorption_window_sec のHEAD・作業ツリー両grep
- T4 pipeline float走査
- T5 time_sales.js全差分と機能帰属走査
- 末尾: `git rev-parse HEAD`(3be272c), `git status --porcelain`, `git diff --cached --name-only`(空)

## 4. 禁止事項
- commit / add / 変更 / 部分ステージ。
- 判定・GO/NO-GO・是非の記載。
- diffの省略。

以上。提出後、統括が第三コミット(Absorption realtime)の対象ファイルとmain.py hunk分割方針を確定し、実行指示書を発行する。
