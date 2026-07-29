# Order Book Heatmap Phase H6 completion report

完了時刻: 2026-07-29 06:50 JST  
判定: **OPERATIONAL ACTIVATION PASS**

GO-H6を完了した。H1 continuity backendを含むimageをbuild／再配備し、runtimeで`BOOK_UPDATE`の`book_stream_id`／`book_sequence`を確認した。static bind-mounted UIのHeatmap flagをtrueへ切り替え、HTTP health、WebSocket payload、15分LIVE観測、rollback rehearsalを実施した。

Identity:

- image: `sha256:f75a4d99f59840338a3aa39f870987b5b4b97e81ca3f40f02b7de8d24d149def`
- container: `05edf40f9bfd`
- rollback fallback: `rollback-pre-h6-20260729` → `sha256:2a8c6d243e6caacc2c1ab29de58062616d098db21bf0e6e9c022c03894d61bcb`

Verification:

- final `/api/health`: GREEN
- WebSocket BOOK_UPDATE: UUID stream／sequence observed
- 15-minute observation: 30 samples、28 all-GREEN、2 latency-YELLOW。pipeline／Tape／Book gap／reconnect／memoryは全サンプルGREEN
- recent production logs: StorageError／Traceback／Parquet I/O error 0
- rollback rehearsal temporary container: PASS、removed

Persistent depth history、live order、Strategy runtime、MT5 algorithmic tradingは変更していない。Flow Price Response、3段チャート、Footprint、Tape、OIの既存計算・構造・操作も変更していない。

注記: Edge headlessのlive DOM dumpはWebSocket接続待ちで69秒timeoutとなったため、browser DOM／page-error項目は未確認と明示する。HTTP static marker、実WebSocket payload、health、15分LIVE観測、rollback rehearsalは別途PASS。
