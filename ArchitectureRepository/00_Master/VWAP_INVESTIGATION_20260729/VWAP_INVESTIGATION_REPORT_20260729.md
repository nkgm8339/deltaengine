# VWAP関連コード調査報告

調査日: 2026-07-29 JST
範囲: Git履歴、現行ソース、ArchitectureRepository内仕様・checkpoint・設計資料、VWAP関連テスト
制約: 調査のみ。コード修正、commit、checkout、reset、patchは実施していない。

## 1. VWAP関連ファイル

### 計算・状態

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/session_vwap.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`
- `Delta_Engine_Pro4web/src/database/session_vwap_warm_start.py`

### WebApp配信・履歴・表示

- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`

### テスト

- `Delta_Engine_Pro4web/tests/strategy_engine/test_session_vwap.py`
- `Delta_Engine_Pro4web/tests/test_session_vwap_live.py`
- `Delta_Engine_Pro4web/tests/database/test_session_vwap_warm_start.py`
- `Delta_Engine_Pro4web/tests/webapp/test_bar_update.py`
- `Delta_Engine_Pro4web/tests/webapp/test_history.py`

### 仕様・資料

- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`
- `ArchitectureRepository/40_Reference/VWAPReference_v3.0.md`
- `ArchitectureRepository/40_Reference/IndicatorDefinitions_v3.md`
- `ArchitectureRepository/40_Reference/TradingSessionsReference_v3.0.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/VWAP_IMPLEMENTATION_CHECKPOINT_20260727.md`

## 2. Git履歴（最終コミット）

Git authorは以下の対象で `unknown <ksckk0126@gmailcom>`。

| 対象 | commit | 日時 | message |
|---|---|---|---|
| `session_vwap.py`, `market_state.py`, `session_vwap_warm_start.py`、Strategyテスト | `715e9cb5323e8569b9023af3bd8414e80d213d4b` | 2026-07-28 17:01:27 JST | `feat(strategy): add exact UTC session VWAP with warm start` |
| `snapshot_producer.py`, `main.py`, `push_broker.py`, `history.py`, `index.html`, `footprint_canvas.js` | `1134886430b7c48487cd4a9389a202acfa6ff53e` | 2026-07-29 05:48:30 JST | `snapshot: preserve Footprint DOM Tape baseline before heatmap` |
| `tests/webapp/test_bar_update.py`, `tests/webapp/test_history.py` | `849a7a30744e5741c4e89e7a7dc9cd1a7376866d` | 2026-07-28 17:02:03 JST | `feat(webapp): overlay qualified session VWAP on price pane` |

## 3. コミット別diff要約

### 715e9cb

追加・修正: SessionVwapAccumulator、UTCセッションリセット、seed、value_at、SnapshotProducer/MarketState統合、DuckDB warm start、Strategy条件、テスト。

分類: 計算機能の新規追加（C）。既存の計算式を変更した差分ではなく、VWAP機能自体の追加。

### 849a7a3

追加・修正: `main.py`の`_chart_session_vwap()`、`push_broker.py`の`vwap`/`vwap_status`、履歴列、WebSocket仕様、価格ペインのVWAP線・ラベル・凡例、WebAppテスト。

分類: 配信変更（B）＋表示変更（A）。計算式を直接書き換えた差分は確認できない。履歴APIは`NULL AS vwap, NULL AS vwap_status`。

表示色: `index.html`の価格ペインは`WARN`、`footprint_canvas.js`は`CYAN`。

### 1134886

Footprint/DOM/Tapeの大規模snapshot。対象ファイルの最終コミットになっているが、VWAP計算式を変更した差分は確認できない。

分類: VWAP観点では周辺表示変更（A）。

## 4. 計算式調査

現行コードの式は次のとおり。

```text
VWAP = Σ(price × quantity) / Σ(quantity)
```

`session_vwap.py`の実装:

```python
self._notional += price * quantity
self._volume += quantity
return self._notional / self._volume
```

- 累積Volume: `_volume += quantity`
- 累積Price×Volume: `_notional += price * quantity`
- セッションリセット: UTC日付が変わった場合
- seed: `SessionVwapSeed`からnotional、volume、trade_count等を復元
- warm start: DuckDBの`sum(price * quantity)`、`sum(quantity)`を利用
- `value_at()`: セッション境界coverage、時刻、volumeを検証し、不成立時は`None`
- 丸め: 計算内部に丸め処理なし。`Decimal`で計算しpayloadで文字列化

### 結論

**既存のVWAP計算式を別の式へ変更した証拠はない。**

ただし、`715e9cb`でVWAP計算機能そのものが新規追加されているため、過去に承認された別実装との同一性まではGitだけでは証明できない。

## 5. 要求との整合性

`VWAP_IMPLEMENTATION_CHECKPOINT_20260727.md`には、

- 「ユーザーの明示指示『VWAP実装しろ』」
- UI overlayは「明示依頼」

と記載されている。

しかし、この記録はリポジトリ内文書であり、ユーザー本人の原指示そのものをGitだけから独立確認することはできない。

結論: **要求元不明**（リポジトリ文書には明示依頼との記載あり）。

## 6. 危険度

| 変更 | 分類 |
|---|---|
| SessionVwapAccumulator新規追加 | C |
| warm start追加 | C |
| MarketState/Strategy統合 | C |
| CANDLE/BAR_UPDATEへのVWAP追加 | B |
| 履歴APIへのVWAP列追加 | B |
| 価格チャート線・ラベル | A |
| VWAP色をWARNへ設定 | A |
| 計算式変更 | 該当証拠なし |

## 7. 最終結論

【変更箇所】

`715e9cb`で計算・warm start・Strategy統合、`849a7a3`でWebApp配信・履歴・価格ペイン表示、`1134886`で周辺UI snapshot。

【変更理由】

コミットメッセージ上はSession VWAP追加と価格ペインoverlay。色を`WARN`へ変更した具体的理由は記録なし。

【要求元】

リポジトリcheckpointは明示依頼と記載するが、独立した原指示の証拠はなく、厳密には要求元不明。

【証拠】

上記3コミット、現行ソース、WebSocket仕様、VWAP checkpoint、VWAP関連テスト。

【計算式変更の有無】

**計算式変更なし。** 現行式は`Σ(price×quantity)/Σ(quantity)`。ただし計算機能自体は`715e9cb`で追加された。

【仕様違反の可能性】

要求元をGit上で確認できないため無断変更の可能性は否定できない。色は資料間で不一致（橙色破線、シアン、現行WARN）があるため表示仕様不一致の可能性がある。

【私（Codex）の判断で変更した可能性】

Git authorは`unknown <ksckk0126@gmailcom>`で、Codexによる変更とは特定できない。今回の調査中にVWAPコードは変更していない。
