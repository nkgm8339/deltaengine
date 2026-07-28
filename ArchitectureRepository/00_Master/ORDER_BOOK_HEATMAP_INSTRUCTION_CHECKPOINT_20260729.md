# Order Book Heatmap instruction drafting checkpoint

最終更新: 2026-07-29 05:22 JST  
状態: **実装指示書V1作成・検証完了／source code未変更**

## 承認範囲

- Bookmap系の板ヒートマップについて、現repositoryに適合する実装指示書を作成する。
- 本承認は文書作成までであり、source code実装、runtime再起動、deployment、板履歴の永続化を含まない。
- 完成済みFlow Price Response、3段チャート、Footprint、LIVE DOM、Time & Salesを変更しない。

## 確認済み

- 本session着手時に`PROJECT_MEMORY.md`全文を確認済み。
- branch `feature/footprint-dom-tape`、HEAD `92ee4ef`、既存dirty worktreeを確認した。
- `BOOK_UPDATE`は`SYNCED`時のみbid／ask各top 50、Best Bid／Ask、Spread、event／projection time、update ID、ageを配信する。
- 非同期状態はlevelsを空にするfail-closed契約である。
- 設定値はbook projection 100ms、stale 2000ms、depth 50段である。
- `TAPE_UPDATE`はaccepted tradeをstream内連続sequence、exact price／quantity／notional、aggressive side付きで配信する。
- reconnect時は最新`BOOK_UPDATE`のみcache再送し、`TAPE_UPDATE`はcacheしない。
- 板履歴は永続化されていない。
- 既存central Canvas、右固定Tape、下段indicator、3段チャートのlayout境界を確認した。
- 正本候補`ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md`を作成した。
- resting liquidityとaggressive tradeの意味を分離した。
- `book_stream_id`／`book_sequence`のadditive continuity契約を固定した。
- session-only 15分、9,000 book frame、100,000 tradeのbounded contractを固定した。
- duration-weighted raster、Q95 logarithmic intensity、bubble radius、gap表示を固定した。
- `FOOTPRINT | HEATMAP`切替、primary 14px、既存layout保護を固定した。
- GO-H0〜H6、feature flag rollback、persistent history別GOを固定した。

## 採用予定の設計方向

- 中央領域を`FOOTPRINT | HEATMAP`切替にし、既存rendererを置換しない。
- V1は直近15分のsession内bounded historyとし、永続化は別GOへ分離する。
- resting liquidityとaggressive tradeを意味上分離する。
- fail-closed区間、Tape gap、stream restartを隠さない。
- Canvas＋bounded typed-array storeで実装し、primary label／tooltipは基本14pxとする。

## 未完了

- なし。本checkpoint承認範囲の文書作成は完了。
- source code実装は未承認であり、GO-H0待ち。

## 変更file

- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_INSTRUCTION_CHECKPOINT_20260729.md`
- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`

## 検証結果／blocker／再開位置

- source code変更: なし
- 文書規模: 31 H2 section（0〜30）、63 H3 section、acceptance checklist 18項目
- 文書contract check: section 0〜30連番PASS、code fence 20 balanced、必須contract 9 PASS、禁止承認表現0
- 現行config／payload／layoutとの照合: PASS
- blocker: なし
- 次の再開位置: ユーザーがV1を確認し、source実装を望む場合は明示GO-H0を受領してbaseline auditから開始する。
