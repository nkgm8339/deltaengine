# Persistent depth history instruction checkpoint

完了: 2026-07-29 07:42 JST  
承認: user `GO` — instruction作成のみ

## 完了

- 30分LIVE sizing結果を根拠にV1 instructionを作成。
- authoritative BOOK_UPDATE、durability、gap／restart、candidate format比較、retention、replay、test matrix、GO-PD0〜PD5、rollback境界を明文化。
- source、DB schema、writer、archive、runtime、purgeは変更していない。

## 未完了

- GO-PD0以降のsource実装、format benchmark、persistent deployment、retention有効化。

正本: `PERSISTENT_DEPTH_HISTORY_IMPLEMENTATION_INSTRUCTION_V1_20260729.md`
