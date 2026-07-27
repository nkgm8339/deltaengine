# P3-c D5〜D8決裁・実行checkpoint

作成日: 2026-07-27 JST  
決裁者: お館様  
対象variant: `VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

## 決裁状態

D5〜D8は決裁済みとして実装工程へ移行する。

- D5: source-time価格履歴、ticks、window未完成omit。
- D6: wall candidate、tie-break、distance ticks、invalid book fail-closed。
- D7: OI source-time、5分窓、stale／欠測omit。
- D8: CalibrationBook供給のcomparator／threshold、candidate OR、contradiction ANY-match veto、欠測・未較正fail-closed。

## 実装状態

既存の `RealPredicateEvaluator` がD8の構造を実装済みである。

- `OPR-019`（E01）
- `OPR-020`（E02）
- `OPR-021`（E03）
- `INV-005`（E98）

各predicateは `CalibrationBook` の `PredicateCalibration` を通じて評価され、threshold値はproduction sourceへハードコードしない。専用試験を含むStrategy Engine回帰は合格済み。

## 残作業

- 収録データからのthreshold較正とholdout検証。
- 13件全てのstrategy-specific reference／temporal state材料が揃った後の追加predicate登録。
- runtime有効化・発注権限は別承認が必要であり、現時点では無効のまま。

## 検証

```text
python -m pytest -q -p no:cacheprovider
590 passed, 1 skipped
```

## 保存

WIP保存コミット: `fb390a0`  
このcheckpoint追加後、次のコミットで決裁反映記録を保存する。
