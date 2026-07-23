この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_BugFix_Live_v1

**対象**: ライブパイプラインのバグ修正 2 件
**前提**: 204 passed

---

## 0. 問題

### Bug 1: aggTrade が 0 件

live_verify 実行で `normalized: 0`、`trades_stored: 0`。60 秒間で raw_out 587（≒10件/秒 = depth のみ）。aggTrade イベントが全く到着していない。

原因候補: Binance Futures の `/ws` エンドポイントで SUBSCRIBE 後、aggTrade メッセージが `{"stream":"btcusdt@aggTrade","data":{...}}` のようにラップされて到着している可能性。この場合 `message.get("e")` は None になり、`is_agg_trade_or_depth` が False を返してフィルタされる。

修正: `is_agg_trade_or_depth` と `classify_raw` の両方で、ラップ形式（`message.get("data", {}).get("e")`）にも対応する。receiver に渡す前に connector または binance_ws 側でアンラップするのが最もクリーン。`BinanceStream.__anext__` で `"data"` キーがあればアンラップして返す。

### Bug 2: depth diff が全て gap 棄却

`book_snapshots_applied: 1` だが `book_diffs_rejected_before_snap: 585`、`book_gaps_detected: 1`。

REST snapshot の `lastUpdateId` と最初の WS diff の `first_update_id` の間にギャップが発生し、gap 検出で `_initialized = False` にリセット → 以降の全 diff が「snapshot 前」として棄却。

修正: Binance 公式ドキュメントの手順に従う。
1. WS 接続を先に開始し、depth イベントをバッファリング
2. REST snapshot を取得
3. `first_update_id <= lastUpdateId+1 <= final_update_id` の最初の diff から適用開始
4. それ以前の diff は捨てる

`OrderBookStateManager` に初期同期ロジックを追加する。具体的には:
- `apply_initial_sync(snapshot_update_id: int)` メソッドを追加
- snapshot 適用後、`_sync_id = snapshot_update_id` を保持
- diff の `first_update_id <= _sync_id + 1` かつ `final_update_id >= _sync_id + 1` の最初の diff で同期完了
- 同期完了前の diff は `diffs_stale` としてカウント（`diffs_rejected_before_snapshot` ではなく）

`LivePipeline.run_async` の順序を変更:
1. connector/receiver を先に起動（depth をバッファリング）
2. REST snapshot 取得・適用
3. バッファ済み depth diff を同期ロジックで処理

---

## 1. 修正ファイル

- `src/acquisition/binance_ws.py`: `BinanceStream.__anext__` でラップ形式をアンラップ
- `src/orderflow/orderbook.py`: `OrderBookStateManager` に初期同期ロジック追加
- `src/pipeline.py`: `run_async` の snapshot/connector 起動順序変更

---

## 2. テスト

### 追加テスト（3 本）

1. `test_binance_ws.py` 追記: ラップ形式メッセージがアンラップされて返ること
2. `test_orderbook.py` 追記: 初期同期ロジック（snapshot 後、gap のある diff → 同期前 diff は stale、同期 diff 以降は applied）
3. `test_binance_rest.py` 追記: snapshot → 同期 → diff 適用の E2E

既存 204 本は無変更。合計 207 本以上。

---

## 3. 完了条件

- [ ] 207 本以上 green、既存 204 本無影響
- [ ] 実ネットワークで `python -m tools.live_verify --duration 30` を実行し、`normalized > 0` かつ `book_diffs_applied > 0` であること（スクリーンショットを報告に含める）
- [ ] 正本無変更

---

## 4. 報告

CompletionLog.md 追記 + `DeltaEngine_BugFix_Live_完了.zip` + チャット報告（live_verify 実測結果含む）
