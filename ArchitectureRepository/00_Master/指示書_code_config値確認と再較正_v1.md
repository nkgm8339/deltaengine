
# 指示書: config 値確認と再較正

code kun,

以下の手順を、確認や承認を求めずに即座に実行してくれ。

## 手順1: config.yaml の3値を確認

`C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web\config\config.yaml` を開き、以下3つのキーの値を確認せよ。

- `signal.stack_ref`
- `imbalance.min_volume`
- `signal.cvd_slope_ref`

各値が以下の通りなら、手順4へ進め。

- `signal.stack_ref = 5`
- `imbalance.min_volume = 0.002`
- `signal.cvd_slope_ref = 65.203` 

もしどれかが異なっていたら、手順2へ進め。

## 手順2: 再較正の実行

プロジェクトのルートディレクトリ(`C:\Users\user\Desktop\DeltaEngine\Delta_Engine_Pro4web`)で以下を実行せよ。

```
python -m tools.calibrate_refs --write
```

これにより `signal.stack_ref` と `imbalance.min_volume` が実測データから再計算され、config.yaml へ上書きされる。

## 手順3: テストの実行

再較正の影響を確認するため、プロジェクトのルートディレクトリで以下を実行せよ。

```
python -m pytest -q
```

テストが全て(348 passed)成功することを確認せよ。もし失敗があれば、理由を調査し、完全な修正をせよ。そして再度テストを実行し、全件成功を確認せよ。

## 手順4: 完了報告

手順1〜3が完了したら、以下のフォーマットで web に報告せよ。

```
お館様、

code です。config 値の確認と、必要な再較正を完了しました。
最終的な config.yaml の該当3値は以下の通りです。

signal.stack_ref = (値)
imbalance.min_volume = (値) 
signal.cvd_slope_ref = (値)

pytest は (件数) passed です。

これにて当該タスクは完了です。次のご指示をお願いします。
```

以上だ。ただちに実行せよ。
