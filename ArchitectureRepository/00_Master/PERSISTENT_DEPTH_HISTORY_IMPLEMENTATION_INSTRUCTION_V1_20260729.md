# Persistent Depth History Implementation Instruction V1

作成日: 2026-07-29  
Status: **DESIGN ONLY／source実装未承認**  
前提: 30分LIVE sizing（10,123 frames、5.6048 frame/s、約79.46MB/hour transport）

## 0. 目的と境界

Order Book Heatmap V1のsession-only storeを、容量・復元性・検証可能性を確認したうえで将来の日次depth historyへ拡張するための実装指示書である。本書の作成はsource実装、schema変更、writer有効化、runtime配備、purge承認を意味しない。

既存のFlow Price Response、3段チャート、Footprint、LIVE DOM、Time & Sales、OI、Strategy runtime、発注権限は変更しない。V1ではreplayへ存在しないdepthを補間しない。

## 1. 観測根拠

- 1,806.13秒で10,123 `BOOK_UPDATE`
- 5.6048 frame/s、平均99.87 bid＋ask levels/frame
- JSON transport 39,864,556 bytes（約3,939 bytes/frame）
- transport換算79.46MB/hour、1.907GB/day（圧縮・index・metadata前）
- WebSocket errors 0、health errors 0、latency-YELLOW 2

この数字は現行cadenceの一標本であり、固定容量保証ではない。実装前にsymbol、sync state、level count、payload sizeの分布を追加測定する。

## 2. 非交渉契約

### 2.1 Source

- authoritative sourceはvalidated `BOOK_UPDATE`のみ。
- `book_stream_id`、`book_sequence`、`event_time`、`projection_time`を保持する。
- exchange `last_update_id`はbrowser delivery sequenceの代用にしない。
- invalid／fail-closed／gap／restart区間は保存するが、valid resting liquidityとして描画・集計しない。
- source payloadの文字列価格・数量を勝手に丸めない。

### 2.2 Durability

- appendは一時segmentへ行い、fsync／atomic rename後だけdurableと数える。
- process crash中のpartial recordはchecksum／lengthで検出し、復元時にsilent repairしない。
- segment manifestへsymbol、UTC開始・終了、stream ID集合、first／last sequence、record count、byte count、checksum、compression、schema revisionを記録する。
- duplicateは`(symbol, book_stream_id, book_sequence)`でdedupし、別streamのsequence再利用を衝突させない。

### 2.3 Gap／restart

- sequence gap、stream restart、invalid payload、upstream resyncは明示eventとして記録する。
- gapを前後snapshotで補間しない。
- restart後はnew stream segmentを開始する。
- recovery時に旧streamのsequenceを継続しない。

## 3. Storage候補と比較計画

実装前に同一captureから次を比較する。

1. JSONL＋ZSTD（監査容易性のbaseline）
2. compact binary／typed record＋ZSTD
3. periodic keyframe＋diff encoding＋ZSTD

各候補でraw bytes、compressed bytes、compression ratio、writer CPU、write latency p50/p95/p99、recovery latency、read hydration latency、失敗時の再開位置を測る。候補を測定せずproduction schemaを選択しない。

## 4. Retention／容量

- retention期間は未決定。1日／7日／30日を候補として容量を実測する。
- automatic purgeは禁止。purgeは別承認・dry-run・manifest照合・recoverability確認後に行う。
- free disk safety thresholdとwrite-stop fail-closed境界を先に定義する。
- disk逼迫時にraw dataをsilent dropしない。明示health／alertとsegment close failureを出す。

## 5. Replay／API境界

- replayは保存済みvalid frameとgap markerだけを再生する。
- 保存されていない期間をcurrent live bookで埋めない。
- browser session Heatmapはhistoryを暗黙にlocalStorage／IndexedDBへ保存しない。
- 履歴APIはmanifest／segment cursor、UTC範囲、stream boundary、gap markerを返す。未準備範囲は空白＋理由を返す。

## 6. Test matrix

- append／fsync／atomic rename crash recovery
- checksum／partial tail／manifest不一致
- duplicate sequence、out-of-order、stream restart、gap、resync
- 1／7／30日容量 projection
- 25,000件 overflow accounting、長時間soak
- concurrent reader／writer、restart／reconnect
- replay no-live-mixing、browser gap表示
- disk threshold fail-closed、purge dry-run拒否

## 7. GO gate

- GO-PD0: capture分布・候補比較設計の承認
- GO-PD1: isolated writer／format prototype（本番未接続）
- GO-PD2: crash／recovery／replay契約
- GO-PD3: sizing／soak／disk safety
- GO-PD4: backend deployment（flag OFF）
- GO-PD5: operational activation／retention承認

各GOは独立した明示承認を必要とする。本書だけでsource実装・配備・purge・永続化有効化を開始しない。

## 8. Rollback

- writer flag OFFで新規appendを停止し、既存read-only履歴を壊さない。
- schema／segment形式を変更する場合は旧readerを保持する。
- user data、raw market data、既存DuckDB／Parquetを削除しない。
- Heatmap session-only modeへ戻してもFootprint／Tape／3段チャートを巻き戻さない。
