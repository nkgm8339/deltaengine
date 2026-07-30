# Stage 2C-3 Hook threshold較正・発火頻度検証レポート
実行日時: 2026-07-30 16:29:00 JST
実行者: Codex
対象データ: stage2a_20260726_xz/full（全session）

## 実行境界

- 変更対象: `config/hook_thresholds.yaml`、同日付backup、`tools/calibrate_hooks.py`、本レポート。
- 非変更対象: 収録データ、`playbooks.yaml`、UI、稼働中liquidation stream。
- 較正対象: 指示された38 Hookのみ。
- 較正対象外: C03/C04/C05/C07/C08/D06/F01-F05。entryを作らず、`default_status: UNCALIBRATED`でfail closedを維持する。
- threshold判断の変更は行わず、指定p90値とdetector metric方向を使用する。

## Phase 1: YAMLスキーマ確認

確認箇所:

- `src/orderflow/hooks/config.py`
  - `ThresholdBook.load`: 197-244行
  - `ThresholdBook.evaluate`: 254-286行
- `src/orderflow/hooks/models.py`
  - `HookThreshold`: 142-203行

rootで許可されるkeyは`schema_version`、`default_status`、`thresholds`だけであり、`schema_version`は整数`1`でなければならない。`default_status`は`CalibrationStatus` enum文字列、`thresholds`はHook IDをkeyとするmappingである。

各threshold entryで許可されるkey:

| YAML field | 読込型 | 必須性・制約 |
|---|---|---|
| `metric` | string | 実質必須。空文字は`HookThreshold`が拒否する。candidateの`metric_name`と完全一致が必要。 |
| `operator` | string | 必須。`ge`/`gt`/`le`/`lt`/`always`のみ。今回は`ge`/`le`を使用。 |
| `quantile` | numeric/null | schema上は任意。指定どおり数値`0.90`を記録し、0〜1に制限される。 |
| `value` | numeric/null | numeric operatorかつCALIBRATEDでは必須。loaderは`Decimal(str(value))`へ変換する。 |
| `status` | string | 必須。今回は`CALIBRATED`。 |
| `input_manifest_sha256` | string/null | CALIBRATEDでは必須。lowercase 16進64文字。 |
| `sample_count` | integer | 任意、default 0、非負。今回の分布countを記録。 |
| `valid_days` | integer | 任意、default 0、非負。72時間収録として3を記録。 |

CALIBRATED entryでもqualityがVALIDでない、metric不一致、manifest hash不一致、operator判定不成立の場合は`ThresholdBook.evaluate`がfail closedする。今回使用する入力manifest集合SHA-256は次の値である。

`f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b`

## Phase 2: operator確定

| Hook | metric | 有意方向 | operator | 根拠 |
|---|---|---|---|---|
| A01/A02 | `level_quantity_over_side_median` | 大 | `ge` | wall量/side中央値。wallが相対的に大きいほど有意（`dom_wall.py` 34-74行）。 |
| A03/A04 | `untraded_removed_fraction` | 大 | `ge` | 非約定で除去されたwall比率（同76-127行）。 |
| A05/A06 | `depth_removed_fraction` | 大 | `ge` | depth減少率の絶対値（`dom_liquidity.py` 32-58行）。 |
| A07/A08 | `depth_added_fraction` | 大 | `ge` | depth増加率（同32-58行）。 |
| A09/A10 | `dominant_to_opposite_depth_ratio` | 大 | `ge` | 優勢側/反対側depth比（同86-103行）。 |
| A11-A14 | `best_quote_move_bps` | 大 | `ge` | best quote移動幅の絶対値（`dom_quote_motion.py` 27-55行）。 |
| A15 | `spread_expansion_bps` | 大 | `ge` | spread拡大幅（`dom_liquidity.py` 60-72行）。 |
| A16 | `spread_contraction_bps` | 大 | `ge` | spread回復幅の絶対値（同73-84行）。 |
| A17/A18 | `replenished_to_executed_ratio` | 大 | `ge` | 執行量に対する補充量比（`dom_iceberg.py` 43-92行）。 |
| A19/A20 | `untraded_pull_count` | 大 | `ge` | 同priceでの非約定pull累積回数（`dom_wall.py` 97-126行）。 |
| A21/A22 | `maximum_upside/downside_level_gap_bps` | 大 | `ge` | 最大level gap。vacuumが広いほど有意（`dom_liquidity.py` 105-122行）。 |
| A23/A24 | `wall_tracking_move_bps` | 大 | `ge` | 追随方向へのwall移動幅（`dom_wall.py` 129-154行）。 |
| C06 | `aggressive_to_wall_quantity_ratio` | 大 | `ge` | wall初期量に対するaggressive量比（`interaction.py` 84-134行）。 |
| D07 | `trapped_duration_ms` | 大 | `ge` | trapped状態の継続時間（`flow_transition.py` 86-98行）。 |
| D08 | `aligned_window_count` | 大 | `ge` | 同方向に揃ったwindow数（同100-132行）。 |
| G01/G02 | `distance_to_recent_high/low_bps` | 小 | `le` | Hook名はrecent high/low touch。距離が小さいほど接触に近い（`price_structure.py` 129-150行、`registry.py` 69-75行）。 |
| G03/G04 | `high/low_break_bps` | 大 | `ge` | recent high/lowを越えたbreak幅（`price_structure.py` 151-172行）。 |
| G05/G06 | `failed_break_return_bps` | 大 | `ge` | break level内側へのreturn幅（同102-127行）。 |
| G07 | `distance_to_session_vwap_bps` | 小 | `le` | Hook名はVWAP touch。距離が小さいほど接触に近い（同198-209行、`registry.py` 73行）。 |
| G08 | `absolute_vwap_deviation_bps` | 大 | `ge` | Hook名はVWAP deviation extreme。絶対乖離が大きいほど有意（同210-220行、`registry.py` 73行）。 |
| G09 | `distance_to_high_volume_node_bps` | 小 | `le` | Hook名はvolume node touch。距離が小さいほど接触に近い（同223-237行）。 |
| G10 | `distance_to_round_number_bps` | 小 | `le` | Hook名はround number touch。距離が小さいほど接触に近い（同238-252行）。 |
| G11 | `distance_to_nearest_range_edge_bps` | 小 | `le` | nearest range edgeへの距離（同174-188行）。 |

G07/G08は現実装で同じ`deviation_bps`をcandidate valueに使用するため分布が同一である。ただしHook意味がtouchとextremeで反対なので、G07は`le`、G08は`ge`とする。原因調査・設計見直しは後続タスクとし、本タスクでは変更しない。

## Phase 3: threshold書き込み

指定38 Hookのentryを書き込み、`default_status: UNCALIBRATED`を維持した。`ThresholdBook.load`に成功し、次を機械検証した。

- CALIBRATED: 38 Hook
- 対象外11 Hook: 全件UNCALIBRATED
- 全entryのp90値と`sample_count`: Stage 2C-2 JSONと一致
- `quantile`/`value`: YAML上で文字列ではなくnumeric
- ThresholdBook config hash: `3767970766d5a70c7cf570e520e3ff495f57aaab5b76d9a6b610768383861444`
- backup Git blobと変更前HEADのYAML blob: ともに`c591a9f986eada7aabb26c08a1fa5c99398ce4f6`で完全一致

更新後のYAML全文:

```yaml
schema_version: 1
default_status: UNCALIBRATED

# Stage 2C p90 calibration from the hashed 72-hour append-only full journal.
# Missing entries remain UNCALIBRATED and fail closed.
thresholds:
  A01:
    metric: level_quantity_over_side_median
    operator: ge
    quantile: 0.90
    value: 3407.1428571429
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 723556
    valid_days: 3
  A02:
    metric: level_quantity_over_side_median
    operator: ge
    quantile: 0.90
    value: 3161.5
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 723265
    valid_days: 3
  A03:
    metric: untraded_removed_fraction
    operator: ge
    quantile: 0.90
    value: 0.9480510776
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 423212
    valid_days: 3
  A04:
    metric: untraded_removed_fraction
    operator: ge
    quantile: 0.90
    value: 0.9582662537
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 416832
    valid_days: 3
  A05:
    metric: depth_removed_fraction
    operator: ge
    quantile: 0.90
    value: 0.2257413037
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 935052
    valid_days: 3
  A06:
    metric: depth_removed_fraction
    operator: ge
    quantile: 0.90
    value: 0.230138894
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 931297
    valid_days: 3
  A07:
    metric: depth_added_fraction
    operator: ge
    quantile: 0.90
    value: 0.266824863
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 1011389
    valid_days: 3
  A08:
    metric: depth_added_fraction
    operator: ge
    quantile: 0.90
    value: 0.2759758466
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 1007302
    valid_days: 3
  A09:
    metric: dominant_to_opposite_depth_ratio
    operator: ge
    quantile: 0.90
    value: 7.4475869641
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 1194226
    valid_days: 3
  A10:
    metric: dominant_to_opposite_depth_ratio
    operator: ge
    quantile: 0.90
    value: 6.6616221957
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 1080611
    valid_days: 3
  A11:
    metric: best_quote_move_bps
    operator: ge
    quantile: 0.90
    value: 0.8919830986
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 41240
    valid_days: 3
  A12:
    metric: best_quote_move_bps
    operator: ge
    quantile: 0.90
    value: 0.8975032953
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 40084
    valid_days: 3
  A13:
    metric: best_quote_move_bps
    operator: ge
    quantile: 0.90
    value: 0.8949303141
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 40302
    valid_days: 3
  A14:
    metric: best_quote_move_bps
    operator: ge
    quantile: 0.90
    value: 0.8902801853
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 41429
    valid_days: 3
  A15:
    metric: spread_expansion_bps
    operator: ge
    quantile: 0.90
    value: 0.0000015227
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 41438
    valid_days: 3
  A16:
    metric: spread_contraction_bps
    operator: ge
    quantile: 0.90
    value: 0.0000015405
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 40251
    valid_days: 3
  A17:
    metric: replenished_to_executed_ratio
    operator: ge
    quantile: 0.90
    value: 1644
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 285761
    valid_days: 3
  A18:
    metric: replenished_to_executed_ratio
    operator: ge
    quantile: 0.90
    value: 1661
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 316051
    valid_days: 3
  A19:
    metric: untraded_pull_count
    operator: ge
    quantile: 0.90
    value: 62
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 423212
    valid_days: 3
  A20:
    metric: untraded_pull_count
    operator: ge
    quantile: 0.90
    value: 67
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 416832
    valid_days: 3
  A21:
    metric: maximum_upside_level_gap_bps
    operator: ge
    quantile: 0.90
    value: 0.0784677447
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 2274837
    valid_days: 3
  A22:
    metric: maximum_downside_level_gap_bps
    operator: ge
    quantile: 0.90
    value: 0.0784220849
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 2274837
    valid_days: 3
  A23:
    metric: wall_tracking_move_bps
    operator: ge
    quantile: 0.90
    value: 0.914078283
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 88938
    valid_days: 3
  A24:
    metric: wall_tracking_move_bps
    operator: ge
    quantile: 0.90
    value: 0.9113299525
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 93831
    valid_days: 3
  C06:
    metric: aggressive_to_wall_quantity_ratio
    operator: ge
    quantile: 0.90
    value: 0.0660099463
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 670740
    valid_days: 3
  D07:
    metric: trapped_duration_ms
    operator: ge
    quantile: 0.90
    value: 1465.2
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 2039
    valid_days: 3
  D08:
    metric: aligned_window_count
    operator: ge
    quantile: 0.90
    value: 4
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 63787
    valid_days: 3
  G01:
    metric: distance_to_recent_high_bps
    operator: le
    quantile: 0.90
    value: 15.8790121078
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3935
    valid_days: 3
  G02:
    metric: distance_to_recent_low_bps
    operator: le
    quantile: 0.90
    value: 17.1345938592
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3935
    valid_days: 3
  G03:
    metric: high_break_bps
    operator: ge
    quantile: 0.90
    value: 7.0508754708
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 620
    valid_days: 3
  G04:
    metric: low_break_bps
    operator: ge
    quantile: 0.90
    value: 6.4573440178
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 710
    valid_days: 3
  G05:
    metric: failed_break_return_bps
    operator: ge
    quantile: 0.90
    value: 8.5284948314
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 307
    valid_days: 3
  G06:
    metric: failed_break_return_bps
    operator: ge
    quantile: 0.90
    value: 8.1968877126
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 334
    valid_days: 3
  G07:
    metric: distance_to_session_vwap_bps
    operator: le
    quantile: 0.90
    value: 35.113490544
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3963
    valid_days: 3
  G08:
    metric: absolute_vwap_deviation_bps
    operator: ge
    quantile: 0.90
    value: 35.113490544
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3963
    valid_days: 3
  G09:
    metric: distance_to_high_volume_node_bps
    operator: le
    quantile: 0.90
    value: 12.5287637773
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3963
    valid_days: 3
  G10:
    metric: distance_to_round_number_bps
    operator: le
    quantile: 0.90
    value: 3.4887781038
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3963
    valid_days: 3
  G11:
    metric: distance_to_nearest_range_edge_bps
    operator: le
    quantile: 0.90
    value: 9.2906141325
    status: CALIBRATED
    input_manifest_sha256: f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b
    sample_count: 3935
    valid_days: 3
```

## Phase 4: 発火頻度検証

### 実行条件と整合性

`tools/calibrate_hooks.py --with-thresholds`をホスト側Pythonで実行し、2 workerを`Idle` priorityかつ別々のlogical CPUへ固定した。sessionごとにdetector stateをresetし、session失敗時はtransaction rollbackでpartial candidateを残さない。稼働中のliquidation収録コンテナ内では実行していない。

- 実行開始: 2026-07-30 16:37:36 JST
- 結果生成: 2026-07-30 18:32:40 JST
- 経過時間: 6,902.803秒
- session: 29選択、28成功、1失敗
- 成功record: 9,054,572
- candidate: 15,667,491
- input manifest SHA-256: `f90fda5131a3a317039fdbc2596737c406319c8066004893e1c47c076a1b548b`
- threshold config hash: `3767970766d5a70c7cf570e520e3ff495f57aaab5b76d9a6b610768383861444`
- Stage 2C-2との照合: 49 Hookすべてのcandidate countが一致。38較正Hookのcandidate countも全件一致。
- eligible: 全38 Hookでcandidate数と一致。quality INVALIDまたはmetric不一致による除外は0件。
- 既知の失敗: `session-20260726T041939.403610Z-1e9ed663` — `JournalIntegrityError: segment is not closed: raw-20260726T04.jsonl.xz`

発火率は指示どおり`threshold通過数 / candidate生成数`で算出した。

| Hook ID | operator | threshold | candidate数 | 発火数 | 発火率 | 判定 |
|---|---|---:|---:|---:|---:|---|
| A01 | ge | 3407.1428571429 | 723556 | 72354 | 9.999779% | 正常 |
| A02 | ge | 3161.5 | 723265 | 72328 | 10.000207% | 正常 |
| A03 | ge | 0.9480510776 | 423212 | 42322 | 10.000189% | 正常 |
| A04 | ge | 0.9582662537 | 416832 | 41684 | 10.000192% | 正常 |
| A05 | ge | 0.2257413037 | 935052 | 93506 | 10.000086% | 正常 |
| A06 | ge | 0.230138894 | 931297 | 93130 | 10.000032% | 正常 |
| A07 | ge | 0.266824863 | 1011389 | 101139 | 10.000010% | 正常 |
| A08 | ge | 0.2759758466 | 1007302 | 100731 | 10.000079% | 正常 |
| A09 | ge | 7.4475869641 | 1194226 | 119423 | 10.000033% | 正常 |
| A10 | ge | 6.6616221957 | 1080611 | 108061 | 9.999991% | 正常 |
| A11 | ge | 0.8919830986 | 41240 | 4124 | 10.000000% | 正常 |
| A12 | ge | 0.8975032953 | 40084 | 4009 | 10.001497% | 正常 |
| A13 | ge | 0.8949303141 | 40302 | 4031 | 10.001985% | 正常 |
| A14 | ge | 0.8902801853 | 41429 | 4143 | 10.000241% | 正常 |
| A15 | ge | 0.0000015227 | 41438 | 4144 | 10.000483% | 正常 |
| A16 | ge | 0.0000015405 | 40251 | 4026 | 10.002236% | 正常 |
| A17 | ge | 1644 | 285761 | 28579 | 10.001015% | 正常 |
| A18 | ge | 1661 | 316051 | 31607 | 10.000601% | 正常 |
| A19 | ge | 62 | 423212 | 42643 | 10.076038% | 正常 |
| A20 | ge | 67 | 416832 | 42413 | 10.175083% | 正常 |
| A21 | ge | 0.0784677447 | 2274837 | 227459 | 9.998914% | 正常 |
| A22 | ge | 0.0784220849 | 2274837 | 227502 | 10.000804% | 正常 |
| A23 | ge | 0.914078283 | 88938 | 8894 | 10.000225% | 正常 |
| A24 | ge | 0.9113299525 | 93831 | 9384 | 10.000959% | 正常 |
| C06 | ge | 0.0660099463 | 670740 | 67074 | 10.000000% | 正常 |
| D07 | ge | 1465.2 | 2039 | 204 | 10.004904% | 正常 |
| D08 | ge | 4 | 63787 | 10496 | 16.454764% | 要注意 |
| G01 | le | 15.8790121078 | 3935 | 3541 | 89.987294% | 異常 |
| G02 | le | 17.1345938592 | 3935 | 3541 | 89.987294% | 異常 |
| G03 | ge | 7.0508754708 | 620 | 62 | 10.000000% | 正常 |
| G04 | ge | 6.4573440178 | 710 | 71 | 10.000000% | 正常 |
| G05 | ge | 8.5284948314 | 307 | 31 | 10.097720% | 正常 |
| G06 | ge | 8.1968877126 | 334 | 34 | 10.179641% | 正常 |
| G07 | le | 35.113490544 | 3963 | 3566 | 89.982337% | 異常 |
| G08 | ge | 35.113490544 | 3963 | 397 | 10.017663% | 正常 |
| G09 | le | 12.5287637773 | 3963 | 3566 | 89.982337% | 異常 |
| G10 | le | 3.4887781038 | 3963 | 3566 | 89.982337% | 異常 |
| G11 | le | 9.2906141325 | 3935 | 3541 | 89.987294% | 異常 |

### 判定結果

- 正常: 31 Hook
- 要注意: D08（16.454764%）。`aligned_window_count`が整数かつp90=4でtieが多いため、`ge 4`の通過率が10%を上回った。
- 異常: G01/G02/G07/G09/G10/G11（89.98〜89.99%）。
- 異常6 Hookはいずれも「小さいほど有意」のdistance/touch metricへ`le`を適用した結果である。分布レポートのp90は上側90%点なので、数学的には約90%が`<= p90`となる。これはoperator方向と指定p90の組合せによる期待可能な結果だが、指示された判定基準では異常である。
- 指示どおり、要注意・異常Hookのthreshold、quantile、operatorは修正していない。後続判断が必要である。
- G07/G08は同じcandidate分布・同じp90値だが、G07=`le`で89.982337%、G08=`ge`で10.017663%となった。分布同一の原因調査は後続タスクとする。

## 事後状態

取得日時: 2026-07-30 18:38:14 JST

- container: `delta_engine_pro4web-deltaengine_clone-1` — `Up 9 hours`
- port: host `18080` → container `8080`
- health: YELLOW
  - YELLOW: `sequence_gap=1`、`ws_reconnect=1`、`memory=969MB`
  - GREEN: `pipeline exceptions=0`、`bar_flow last=11s`、`event lag=0ms`、`tape dropped=0 pending=1 send_failures=0 balanced=True`
- C:空き: 93,309,956,096 bytes
- `localhost:8080`は未公開のため接続不可。`docker ps`で確認した公開port `localhost:18080/api/health`から取得した。

health生出力:

```json
{"state":"YELLOW","sample_time":"2026-07-30T09:38:10.912150+00:00","checks":{"sequence_gap":{"level":"YELLOW","value":"1","detail":"book gaps in window: 1"},"ws_reconnect":{"level":"YELLOW","value":"1","detail":"reconnects in window: 1"},"pipeline":{"level":"GREEN","value":"0","detail":"pipeline exceptions in window: 0"},"bar_flow":{"level":"GREEN","value":"11","detail":"last bar 11s ago"},"latency":{"level":"GREEN","value":"0","detail":"event lag 0ms"},"memory":{"level":"YELLOW","value":"969","detail":"rss 969MB"},"tape":{"level":"GREEN","value":"0","detail":"dropped=0 pending=1 send_failures=0 balanced=True"}},"anomalies_today":246}
```

## テスト結果

| command | 結果 |
|---|---|
| `python -m pytest tests/orderflow/test_stage2b_dom_detectors.py tests/orderflow/test_stage2b_context_detectors.py -q` | PASS — 14 passed in 0.20s |
| `python -m pytest -q -p no:cacheprovider` | 727 passed, 1 skipped, 1 failed in 118.10s |

全体回帰の唯一の失敗:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
assert 'body.phase5-fusion #right>#left{display:none!important}' in html
```

本タスク開始前から変更済みだった`webapp/static/index.html`では当該selectorが`body.phase5-fusion #main>#left{display:none!important}`へ変更されており、testの期待文字列と不一致だった。本タスクの対象差分は`config/hook_thresholds.yaml`、backup、`tools/calibrate_hooks.py`、本レポートだけで、UIは変更していない。禁止事項に従い、この既存UI/test不整合は修正せず記録のみとした。

## 作業checkpoint

- checkpoint日時: 2026-07-30 18:45 JST
- 承認範囲: 指定38 Hookのp90較正、backup、host側read-only replay、発火頻度集計、指定test、指定成果物のcommit。
- 完了済み: PROJECT_MEMORY全文再読、preflight、YAML schema確認、detector metric方向確認、operator確定、元YAML backup、`--with-thresholds`実装、YAML本体38 entry更新、load/entry/p90/count/numeric型/backup検証、bounded distribution smoke、発火SQL smoke、全29 session replay、Stage 2C-2 count完全一致確認、38 Hook発火頻度集計・判定、Phase 4レポート反映、YAML全文埋込み・一致確認、事後health/C:空き取得、対象test、全体回帰・既存UI失敗切り分け、最終config/script/report/backup検証、指定4 fileだけのstage・cached diff check。
- 未完了: レポートcheckpoint再stage、commit、post-commit確認。
- 変更file: `config/hook_thresholds.yaml`、`config/hook_thresholds.yaml.bak.20260730`、`tools/calibrate_hooks.py`、本レポート。
- 検証済み:
  - 開始HEAD: `bffe6f5f4dfd195429874d9ec80bd3464beb73f8`
  - 既存stagingなし。
  - backup pathは作成前に不存在を確認。
  - 開始時container: `delta_engine_pro4web-deltaengine_clone-1`、Up。
  - 開始時health: GREEN。
  - 開始時C:空き: 93,207,269,376 bytes。
  - `python -m py_compile tools/calibrate_hooks.py`: 成功。
  - 3 session選択/各1,000 record bounded smoke: 既知の1 error、2成功、2,000 records、8,242 candidatesでStage 2C-2基準と一致。
  - in-memory発火SQL smoke: `ge`/`le`、VALID/INVALID、metric一致/不一致を含め全assertion成功。
  - 全量run直前C:空き: 93,181,632,512 bytes。
  - 全量run直前container: Up。overall YELLOW（開始前からRSS 930MB）だが、pipeline/gap/reconnect/latency/TapeはGREEN。
  - 全量run開始: 2026-07-30 16:37:36 JST。host親PID 18004、worker PID 11712/10412。
  - 全process priority `Idle`、worker affinity `4`/`8`（logical CPU 2/3へ個別固定）。
  - 全量run終了・JSON生成: 2026-07-30 18:32:40 JST。
  - 29 session選択、28成功、1既知ERROR。9,054,572 records、15,667,491 candidates。
  - Stage 2C-2 JSONとの49 Hook count不一致: 0。
  - 較正38 Hookのcandidate count不一致: 0。eligible除外: 0。
  - 発火判定: 正常31、要注意1、異常6。threshold修正なし。
  - レポート埋込みYAMLと実ファイル: 完全一致。
  - 事後container: Up 9 hours。
  - 事後health: YELLOW（gap 1、reconnect 1、RSS 969MB）。pipeline/latency/tapeはGREEN。
  - 事後C:空き: 93,309,956,096 bytes。
  - detector対象test: 14 passed。
  - 全体回帰: 727 passed、1 skipped、1 failed。唯一の失敗は開始前から変更済みのUI selectorとtest期待値の不一致で、本変更と無関係。
  - `python -m py_compile tools/calibrate_hooks.py`: 成功。
  - 最終`ThresholdBook.load`: 成功。CALIBRATED 38、対象外UNCALIBRATED 11、config hash一致。
  - backupと変更前HEAD YAML Git blob: `c591a9f986eada7aabb26c08a1fa5c99398ce4f6`で一致。
  - レポート埋込みYAMLと実ファイル: 再検証で一致。
  - cached file: 指定4件のみ。`git diff --cached --check`: 成功。
- blocker: なし。
- 次の再開位置: 本checkpointを再stageし、cached file/checkを再確認後、指定messageでcommitする。
