# 作業引継ぎ — 2026-07-19

## 運用ルール

- 実装・設定変更は、ユーザーが明確に `GO` と言った後だけ行う。
- 機能単位でテストし、Gitコミットする。
- 問題時は `git revert <commit>` で対象コミットだけ戻す。

## 完了済み（コミット済み）

| Commit | 内容 |
| --- | --- |
| `fc18b56` | 作業開始前のベースライン |
| `33653d9` | 1分足を維持した5分・15分足の内部同時集計 |
| `963e771` | 確定15分足のEMA20/EMA50による `WARMUP` / `UP` / `DOWN` / `RANGE` 判定 |
| `f2c69fe` | 順張りフィルター。UPはBUYのみ、DOWNはSELLのみ、RANGE/WARMUPはWAIT |
| `eb48d28` | 1分確定足の価格/CVD通常ダイバージェンス検出器 |

## 未完了（未コミット）

ダイバージェンスを画面へ送る接続を途中まで追加している。以下の3ファイルが変更中。

- `src/pipeline.py`
  - 1分確定足ごとに `CvdDivergenceDetector` を更新し、最新結果を `pipeline.divergence` に保持する変更。
- `webapp/main.py`
  - `pipeline.divergence` を `PushBroker.on_analysis()` へ渡す変更。
- `webapp/push_broker.py`
  - `ANALYSIS` ペイロードに `divergence: "BULLISH" | "BEARISH" | null` を含める変更。

現時点では **UI表示は未実装**。アプリ画面にはダイバージェンス文言は出ない。

## 再開時の推奨手順

1. 未コミットの3ファイルを確認し、`python -m py_compile src/pipeline.py webapp/main.py webapp/push_broker.py` と関連テストを実行する。
2. `webapp/static/index.html` の「SIGNAL — WHY」欄に `DIVERGENCE: BULLISH / BEARISH` を表示する欄を追加する。
3. UIで表示されることを確認し、未コミット分を独立コミットする。
4. ダイバージェンスをシグナルの加点／警戒に使うかは、ユーザーと仕様を決めてから別段階で実装する。

