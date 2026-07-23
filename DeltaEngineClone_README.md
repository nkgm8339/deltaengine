# DeltaEngineClone 分離メモ

このフォルダは、元のDeltaEngineと同じコード・仕様を保持した第2実行系です。
元システムと競合しないよう、クローン側だけ次を分離しています。

| 項目 | DeltaEngineClone |
|---|---|
| 起動ファイル | `DeltaEngineClone.bat` |
| Web URL | `http://localhost:18080` |
| Webポート | `18080` |
| MT5ポート | `15555` |
| Compose project | `deltaengine_clone` |
| データ | `Delta_Engine_Pro4web/data_clone/` |
| DuckDB | `data_clone/duckdb/orderflow_clone.duckdb` |
| 監視ログ | `data_clone/monitor/` |

元の `C:\Users\user\Desktop\DeltaEngine` のファイル・設定・完成済み機能は、この作業で変更していません。

同時起動時も、プロセス名・表示名・ポート・DB・ログ・一時書き込み先を混同しないことを目的とします。