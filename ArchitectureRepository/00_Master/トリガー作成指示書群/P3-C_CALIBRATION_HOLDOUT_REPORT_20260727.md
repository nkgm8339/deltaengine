# P3-c Calibration / Holdout実測報告

作成日: 2026-07-27 JST  
対象: `BTCUSDT` / `1m`  
実行: 2026-07-27

## 1. 入力データ

元DBは `dllhost.exe` が保持中だったため、元DBを変更せず、workspace内コピーに対してread-only較正を実行した。

```text
data_05M/duckdb/orderflow_05M_calibration_20260727.duckdb
```

実測範囲:

```text
trades : 2026-07-23 16:56:47.644000 ～ 2026-07-27 09:42:43.929000
candles: 2026-07-23 16:56 ～ 2026-07-27 09:41
```

## 2. 実測較正候補

既存ツールをdry-runで実行した。production configへの書き込みは行っていない。

```text
python tools/calibrate_cvd.py --days 7 --db data_05M/duckdb/orderflow_05M_calibration_20260727.duckdb
CVD slope ref (P80 of |delta|): 26.434
symbol=BTCUSDT timeframe=1m samples=4846
window_start=2026-07-20T09:41:00 days=7
```

```text
python tools/calibrate_refs.py --days 7 --db data_05M/duckdb/orderflow_05M_calibration_20260727.duckdb
imbalance.min_volume (P25): 0.002
bars=4851 level_samples=720369
window_start=2026-07-20T09:42:43.929000 days=7
signal.stack_ref (P80): 5
stacked_samples=96831
```

## 3. G16 holdout判定

G16の実測thresholdを確定するholdoutは未成立である。

理由:

- 入力期間は約3.7日で、7日較正窓を満たしていない。
- 現行DuckDBにG16の正解label、strategy-specific reference identity、temporal prerequisite stateがない。
- CVD／imbalanceの既存較正候補はG16 13件のthresholdそのものではない。
- したがって、上記候補をG16 CalibrationBookへ流用することはしていない。

## 4. 安全状態

- `config/hook_thresholds.yaml` は変更していない。
- G16の実測thresholdは未較正のまま。
- runtime有効化・発注権限は0。
- holdoutを見た後のthreshold再調整は行っていない。

## 5. 次の入力条件

G16の較正を完了するには、少なくとも以下が必要である。

1. calibration期間とuntouched holdout期間を分離した収録。
2. E01／E02／E03／E98のreference identityとtemporal stateを含む観測列。
3. G16各predicateの正解labelまたは独立妥当性判定。
4. 版付きCalibrationBook manifest。

本報告は「実データで測れる既存候補は測定したが、G16 thresholdを捏造せず、holdout未成立を確定した」記録である。
