# Flow → HFM execution prototype checkpoint

更新時刻: 2026-07-26 01:25 JST

## 重要 — 完成扱い撤回

このcheckpointで実装したものは、Flow Price Response単体の状態遷移からHFM注文requestを
作るexecution prototypeである。CVD、divergence、Footprint、Imbalance、Absorption、
Flow Event、Liquidation、8パターン、OI、native 5m/10m分析をENTRY根拠へ統合していない。

したがって「分析から自動発注まで完成」という過去報告を撤回する。

- 分析から自動発注までの完成品ではない
- ENTRYロジックとして採用禁止
- LIVE起動禁止
- `FLOW_STATE_TO_SIDE`をproduction GOとして使用禁止
- execution plumbing、JSONL audit、dashboardだけ再利用候補
- 統合ENTRY GOを実装するまで未完成

以下の変換、実装、試験結果はprototype作業の監査履歴であり、
現在のENTRY完成条件や相場上の有効性を表さない。

## prototype着手時の意図

- Flow Price Responseの初回状態遷移をHFM発注requestへ接続
- spread制限、SL/TP、決済、安全制約は後工程
- intent、MT5 check、ticket、約定価格を目視可能にする
- 完成済みFlow Price Responseと3段チャートは変更しない

この意図自体が、ユーザーの本来の目的である「オーダーフロー全体からENTRY根拠を作る」
より狭い問題へ勝手に置き換わっていた。

## 不採用となったFlow単体変換

| Flow state | HFM side |
|---|---|
| `BUY_EFFECTIVE` | `BUY` |
| `SELL_EFFECTIVE` | `SELL` |
| `BUY_TRAPPED` | `SELL` |
| `SELL_TRAPPED` | `BUY` |

prototypeの重複制御:

- 対象window初期値30秒
- 起動直後はbaselineで発注しない
- 同一状態継続では重複しない
- 別状態への遷移で再度intentを作る

この変換を統合ENTRY GOとして使用してはならない。

## 実装したexecution部品

- 既存WebSocket `FLOW_RESPONSE`受信
- 状態遷移検出
- MetaTrader5 Python API request生成
- observe / check / live mode
- append-only JSONL audit
- 独立dashboard
- retcode、order ticket、deal ticket、fill price表示

変更file:

- `Delta_Engine_Pro4web/src/execution/__init__.py`
- `Delta_Engine_Pro4web/src/execution/flow_hfm_executor.py`
- `Delta_Engine_Pro4web/tools/run_flow_hfm_autotrader.py`
- `Delta_Engine_Pro4web/tests/execution/test_flow_hfm_executor.py`
- `Delta_Engine_Pro4web/docs/FLOW_TO_HFM_AUTOTRADER_RUNBOOK_20260726.md`

上記fileは削除していないが、ENTRYロジックとして使用禁止。

## prototypeで確認済みの機械事実

HFM:

- server: `HFMarketsGlobal-Live8`
- symbol: `#BTCUSDr`
- minimum volume / step: `0.01 / 0.01`
- filling: FOK
- BUY 0.01 lot `order_check`: `retcode=0 / Done`
- SELL 0.01 lot `order_check`: `retcode=0 / Done`

実Flow check例:

- source time: `2026-07-26 01:06:48.563 JST`
- transition: `UNCLEAR -> BUY_EFFECTIVE`
- prototype mapped side: BUY
- Binance signal price: `64167.40`
- receive lag: `1398 ms`
- HFM Ask / request price: `64177.548`
- order check: `retcode=0 / Done`

この例が証明するのはrequest plumbingだけであり、オーダーフロー統合分析、ENTRY正確性、
production GOの有効性を証明しない。

試験:

- execution unit: 8 passed
- Flow/WebSocket境界込み: 55 passed
- 当時の全回帰: 472 passed

上記test件数をENTRY完成の根拠にしてはならない。

## 未完成の本来の仕事

- 現象別ENTRYトリガーの設計報告
- CVD、divergence、Footprint、Imbalance、Absorption、Flow Event、Liquidation、
  8パターン、OI、native 5m/10mの役割分類
- primary trigger / confirmation / veto / context / data qualityの分離
- armed / confirmed / GO / expiry / invalidation / duplicate / re-arm仕様
- 保存済み実データでの発生順序、時刻同期、欠測監査
- 統合ENTRY GOの実装
- zero-spreadでの分析方向・entry時点正確性評価
- Binance/HFM同時時刻比較
- 統合GOだけをHFM executionへ接続
- 根拠・反対根拠・欠測をdashboardとauditへ表示

## 本質的blocker

本質的blockerはMT5 algorithmic tradingではない。
オーダーフロー全体から説明可能なENTRYトリガーと統合GOが存在しないことが先である。
端末設定をONにしてはならない。

コード監査で確認済み:

- `SignalEngine.evaluate()`は固定WAIT / confidence 0 / NO_INPUT
- `AnalysisEngine.evaluate()`は固定NEUTRAL / confidence 0
- pipelineは独立指標を旧composite scoreへ渡していない
- 各分析器は計算・表示されるが、現象別ENTRY層は未実装

## 2026-07-26 01:24 JST 停止状態

- Flow単体check sidecar PID 21764を停止
- port 18081停止
- HFM position 0
- HFM pending order 0
- MT5 algorithmic trading OFF
- LIVE注文0件
- Docker分析WebAppとMT5 quote exporterには停止操作をしていない

## 次の再開位置

`ORDERFLOW_ENTRY_TRIGGER_DESIGN_HANDOFF_20260726.md`を全文読む。

次セッションは実装や大量試験から始めず、相場現象ごとのENTRYトリガーを何種類へ分けるべきか、
各triggerの主発火条件、confirmation、反対根拠、hard reject、時刻、expiry、duplicate、
re-armを設計してユーザーへ詳細報告する。

Flow単体sidecarを再起動しない。LIVE注文を送らない。
