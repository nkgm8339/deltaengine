
# 指示書: calibration_log 追記作業

code kun,

引継ぎ書の内容が正しいことが確認できたので、予定通り CHANGELOG.md と CompletionLog.md への追記を実行してくれ。以下の手順を、確認や承認を求めずに即座に実行せよ。

## 手順1: CHANGELOG.md への追記

`ArchitectureRepository/00_Master/CHANGELOG.md` を開き、先頭の `---` の直後に以下を挿入せよ。

```
# v3.6.7 — 2026-07-20

## Changed

- 較正(課題5): `signal.stack_ref` 3 → 5、`imbalance.min_volume` 0.5 → 0.002 を実測較正で反映。stacked run 長 P80 / レベル総出来高 P25 に基づく(`tools/calibrate_refs.py`)。stack_ref=3 は 3スタック1本で ±100 到達=飽和のため是正。
- `signal.cvd_slope_ref` は 65.203 据え置き(課題6見送り)。サンプル 2,515 件で P80 推奨は 26.5 だが、65.203 → 26.5 は CVD 感度が約 2.46 倍に上がるため、課題5のみ反映して様子見とした。

## Unchanged

- コード無変更(config 値のみ)。テスト件数不変(348 passed)。DuckDB/Parquet スキーマ・正本モジュール仕様は無変更。

---
```

## 手順2: CompletionLog.md への追記

`ArchitectureRepository/00_Master/CompletionLog.md` を開き、ファイル末尾に以下を追記せよ。

```
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

## 手順3: バージョン表示の確認 

追記作業が完了したら、`docker-compose up --build` で本番を起動せよ。
ブラウザで `http://localhost:8080` を開き、右上の version 表示が `v3.6.7` に変わったことを確認せよ。

## 手順4: 完了報告

手順1〜3が完了したら、以下のフォーマットで完了報告をせよ。

```
お館様、

code です。CHANGELOG.md と CompletionLog.md への calibration_log 追記を完了しました。
docker-compose up 後の http://localhost:8080 でバージョン表示が v3.6.7 に昇格したことを確認済みです。

これにてタスクは全て完了しました。ご確認ください。
```

以上だ。web からの確認や許可を一切待たず、ただちに実行せよ。
