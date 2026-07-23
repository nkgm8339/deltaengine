# 復旧手順（退避線 2026-07-19）

後戻りが必要になった場合、以下のいずれかで復旧できる。上から順に試すこと。

## 方法1: git タグから復旧（最速）
    cd /d C:\Users\user\Desktop\DeltaEngine
    git stash        （作業中の変更を退避したい場合のみ）
    git checkout SAFE-20260719

## 方法2: 物理バックアップから復旧（git が壊れた場合）
    C:\Users\user\Desktop\DeltaEngine_BACKUP_20260719 を丸ごとコピーして戻す

## 方法3: web保管ZIPから復旧（ローカルが全滅した場合）
    webに依頼する。2026-07-19時点の全体ZIP（DeltaEngine.zip）を保管済み。

## 退避線の内容
- 対象: v3.6.4 稼働状態の全ツリー（Delta_Engine_Pro4web / ArchitectureRepository / releases 含む）
- 既知の障害: オーダーブック初期同期が不成立（板パネル空表示）。約定系（CVD/Footprint/Signal/Flow）は正常
- 注意: バックアップには __pycache__ / DuckDB実行時ファイルを含まない（再生成可能なため除外）
