# Big Trades Effort／Result V2 書き直し CHECKPOINT

- 更新時刻: 2026-08-12 01:01:06 JST
- user承認: 現行Big Trades指示書を、Fabio型の判断目的を満たす内容へ書き直す
- 承認範囲: logic正本V2、実装指示書V2、文書検証まで
- source実装、config変更、test実行、runtime変更、UI変更、deployment: 対象外
- branch: `feature/big-trades-v1`
- 開始HEAD: `8e81cb389d459afa68bb5a85bbe4e593d7bfe19b`

## 書き直し理由

現行V1/V1.1は、4項目のうちManual Min／Max、Automatic Size Filter、marker＋履歴を定義したが、大口約定価格から時間方向へ延長し、後続価格の反応、反復攻撃、拒否、突破を追うReaction Zoneを対象外にした。

Fabio本人の公開判断はBig Trade markerの検出で完了せず、`effort`と`price result`、同一価格帯での反復、反対側の失敗、level protectionを時系列で照合する。Size Filter単体の完成をFabio型判断の完成としてはならない。

## 開始時事実

- staged tracked change: 0 file。
- unstaged tracked change: 0 file。
- untracked: pre-Big-Trades除外manifest記載の23 local生成物。
- V1 logic SHA-256: `84D108F8F4DC4DBC6D95C58301EEBE23E0EC200779ED391FEDB5E39A71ECD4E6`。
- V1.1 instruction SHA-256: `8548AF1905B7A4AC47FBB2914496C39F2D046FD7131A23BAED7F3FCE7528`。
- V1／V1.1は削除・上書きせず、誤りの経緯を確認できる旧版として保持する。

## 完了済み

- `AGENTS.md`と`PROJECT_MEMORY.md` 1,725行を全文確認した。
- V1.1実装指示書3,135行を全文確認した。
- V1 Size Filter logicのscope、marker、history、公開事実／推論境界を確認した。
- Fabio公式70動画監査、具体証拠16事例、観測研究、問1選別文書を再確認した。
- 欠落が技術的制約ではなく、V1 logicのscopeをSize Filterまでへ狭めた結果であることを確定した。
- `DEEPCHARTS_BIG_TRADES_EFFORT_RESULT_REACTION_ZONE_LOGIC_V2_20260812.md`を作成した。
- V2 logicにManual Min／Max、Automatic Size Filter、event marker／history、Reaction Zone／result observationを一続きの決定論的logicとして固定した。
- `DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V2_20260812.md`をstandalone指示書として作成した。
- V2 instructionへschema、pipeline、API、UI、performance、296 test contracts、固定vector、7工程、rollback、checkpoint、30禁止shortcut、traceability、acceptanceを固定した。
- system factとuser assessmentを分離し、Fabio本人の非公開formulaを自動再現したと偽装しない境界を固定した。
- 既存3段chartとFlow Price Responseをprotected scopeとして固定した。
- `BIG_TRADES_V2_APPLICATION_CHANGE_EXPLANATION_20260812.md`へ、現在のアプリは未変更であることと、V2実装後に追加される画面・選別・marker・Reaction Zone・result履歴を記録した。

## V2の目的

```text
大口規模候補を抽出する
  → 約定価格帯をReaction Zoneとして時間方向へ保持する
  → 後続価格の位置、移動量、再訪、反復攻撃、突破、拒否をsource timeで記録する
  → effortとresultを同じevent／zone／履歴／Replayで比較できる
```

V2は売買signal、勝率、発注許可を生成しない。Fabio本人が公開していない判断式を本人のformulaとして偽装しない。画面には確認済み市場事実と、明示的にDeltaEngine再構成である状態名だけを出す。

## 未完了

- source実装は未着手。今回の承認範囲外である。
- config変更、DB migration、backfill、service restart、UI変更、feature enableは未着手。今回の承認範囲外である。
- 次工程はuserが工程番号または具体的作業を明示するまで開始しない。

## 変更file

- `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_EFFORT_RESULT_REACTION_ZONE_LOGIC_V2_20260812.md`
  - 1,111行。
  - SHA-256: `62FCC2DE602F87FC0B9BE3CFF92793B7F416770002B1C03160FA0F7650B44244`。
- `ArchitectureRepository/00_Master/DEEPCHARTS_BIG_TRADES_IMPLEMENTATION_INSTRUCTION_V2_20260812.md`
  - 2,405行。
  - SHA-256: `DD1D7CCFD246AA1AA4AA4103A89614E65F295435B2A7FEB7C679B239728B3F43`。
- `ArchitectureRepository/00_Master/BIG_TRADES_EFFORT_RESULT_V2_REWRITE_CHECKPOINT_20260812.md`
  - 本file。自己参照になるため本文内へ自己hashを埋め込まない。
- `ArchitectureRepository/00_Master/BIG_TRADES_V2_APPLICATION_CHANGE_EXPLANATION_20260812.md`
  - 216行。
  - SHA-256: `CD3377B7866DC1E3C5FE182C533E90DA874AAF59213F062A729DB09B5BBC46D2`。

既存tracked source／config／runtime／UIの変更は0件。開始前から存在する23 untracked local生成物へ変更を加えていない。

## 検証結果

- source、config、runtime、UI変更: 0件。
- logic正本のlevel-2 section: 0～38、39件、欠番0、重複0。
- 実装指示書のlevel-2 section: 0～75、76件、欠番0、重複0。
- test contract: 296件、ID 001～296、欠番0、重複0、list ordinal不一致0。
- Markdown code fence: logic 130 lines、instruction 156 lines、両方偶数でbalanced。
- trailing whitespace: 4文書とも0行。
- tab: 4文書とも0行。
- application change説明書: code fence balanced、trailing whitespace 0行。
- `git diff --check`: error 0。
- tracked staged／unstaged diff: 0 file。
- test: 文書だけの変更であり、source testは未実行。

## blocker

- なし。

## 次の再開位置

- V2 instruction §74に従い、userが承認する工程番号と未決定運用値を確認する。
- source実装を開始する場合の最初の位置は§59「工程0：baseline／design lock」である。
