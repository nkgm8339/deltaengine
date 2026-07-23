# DeltaEngine 復元手順（新PC / 壊れたとき）

このリポジトリ（1M 本体 = `Delta_Engine_Pro4web`）から、新しい PC で動く状態に戻すための手順。

> 要点: **コードと設定は GitHub にある。過去データ(DB/parquet)は容量が大きく GitHub に入らないため、別ドライブのバックアップから手動で戻す**（不要なら空スタートでよい。未来のデータはライブから再生成される）。

---

## 1. 前提ソフトを入れる（新PCで一度だけ）

- **Python 3.12**（https://www.python.org/downloads/ ／インストール時に「Add python to PATH」にチェック）
- **Git**（https://git-scm.com/download/win）

確認:
```powershell
python --version   # Python 3.12.x
git --version
```

## 2. クローン

```powershell
cd $HOME\Desktop
git clone https://github.com/nkgm8339/deltaengine.git Delta_Engine_Pro4web
cd Delta_Engine_Pro4web
```

## 3. 依存ライブラリを入れる（ネット必要・数分）

```powershell
python -m pip install -r requirements.txt
```

## 4. 起動

```powershell
.\start.ps1
```

- ブラウザで http://127.0.0.1:8080 が開く。
- 動作確認: `Invoke-WebRequest http://127.0.0.1:8080/health` が `{"status":"ok"}` を返せば成功。
- 停止: 起動したウィンドウで `Ctrl+C`。

> `start.ps1` は clone 直下で動く自己完結ランチャ。従来の `archive/maintenance-scripts/DeltaEngine1M-Manager.ps1`（プロセス所有チェック等つき）は「親フォルダ layout（`deltaengine/Delta_Engine_Pro4web`）」を前提にするため、丸ごとの旧環境を再現する場合のみ使う。参考コピーを `scripts/legacy-launchers/` に同梱。

## 5. （任意）過去データを戻す

過去の記録（DuckDB / parquet）が必要な場合のみ。GitHub には含まれないので、別ドライブのバックアップ zip から復元する:

```powershell
# 例: J:\DeltaEngine_DB_backup_YYYYMMDD.zip を展開して data/ 配下へ
Expand-Archive -Path "J:\DeltaEngine_DB_backup_YYYYMMDD.zip" -DestinationPath ".\data" -Force
```

不要なら何もしなくてよい（空の `data/` のままライブ観測は動く）。

---

## 含まれるもの / 含まれないもの

| 種類 | GitHub | 備考 |
|------|:------:|------|
| アプリのコード（webapp/src/tools/tests） | ✅ | |
| 設定（config/config.yaml, profiles） | ✅ | |
| 起動スクリプト（start.ps1 / legacy launchers） | ✅ | |
| requirements.txt（依存一覧） | ✅ | |
| 過去データ（data/duckdb, data/parquet） | ❌ | サイズ超過。別ドライブに退避 |
| 観測の生ログ（data/execution_costs, latency 等） | ❌ | 再生成される記録 |

## メモ
- 30M 製品（port 8180 / `Delta_Engine_30M`）は別フォルダ・別バックアップ。ここには含まれない。
- Python 導入と `pip install` だけは新PC側で必ず必要（これは避けられない）。
