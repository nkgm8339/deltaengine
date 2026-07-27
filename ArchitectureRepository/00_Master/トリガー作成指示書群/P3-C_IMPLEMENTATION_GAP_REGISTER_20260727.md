# P3-c 実装ギャップ一覧

作成日: 2026-07-27 JST  
分類方針: 以下は現時点では「バグ」と断定しない。P1/P2で未実装、またはG16正本の定義統一待ちの構造ギャップとして記録する。

## 1. 問題一覧

| ID | モジュール | 該当行 | 問題 | 分類 | 影響 |
|---|---|---:|---|---|---|
| A | `snapshot_producer.py` | 214-219 | `_price_samples()`が各windowの最新値を返すだけで、価格履歴系列を返さない | 未実装 | 5分price response、price/OI joint、G16 price-response系を履歴で評価できない |
| B1 | `snapshot_producer.py` | 144-152 | `trade_delta_*`がCVD由来とFlowResponse由来で同一dictへ二重書き込みされる | 構造整理未実施 | 後段の値の由来が一意でなく、window/定義統一時に上書き関係を再確認する必要がある |
| B2 | `condition_adapter.py` | 41, 119 | `_add_pre_aggregated()`が既存keyを無言で上書きする | 契約未定義 | 同名keyの優先順位・衝突検出が未定義。G16正本の材料由来を追跡しにくい |
| C | `market_state.py` 47-48 / `snapshot_producer.py` 268 | 時刻系がmonotonic表記とUTC epoch変換の二重系になっている | 契約統一待ち | 過去/未来filter、Replay/Live一致性、expiry時刻の基準を確定できない。pipeline.pyの供給実装確認が必要 |
| D | `snapshot_producer.py` | 39, 98, 105 | book履歴・時刻・reset契約がない | 未実装 | wall差分、freshness、depth gap後の復帰判定を生成できない |
| E | `condition_adapter.py` | 80, 87 | `distance_to_nearest_*_wall`という名前だが、実際にはtop10内の最大数量levelまでの距離を計算している | 定義不一致候補 | key名と実測値の意味が一致しない可能性。G06正本の語義を確定するまで読み替え禁止 |

## 2. 取得可否

### 取得できる構造

- `FlowResponseSnapshot`の`price_change`/`price_change_bps`/`last_price`/`event_time`/`window_sec`: `src/orderflow/flow_price_response.py:40-61`
- 現在のbook levels: `src/orderflow/orderbook.py:69-81,148-157`
- `MarketStateSnapshot.oi_samples`フィールド: `src/strategy_engine/ingestion/market_state.py:67-68`
- point-in-time wall concentration/distance計算: `src/strategy_engine/ingestion/condition_adapter.py:65-87`

### 今は取れない・未実装

- price履歴としての系列化（A）
- wall履歴・比較window・reset・freshness（D）
- OI sampleをpipelineから`MarketStateSnapshot`へ供給する経路
- G16 compositeのAND/OR式、side解決、threshold/window

## 3. pipeline.py依存

Cの時刻系は、producer単体では確定できない。以下を`pipeline.py`で実測する必要がある。

- Replayのengine_time_ns供給元
- Liveのengine_time_ns供給元
- bar_time/source time/receive timeの使い分け
- `MarketStateSnapshot`とstrategy eventの時刻単位が同一か
- out-of-order・depth gap・再同期時のreset

根拠となる現行pipelineのsnapshot生成箇所は`Delta_Engine_Pro4web/src/pipeline.py:551-608,1300-1468`。

## 4. G16正本待ちの項目

以下はC側のG16正本追記なしに実装を開始しない。

- price responseのTier A key名・単位・window・符号
- wall差分のkey名・baseline・window・reset/freshness
- passive defense / breakout / progressの論理式
- OI stale/freshness契約
- composite FLAGのthreshold供給元（CalibrationBook）

## 5. 判定

この一覧のA〜Eは、現時点では「壊れたコード」ではなく、P1/P2の範囲で残った実装ギャップまたは定義統一待ちである。

Cのみpipeline.pyの時刻供給を確認しないと、構造評価を完了できない。G16正本が確定した後、A〜Eを個別の実装タスクと回帰テストへ分解する。

commit/push: 未実施

## 契約決定追記（2026-07-27）

C（時刻二重化）は未定義のまま放置せず、engine_time_ns=monotonic、source_time_ns=UTC epochの二時計契約をENGINE_TIME_SOURCE_TIME_CONTRACT_V0_1_20260727.mdへ固定した。A/D/EはG16正本の材料定義が必要なため未実装継続。B1は既存値をsetdefaultで保護し、B2はpre_aggregatedが既存adapter出力を上書きしないsetdefaultへ変更した。

## 解決追記（2026-07-27 20:46:47 JST）

お館様の「ひとつひとつ解決しろ」という明示指示により、A、D、Eを順次契約化・実装した。

| ID | 解決内容 | 正本契約 |
|---|---|---|
| A | normalized tradeのsource-time価格履歴、G09 100ms／1s／5s／30s progress ticks、300秒OI joint履歴、event時刻評価境界 | `PRICE_RESPONSE_HISTORY_CONTRACT_V0_1_20260727.md` |
| D | applied depth diffからG07全48 key、gap／snapshot／resync reset、window完成までomit、future除外 | `BOOK_EVENT_HISTORY_RESET_CONTRACT_V0_1_20260727.md` |
| E | top10最大数量wall candidate、同量nearest tie-break、ticks、空／交差／off-grid fail-closed | `WALL_DISTANCE_SEMANTICS_CONTRACT_V0_1_20260727.md` |

A/D/Eの個別blockerは解消した。G16 composite、CalibrationBook threshold、runtime有効化、
発注権限は別工程であり、本解決による承認ではない。全回帰は **590 passed, 1 skipped**。

