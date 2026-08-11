# 指示書: Phase 2-3 Stage 2 Task 1 最終設計材料(build_book_projection依存)
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3 Stage 2
前提: 設計方針確定。frame_source = OrderBookSnapshot → 最小book_stateラッパ → 既存build_book_projection → book payload → Canvas ingestBook(ADR applyコア共有)。ラッパのインターフェース確定に、build_book_projectionのbook_state依存とsync_state分岐を要する。
段階: 調査のみ。変更・実装・新規ソース生成を行わない。読み取りのみ。

---

## 規律
- 変更するな。読み取りのみ。全回答に ファイル:行番号 併記。判定を書くな。事実のみ。

## 調査項目

### L1. build_book_projection 全文
```
sed -n で webapp/book_projection.py の build_book_projection 関数全体(定義行〜return)を提出
```
関数本体を無編集で全文提出せよ(book_projection.py:85-220相当)。

### L2. book_state に対する呼び出し・属性アクセスの全列挙
build_book_projection 内で引数 `book_state`(第1引数)に対して呼ぶメソッド・アクセスするプロパティを、出現順に ファイル:行番号 で全列挙せよ。例: `.snapshot()`, `.age_ms(...)`, `.last_event_time`, `.gaps_detected`, `.is_synchronized` 等。各々の引数と戻り値の使われ方も1行で示せ。

### L3. sync_state 分岐条件
sync_state が各値(SYNCED / STALE / INVALID / EMPTY / LOCKED / CROSSED / NO_SNAPSHOT / 他)に決まる条件を、判定に使う入力(snapshot有無、bids/asks内容、best bid<ask、gaps_detected、is_synchronized、age_ms)ごとに ファイル:行番号 で示せ。
特に「SYNCEDになるための必要条件」を、入力値の観点で明示せよ。

### L4. OrderBookStateManager 公開インターフェース
`src/orderflow/orderbook.py` の OrderBookStateManager の公開メソッド・プロパティ(snapshot, age_ms, last_event_time, gaps_detected, is_synchronized 等)のシグネチャと戻り値型を ファイル:行番号 で全列挙せよ。build_book_projectionが依存する各メンバの実体を対応づけよ。

### L5. envelope と d2s の payload 出力仕様
push_broker.on_book_update が payload を組む際の envelope 構造と、Decimal→str 変換(d2s等)の適用箇所を ファイル:行番号 で示せ(第二コミット後のpush_broker.py)。book payload の最終キー一覧(book_stream_id, book_sequence, bids, asks, best_bid, best_ask, spread, sync_state, event_time, projection_time, last_update_id, depth_levels)の各値の型(str/number)を示せ。

## 提出物
- L1 build_book_projection全文
- L2 book_state依存メンバ全列挙(行番号付き)
- L3 sync_state分岐(SYNCED必要条件を明示)
- L4 OrderBookStateManager公開IF
- L5 envelope/payloadキーと型
- 参照ファイルのHEAD SHA-256とbyte/LF/CR
- `git rev-parse HEAD`(bf95126), `git status --porcelain -- Delta_Engine_Pro4web/`, `git diff --cached --name-only`(空)

## 禁止事項
- 実装・変更・新規ソース生成。判定・GO/NO-GO記載。

以上。提出後、統括がOrderBookSnapshotラッパの正確なインターフェース仕様(実装すべきメソッド・戻り値・SYNCED保証条件)とframe_sourceのアダプタIF、Task 1の対象ファイル位置・単体テスト要件を確定し、Task 1実装指示書を発行する。
