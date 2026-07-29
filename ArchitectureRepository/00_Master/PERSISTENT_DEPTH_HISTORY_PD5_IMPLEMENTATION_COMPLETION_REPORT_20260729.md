# Persistent Depth History PD5 implementation completion report

完了: 2026-07-29 08:12 JST  
判定: **PRODUCTION WRITER ACTIVATION PASS（limited soak）**

PD5のpreflight NO-GOを解消し、PD1／PD2／PD3の契約をproduction WebSocket `BOOK_UPDATE`経路へ接続した。

## Implementation

- `webapp/persistent_depth_writer.py`: dedicated UTC depth segment writer
- PushBroker `BOOK_UPDATE` append hook
- `webapp/main.py` env-gated writer lifecycle
- compose flags:
  - `PERSISTENT_DEPTH_HISTORY_ENABLED=true`
  - `PERSISTENT_DEPTH_HISTORY_ROOT=/app/data_05M/depth_history`
- existing DuckDB／Parquet storage remains separate

## Deployment identity

- corrected image: `pd5-fixed-20260729` (latest image built from corrected source)
- active container: `befd08691576` replacement lineage; final running container verified via compose
- rollback tag: `rollback-pre-pd5-20260729`

## Verification

- writer／PushBroker／book contracts／PD3: **48 passed**
- final health: GREEN
- dedicated depth path: 2 closed manifests／2,000 records＋1 open `.part` segment
- recent 10-minute logs: StorageError／Traceback／persistent writer errors 0
- short rotation observation: health mostly GREEN; one transient YELLOW sample, final GREEN
- manifest records and open segment are outside existing DuckDB／Parquet tables

初回PD5 imageは`PushBroker.__init__`のintegration mismatchで起動失敗したが、即時に検出・修正・再build／再配備した。初回failed containerをactivation PASSとは扱わない。

PD5はwriter activationの限定PASSであり、長期soak、retention／purge、replay API、browser history hydrationは次工程である。
