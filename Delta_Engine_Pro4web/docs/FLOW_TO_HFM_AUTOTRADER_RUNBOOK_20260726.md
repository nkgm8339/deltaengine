# Flow → HFM execution prototype（不採用・LIVE禁止）

> **現在の運用境界（2026-07-26）**
> このsidecarは統合Order Flow ENTRY GOではないため、ENTRYロジックとして不採用である。
> LIVE起動は禁止し、稼働中process、port 18081、HFM position、pending orderはすべて0、
> MT5 algorithmic tradingはOFFの状態を維持する。以下はprototypeの監査記録であり、
> production起動手順ではない。

完成済み Flow Price Response と3段チャートは変更せず、既存WebSocketの
`FLOW_RESPONSE`をHFM MT5注文へ接続する独立プロセスである。

## 変換

| Flow state | HFM side |
|---|---|
| `BUY_EFFECTIVE` | BUY |
| `SELL_EFFECTIVE` | SELL |
| `BUY_TRAPPED` | SELL |
| `SELL_TRAPPED` | BUY |

起動直後の状態はbaselineとして保存するだけで発注しない。以後、指定windowの状態が変化し、
新状態が上表のいずれかになった最初の更新でだけ注文intentを作る。同じ状態の継続更新では
重複発注しない。

## 保存している機械的確認経路

先に通常のDeltaEngine WebAppを起動し、`http://127.0.0.1:18080`で3段チャートが
動いていることを確認する。

`observe`と`check`は機械的経路の再検証用にだけ残す。現在の通常運用ではsidecarを起動しない。
隔離試験が明示承認された場合に限り、`check`は次の形で`order_check`まで確認できる。

```powershell
python -m tools.run_flow_hfm_autotrader --mode check --window-sec 30
```

目視画面:

```text
http://127.0.0.1:18081
```

check modeは、Flow遷移のたびに実際のHFM tick、symbol、volumeを使って
`order_check`まで実行するが、`order_send`は呼ばない。

`--mode live`はCLIと`FlowExecutionController`の両方でfail-closed拒否する。
将来、説明可能な統合ENTRY GOがユーザー承認された場合だけ、再利用可能な
`Mt5MarketOrderGateway`をその統合層へ別途接続する。

## 監査

既定監査ログ:

```text
data_05M/execution/flow_hfm_execution.jsonl
```

同じ`event_id`で以下が順に残る。

1. `FLOW_BASELINE`または`FLOW_TRANSITION`
2. `ORDER_INTENT`
3. `MT5_ORDER_CHECK`または`MT5_ORDER_SEND`

MT5結果にはretcode、order ticket、deal ticket、fill price、HFM Bid/Ask、
Flow signal price、source time、受信lagを保存する。

## 実機前提

- terminal: `C:\Program Files\HFM Metatrader 5\terminal64.exe`
- server: `HFMarketsGlobal-Live8`
- symbol: `#BTCUSDr`
- volume: `0.01`
- dashboard: `127.0.0.1:18081`

MT5端末上部の「アルゴリズム取引」はOFFを維持する。このprototypeを理由にONへ変更しない。
