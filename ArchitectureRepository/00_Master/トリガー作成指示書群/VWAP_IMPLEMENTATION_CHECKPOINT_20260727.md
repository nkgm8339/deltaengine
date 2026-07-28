# VWAP実装checkpoint

最終更新: 2026-07-28 02:27:15 JST
状態: 完了

## 承認範囲

ユーザーの明示指示「VWAP実装しろ」に基づき、Strategy Engineへ実約定ベースの
Session VWAP材料を実装する。

- 計算式は `Σ(price × quantity) / Σ(quantity)`。
- Binance BTCUSDTの現行UTC時刻契約に合わせ、session開始はUTC 00:00とする。
- `CD-G03-037`〜`CD-G03-040`のSession VWAP／Session Open AVWAP距離・位置関係を
  source-timeで生成する。
- 再起動時は既存DuckDBから当日分の累積値をread-only復元する。
- session開始部分が収録されていない場合はSession VWAPを部分標本で偽装せずomitする。
- threshold較正、HookEvent解禁、Strategy runtime有効化、発注権限は変更しない。
- 完成済みFlow Price Response、3段チャート、8パターン、OI、UIは変更しない。

## 既存作業の保全

着手時点で次のユーザー既存差分がある。今回の作業で消さない。

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
  - `_PRICE_HISTORY_NS`を600秒へ延長した未コミット差分
- `Delta_Engine_Pro4web/webapp/static/index.html`
  - git上はmodified表示だが内容差分なし
- `ArchitectureRepository/00_Master/トリガー作成指示書群/`配下の未追跡文書3件

## 完了済み

- `PROJECT_MEMORY.md`全文確認。
- VWAP正本、Condition Dictionary、既存G07/G08、SnapshotProducer、Adapter、
  Live／Replay配線を調査。
- 既存G07/G08はclosed candleのtypical price近似であり、Strategy Engineの
  `CD-G03-037`〜`040`は未生産と確認。
- 変更前の対象試験は30件合格。
- 実約定`Σ(price × quantity) / Σ(quantity)`のDecimal累積器を追加。
- UTC 00:00日次reset、session冒頭coverage、source-time、future-data、
  seed境界duplicateをfail closedで実装。
- Session VWAPとUTC session open AVWAPをMarketStateへ独立名で載せ、現anchor契約では
  同じ値を供給。
- signed distanceを`(current price - VWAP) / tick_size`、relationを
  `BELOW=-1 / AT=0 / ABOVE=1`として`CD-G03-037`〜`040`を生産。
- DuckDB read-only loaderをUTC session境界固定で追加し、Live起動前にaggregate seedを復元。
- 新規契約9件、Live再起動統合1件、既存関連を含む46件が合格。
- 全体回帰は `600 passed, 1 skipped`。

## 未完了

- 全体回帰。
- `PROJECT_MEMORY.md`への完成記録追記。
- 最終diff、既存差分保全、発注権限不変の確認。

## 変更file

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/session_vwap.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`
- `Delta_Engine_Pro4web/src/database/session_vwap_warm_start.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/tests/strategy_engine/test_session_vwap.py`
- `Delta_Engine_Pro4web/tests/database/test_session_vwap_warm_start.py`
- `Delta_Engine_Pro4web/tests/test_session_vwap_live.py`
- 本checkpoint

## 検証結果

変更前:

```text
30 passed
2 setup errors
```

2件のsetup errorはコード失敗ではなく、既定pytest一時directory
`C:\Users\user\AppData\Local\Temp\pytest-of-user`へのアクセス拒否。
以後はworkspace内の明示`--basetemp`で再実行する。

変更後:

```text
python -m py_compile ...: passed
新規VWAP契約: 9 passed
Live再起動統合: 1 passed
既存関連を含む対象回帰: 46 passed
全体回帰: 600 passed, 1 skipped in 95.85s
```

workspace内basetempもsandbox内processではアクセス拒否となったため、同じpytest commandを
承認済みsandbox外実行へ切り替え、上記結果を確認した。

## blockerの限定範囲

sandbox内pytest一時directoryの権限制約はあるが、承認済みsandbox外実行で全試験合格。source上のblockerなし。

## 次の再開位置

完了。次回はこのcheckpointとPROJECT_MEMORYを正本として再開する。

## 2026-07-28 UI VWAP overlay（明示依頼）
- 状態: 完了
- 実施: 3段チャートの価格ペインへ、セッションVWAPを橙色の破線で描画。CANDLE/BAR_UPDATE payload と履歴APIに `vwap` フィールドを追加し、既存ローソク足・CVD・出来高の配置と計算は維持。
- 検証: webapp回帰 36 passed、Python compile passed。
- 制限: 履歴DBの既存candles行にはVWAP列がないため、履歴再読込分は値なし（ライブCANDLE/BAR_UPDATEから表示）。
- 再開位置: 完了。履歴VWAPを過去セッションまで描画する場合は、取引テーブルからのas-of集計APIを別変更として設計する。

## 2026-07-28 表示不具合修正
- 原因: セッション開始直後の取引が00:00±1秒を満たさない場合、戦略用VWAPはfail-closedでNoneとなり、UIにも値が渡らなかった。
- 対応: 戦略判定のfail-closed契約は維持しつつ、表示専用の`current_value`を追加。WebAppは確定VWAPを`EXACT`、coverage不足の表示用累積を`PARTIAL`として配信する。
- 表示: `PARTIAL`は価格labelへ`~`を付け、Strategy conditionへ使用しない。
- 検証: Phase 0A対象回帰72 passed、全体606 passed, 1 skipped。

## 2026-07-28 履歴チャート方針の監査訂正
- 画像確認で履歴バーのVWAPが空になることを確認。
- 以前のcheckpointにあった「OHLCVのセッション累積推定で補完」は現物に存在せず、実約定VWAPと同一でもないため採用しない。
- 履歴APIは`vwap=null`／`vwap_status=null`を返し、ライブの実約定累積だけを表示する。
- CANDLE／BAR_UPDATEは`vwap_status=EXACT/PARTIAL`を同梱し、橙色破線で描画する。
- server／browserの一時debug traceは除去済み。

## 2026-07-28 Phase 0A baseline remediation

- 状態: 完了、Phase 0B commit／branchは未承認・未実施。
- WebSocketPayload正本をv1.1 additive extensionへ更新。
- Session VWAP関連／WebApp対象回帰: 72 passed。
- 全体回帰: 606 passed, 1 skipped in 116.81s。
- JavaScript構文: inline script 1件合格。
- 完成済みFlow Price Response、3段チャート構造、8パターン、OI計算、発注権限は変更していない。
