
# 指示書: Calibration_Log 反映作業

code kun,

下記手順を、確認と承認を求めずに全て即座に実行せよ。

## 1. 現状 config 値の確認

- `config/config.yaml` を開き、以下3値を確認せよ。
  - `signal.stack_ref` = 5
  - `imbalance.min_volume` = 0.002  
  - `signal.cvd_slope_ref` = 65.203
- 上記以外の場合は、web に報告せよ。一致なら次へ進め。

## 2. テストの実行

- `python -m pytest -q` を実行し、 **348 passed** を確認せよ。
- エラーや件数相違があれば web に報告せよ。完走なら次へ。

## 3. CHANGELOG.md への追記

- `ArchitectureRepository/00_Master/CHANGELOG.md` を開く。
- ファイル先頭の `---` の直後に、以下を挿入せよ。

```md
# v3.6.7 — 2026-07-20

## Changed

- 較正(課題5): `signal.stack_ref` 3 → 5、`imbalance.min_volume` 0.5 → 0.002 を実測較正で反映。stacked run 長 P80 / レベル総出来高 P25 に基づく(`tools/calibrate_refs.py`)。stack_ref=3 は 3スタック1本で ±100 到達=飽和のため是正。
- `signal.cvd_slope_ref` は 65.203 据え置き(課題6見送り)。サンプル 2,515 件で P80 推奨は 26.5 だが、65.203 → 26.5 は CVD 感度が約 2.46 倍に上がるため、課題5のみ反映して様子見とした。

## Unchanged

- コード無変更(config 値のみ)。テスト件数不変(348 passed)。DuckDB/Parquet スキーマ・正本モジュール仕様は無変更。

---
```

## 4. CompletionLog.md への追記

- `ArchitectureRepository/00_Master/CompletionLog.md` を開く。 
- ファイル末尾に、以下を追記せよ。

```md
---

## Calibration_v1: stack_ref・min_volume 実測較正(課題5)/ cvd_slope_ref 見送り(課題6)

**実施日時**: 2026-07-20
**指示書**: `00_プロジェクト引継ぎ書_v3.19.md` §2

### 完了報告

- 課題5(較正実行): `tools/calibrate_refs.py` により実測較正を実施し `config/config.yaml` へ `--write` 反映。
  - `signal.stack_ref`: 3 → **5**(stacked run 長 P80)
  - `imbalance.min_volume`: 0.5 → **0.002**(レベル総出来高 P25)
  - 狙い: シグナル飽和の是正。stack_ref=3 は 3スタック1本で ±100 到達=飽和しやすい問題を実測分布で是正。
- 課題6(cvd_slope_ref 再較正): **見送り**。
  - サンプル 2,515 件で P80 推奨値は 26.5。
  - 65.203 → 26.5 は CVD 感度が約 2.46 倍に上がるため、課題5のみ反映して様子見と判断。`signal.cvd_slope_ref` は **65.203 据え置き**。
- コード変更なし(config 値のみ)。テスト: **348 passed**(無影響)。

### 較正前後の値

| キー | 較正前 | 較正後 |
|---|---|---|
| signal.stack_ref | 3 | 5 |
| imbalance.min_volume | 0.5 | 0.002 |
| signal.cvd_slope_ref | 65.203 | 65.203(据え置き) |

### 逸脱

なし。
```

## 5. 本番 UI の version 追従確認

- `docker-compose up --build` で本番起動せよ。
- ブラウザで `http://localhost:8080` を開き、画面右上の version 表示が `v3.6.7` に変わったことを確認せよ。
- 変わっていなければ web に報告せよ。表示が `v3.6.7` なら完了。

## 6. 完了報告

- 手順1〜5を全て滞りなく完了したら、以下の書式で web に報告せよ。
- 手順名が「確認」の場合は実測値、「追記」の場合は対象ファイル名を括弧内に記すこと。

```
お館様、

code です。calibration_log 反映作業を完了しました。
各手順の結果は以下の通りです。

1. 現状 config 値の確認 (stack_ref=5, min_volume=0.002, cvd_slope_ref=65.203)
2. テストの実行 (348 passed)
3. CHANGELOG.md への追記 (ArchitectureRepository/00_Master/CHANGELOG.md)
4. CompletionLog.md への追記 (ArchitectureRepository/00_Master/CompletionLog.md)
5. 本番 UI の version 追従確認 (v3.6.7)

全手順を問題なく完了しました。ご確認ください。
```

以上だ。web からの許可や合図は一切待つな。黙って全て実行しろ。
