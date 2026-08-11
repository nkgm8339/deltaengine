# 指示書: 第三コミット time_sales.js帰属確定 材料
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M
前提: 第二コミット完了(HEAD 3be272c)。pipeline.pyはabsorption純粋と確定(全hunk absorption、float0、window_secはHEAD既存)。time_sales.jsのonAcceptedTradesフックはabsorption/book/tape文字列を含まず帰属不明瞭。第三コミット(absorption)に含めるか独立させるかを、テスト依存とフック消費先で確定する。
段階: 材料収集。commit・add・変更を一切実行しない。読み取りのみ。

---

## 1. 絶対規律
- commit / git add / checkout / restore / stash / 変更を実行するな。読み取り(cat/grep)のみ。
- 全回答に ファイル:行番号 を併記。判定を書くな。事実のみ。

## 2. 収集タスク

### T1. test_absorption_realtime_display.py 全内容
未追跡ファイルの全文を提出せよ(読み取りのみ、変更するな)。
```
cat Delta_Engine_Pro4web/tests/webapp/test_absorption_realtime_display.py
```

### T2. テストの依存対象
上記テストファイルについて:
- import文・読み込み対象ファイル(HTML_PATH等でファイルを読む場合はそのパス)を ファイル:行番号 で列挙せよ。
- テスト内に `onAcceptedTrades`、`time_sales`、`ABSORPTION_STATE`、`onAbsorptionState` の文字列が出現するか、各々 ○/× と出現行を示せ。

### T3. onAcceptedTrades の消費先(全ソースgrep)
```
grep -rn "onAcceptedTrades" Delta_Engine_Pro4web/webapp/ Delta_Engine_Pro4web/tests/
```
- `config.onAcceptedTrades` を渡している箇所(プロデューサ)を ファイル:行番号 で特定せよ。渡す箇所が無ければ「未接続」と明記せよ。

### T4. pipeline on_accepted_trade 呼出実体
```
grep -n "on_accepted_trade" Delta_Engine_Pro4web/src/pipeline.py
git -C <root> show HEAD:Delta_Engine_Pro4web/src/pipeline.py | grep -n "on_accepted_trade"
```
- pipeline内で `on_accepted_trade` を呼ぶ(発火する)行を ファイル:行番号 で示せ。HEAD既存か作業ツリー追加かを両grepで示せ。

## 3. 提出物
- T1 テスト全文
- T2 依存対象と文字列走査(行番号付き)
- T3 onAcceptedTrades消費先(プロデューサ特定 or 未接続)
- T4 on_accepted_trade呼出実体とHEAD/作業ツリー差
- 末尾: `git rev-parse HEAD`(3be272c), `git status --porcelain`, `git diff --cached --name-only`(空)

## 4. 禁止事項
- commit / add / 変更。
- 判定・GO/NO-GO・是非の記載。

以上。提出後、統括がtime_sales.jsの第三コミット包含可否を確定し、第三コミット実行指示書を発行する。
