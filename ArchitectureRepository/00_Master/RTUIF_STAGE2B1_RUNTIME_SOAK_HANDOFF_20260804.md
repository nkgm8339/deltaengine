# DeltaEngine05M — RTUIF Stage 2B-1 Runtime Soak 引き継ぎ

作成日: 2026-08-04  
対象: `C:\Users\user\Desktop\DeltaEngine05M`

## 現在地

- Realtime UI Freshnessの根本対策はStage 2B-1。
- `LivePipeline` backlog drain loopにchunk公平性を実装済み。
- event数budget既定値: 32件。
- wall-time budget既定値: 50ms。
- event境界で`await asyncio.sleep(0)`し、heartbeat/canary等へ制御を返す。
- book構築・順序・ownership、storage、PushBroker、timeout値は変更していない。
- UI側のheartbeat grace修正は採用せず、`market_freshness.js`は開始SHAへ復元済み。

## 検証済み

- Stage 2B-1専用/configテスト: 56 passed。
- UI freshness/pipeline wiring回帰: 12 passed。
- `src/pipeline.py` SHA-256: `7591fef6cdeed2b1515add62bb4e9eda8ce8df904360cd5304df8a13c9893bae`
- `src/config.py` SHA-256: `df5b727850fa2be15f2ec85dfba0dba1f3b59feeaa485ff5cadd7fc187225a0d`
- `config/config.yaml` SHA-256: `3411cb14b55d228b3c856fe34572857f596f793cd675134535d15b89e7fa9fc0`
- `webapp/static/market_freshness.js` SHA-256: `65c94cf5f90f37b381b1877c9ed1c4f0e93d92540ff90238dbc5c44af3483a48`

## 未完了

runtime効果の600秒soakが未実施。したがって、実装・テストは完了しているが、runtime効果は未証明。

## 次セッションで実施すること

1. 上記source/config/protected SHA、正規Stage 2B-1 image、container状態を事前記録。
2. 正規imageを親にtemporary overlay計装を適用する。source本体は編集しない。
3. 600秒soakを実行し、以下を収集する。
   - canary lateness最大
   - server/browser生成間隔最大
   - backlog burst占有時間
   - queue/backlog推移
   - heartbeat状態
4. book gap=0、全SYNCED、`pipeline_alive`/`upstream_fresh`、Tape failure、message順序を確認。
5. 3000ms超の残存をbacklog型／単一event型に分類する。
6. 親imageへ復元し、SHA・ログ・計装点・manifestを提出する。

## 絶対条件

- ユーザーが明示的に「よし」と言うまでruntime実行を開始しない。
- 対象名は必ずDeltaEngine05Mと表記する。
- protected、UI freshness、timeout値、book ownershipは変更しない。
- `git add` / `commit` / `push`は禁止。
- soak結果がNGなら、勝手に次Stageへ進まず停止して報告する。
