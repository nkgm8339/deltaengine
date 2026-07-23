# DeltaEngineClone

DeltaEngineの実行系を同一内容のまま分離したクローンです。元の
`C:\Users\user\Desktop\DeltaEngine` と同時に起動できるよう、名称、Composeプロジェクト、ポート、書き込み先を分けています。

## 起動

```bat
DeltaEngineClone.bat
DeltaEngineClone.bat stop
```

起動URLは `http://localhost:18080` です。

## 分離設定

- 表示・起動識別子: `DeltaEngineClone`
- Docker Composeプロジェクト: `deltaengine_clone`
- Webポート: `18080`（元は `8080`）
- MT5アダプタ: `127.0.0.1:15555`（元は `5555`）
- 書き込みデータ: `Delta_Engine_Pro4web/data_clone/`
- DuckDB: `data_clone/duckdb/orderflow_clone.duckdb`
- 監視ログ: `data_clone/monitor/`

Flow Price Response、3段チャート、CVD、Delta、OI、Flow Eventの計算と表示は元から変更していません。
変更したのはクローン識別子と、同時稼働に必要な実行環境の分離だけです。