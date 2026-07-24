# DeltaEngine05M 分離メモ

このフォルダは、元のDeltaEngineと同じコード・仕様を保持した第2実行系です。
元システムと競合しないよう、クローン側だけ次を分離しています。

| 項目 | DeltaEngine05M |
|---|---|
| 起動ファイル | `DeltaEngine05M.bat` |
| Web URL | `http://localhost:18080` |
| Webポート | `18080` |
| MT5ポート | `15555` |
| Compose project | `deltaengine_05M` |
| データ | `Delta_Engine_Pro4web/data_05M/` |
| DuckDB | `data_05M/duckdb/orderflow_05M.duckdb` |
| 監視ログ | `data_05M/monitor/` |

元の `C:\Users\user\Desktop\DeltaEngine` のファイル・設定・完成済み機能は、この作業で変更していません。

同時起動時も、プロセス名・表示名・ポート・DB・ログ・一時書き込み先を混同しないことを目的とします。
