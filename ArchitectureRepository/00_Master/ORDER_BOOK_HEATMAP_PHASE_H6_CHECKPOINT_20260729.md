# Order Book Heatmap GO-H6 checkpoint

更新: 2026-07-29 06:50 JST  
承認: user `G-h6` interpreted as `GO-H6`

## 完了

- H1 backend image built and deployed: `sha256:f75a4d99f59840338a3aa39f870987b5b4b97e81ca3f40f02b7de8d24d149def`.
- Production container: `05edf40f9bfd`.
- Container source confirms `book_stream_id`／`book_sequence`.
- Static bind-mounted UI flag enabled: `ORDER_BOOK_HEATMAP_ENABLED=true`.
- HTTP health GREEN and WebSocket `BOOK_UPDATE` with `book_sequence=371`／UUID stream observed.
- 15-minute LIVE observation: 30 samples. 28 all-GREEN; 2 latency-YELLOW samples. Pipeline／Tape／Book gap／reconnect／memory stayed GREEN in all samples.
- Rollback rehearsal: temporary container created from `rollback-pre-h6-20260729` (`sha256:2a8c6d243e6caacc2c1ab29de58062616d098db21bf0e6e9c022c03894d61bcb`), inspected successfully, then removed.
- Final health GREEN; current container recent log scan found StorageError／Traceback／Parquet I/O error 0.

## 限定状態

The two latency-YELLOW samples were transient upstream/runtime latency observations; no pipeline, Tape, Book continuity, storage, or browser payload failure was observed. Continue normal monitoring.

## 次の再開位置

V1 operational activation is complete. Persistent depth history remains a separate future instruction／GO. Do not modify completed Flow Price Response, 3-stage chart, Footprint, Tape, or OI behavior.

## Browser verification note

HTTP/static marker and WebSocket checks passed. Edge headless DOM dump against the live WebSocket page timed out after 69s; therefore browser DOM/page-error acceptance is **UNCONFIRMED**, not claimed PASS. This blocker is limited to browser automation and does not invalidate the independent health／payload／15-minute LIVE／rollback results.
