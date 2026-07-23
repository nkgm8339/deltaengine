# DeltaEngineClone 外部衝突防止台帳

クローンは元DeltaEngineやホスト上の別アプリと同時稼働できるよう、書込み・制御系の資源を専用化する。

| 資源 | Clone専用値 | 元／他アプリとの扱い |
|---|---|---|
| Compose project | `deltaengine_clone` | 元のCompose projectと別名 |
| Compose network | `deltaengine_clone_default`（Compose生成） | 元ネットワークへ接続しない |
| Web公開 | `127.0.0.1:18080 -> container:8080` | 元の8080と重複しない |
| MT5 adapter | `127.0.0.1:15555 -> container:5555` | 元の5555と重複しない |
| Docker volume | `Delta_Engine_Pro4web/data_clone -> /app/data_clone` | 元の`data`をマウントしない |
| DuckDB / Parquet / monitor | `data_clone/...` | 元の書込み先と分離 |
| MT5 Common File | `DeltaEngineClone_HFM_quotes_utf8.jsonl` | 元の`DeltaEngine_HFM_quotes_utf8.jsonl`と別名 |
| InfinityX Common File | `DeltaEngineClone_HFM_InfinityX_quotes_utf8.jsonl` | 元のファイルと別名 |
| Observer PID | `data_clone/execution_costs/observer_clone.pid` | 元PIDと別名 |
| UI latency target | `ws://127.0.0.1:18080/ws` | 元の8080へ接続しない |

Binance等の市場データWebSocket／RESTは読み取り専用の同一公開エンドポイントを使う。共有しても書込み・停止制御の衝突は起こさない。注文・発注系の接続はこのクローンで有効化していない。

起動・停止は`DeltaEngineClone.bat`だけを使う。元のプロセスを名前検索で停止する操作や、元のDocker Compose projectをdownする操作は行わない。