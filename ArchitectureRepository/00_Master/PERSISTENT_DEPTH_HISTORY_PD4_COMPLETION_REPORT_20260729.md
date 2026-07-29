# Persistent Depth History GO-PD4 completion report

完了: 2026-07-29 07:49 JST  
判定: **BACKEND COMPATIBILITY DEPLOYMENT PASS／writer OFF**

GO-PD4を完了した。composeへ`PERSISTENT_DEPTH_HISTORY_ENABLED=false`を追加し、persistent writerを呼び出さないcompatibility boundaryを再配備した。既存Heatmap operational image／static UIは維持し、persistent schema／archive／retentionは接続していない。

Identity:

- deployed container: `6a08017f2911`
- image: current H6 image `sha256:f75a4d99f59840338a3aa39f870987b5b4b97e81ca3f40f02b7de8d24d149def`
- rollback tag: `rollback-pre-pd4-20260729` → same H6 image identity

Verification:

- container env contains `PERSISTENT_DEPTH_HISTORY_ENABLED=false`
- final `/api/health`: GREEN; pipeline／Tape／Book gap／reconnect／latency／memory GREEN
- rollback temporary container create／remove: PASS
- isolated PD3／PD4 tests: **4 passed**

No persistent writer, DB／Parquet schema, archive, retention, purge, or replay source was changed.
