# 指示書: Phase 2-3 Stage 2 Task 1 設計確定調査(アダプタ経路)
Version: 1.0
発行: Claude(統括) → Codex(実装)
対象: DeltaEngine05M / Heatmap Phase 2-3 Stage 2
前提: Task 1調査で、orderbook_heatmap.js(HEAD)が動的ヒートマップ(store/スクロール/duration加重ラスタ/gap/p95計測)を実装済みと判明。frame_sourceはrecording(OrderBookSnapshot)→book payloadアダプタと再定義。ADR「Replay/Live同一applyコア共有」に沿い、アダプタがpush_broker経由か直接組成かを確定する。
段階: 調査のみ。変更・実装・新規ソース生成を行わない。読み取りのみ。

---

## 規律
- src/heatmap・保護ファイル・git・stagingを変更するな。読み取りのみ。
- 全回答に ファイル:行番号 を併記。設計の是非判定を書くな。事実と論点提示のみ。

## 調査項目

### K1. BookProjection の構造と生成元
- `BookProjection`(webapp/book_projection.py想定)のフィールド全定義を ファイル:行番号 で示せ。特に best_bid/best_ask/spread/sync_state/event_time/projection_time/depth_levels/last_update_id/bids/asks の有無。
- ライブ経路で BookProjection がどこで OrderBookSnapshot 相当から生成されるか(book_manager/projection pump等)を ファイル:行番号 で示せ。

### K2. push_broker.on_book_update の入力契約
- `on_book_update(projection: BookProjection)` が payload を組む箇所で、BookProjection のどのフィールドを book payload のどのキーへ写像するかを ファイル:行番号 で示せ(第二コミット後の push_broker.py:250-300 付近)。
- book_stream_id/book_sequence/best_bid/best_ask/spread が payload に入る経路を特定せよ。

### K3. OrderBookSnapshot → BookProjection の距離
- OrderBookSnapshot(symbol/last_update_id/bids dict/asks dict/event_time)から BookProjection を構成するのに不足するフィールド(best/spread/projection_time/depth_levels/sync_state等)を列挙し、それぞれ既存コードで算出する関数があるか(best bid/ask/spread計算等)を ファイル:行番号 で示せ。無ければ「該当なし」と明記。

### K4. 既存Canvas gate=false の理由痕跡
- index.html の presentation gate(`H:index.html:969` 付近)が false である箇所と、その周辺コメント・関連フラグを ファイル:行番号 で示せ。
- gate を true にした場合に有効化される要素(Canvas/ボタン/setup)の範囲を ファイル:行番号 で示せ。
- orderbook_heatmap.js または index.html に、gate offの理由・未完了事項を示すコメント/TODO/FIXMEがあるか grep で示せ。無ければ「該当なし」。

### K5. replay/recording供給の既存フック
- 既存に recording を replay して webapp へ流す経路(ReplayPipeline → webapp)があるか、`src/pipeline.py` の ReplayPipeline と webapp/main.py の replay分岐を ファイル:行番号 で示せ。
- recording(depth_history_raw)を読む既存の webapp側エントリがあるか示せ。無ければ「該当なし」。

## 提出物
- K1-K5 の調査結果(ファイル:行番号併記)
- 参照ファイルのHEAD SHA-256とbyte/LF/CR
- `git rev-parse HEAD`(bf95126), `git status --porcelain -- Delta_Engine_Pro4web/`(core M追加なし), `git diff --cached --name-only`(空)

## 禁止事項
- 実装・変更・新規ソース生成。
- 設計の是非判定・GO/NO-GO記載。

以上。提出後、統括がアダプタ経路(push_broker経由 or 直接組成)とframe_sourceの実装インターフェース、Task 1の対象ファイル(新規モジュール位置)を確定し、Task 1実装指示書を発行する。
