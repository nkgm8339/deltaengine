# DE多重起動設計

## 目的

複数の Windows 端末へ DeltaEngine 一式を配置し、使いたい端末で MT5 と
DeltaEngine を独立して起動できるようにする。VPS・常時稼働・端末間の自動同期は
前提としない。

## 基本方針

- 各端末は `DeltaEngine` フォルダ一式、Docker Desktop、MT5 をそれぞれ保持する。
- DeltaEngine と MT5 の通信は、その端末内の `127.0.0.1:5555` に限定する。
- 各端末の `data/`、ログ、MT5 設定はローカルに保持し、自動同期しない。
- 起動はルートの `DeltaEngine.bat` を使用する。
- フル構成の対象は Windows PC / Windows タブレットとする。iPad / Android は対象外。

## 端末ごとの構成

```text
<端末>
├─ MT5
└─ DeltaEngine/
   ├─ DeltaEngine.bat
   ├─ Delta_Engine_Pro4web/
   │  ├─ config/
   │  ├─ data/            # 端末固有。更新で保持する
   │  └─ logs/            # 端末固有。更新で保持する
   └─ ArchitectureRepository/
```

## 安全ルール

1. 通常は「分析のみ」モードで起動する。
2. MT5 連携を有効にする場合だけ、明示的に「ライブ」モードを選ぶ。
3. 同一の MT5 口座に対し、複数端末で同時にライブ起動しない。
   独立端末だけでは、他端末のライブ起動を完全には検知・停止できないためである。
4. ライブ利用の可否と複数ログインの扱いは、利用ブローカーの規約にも従う。

## 実装ロードマップ

### V1: 端末独立起動

- `device.yaml` を端末ごとに用意し、端末名（例: `HOME-PC`、`LAPTOP`）を設定する。
- UI に端末名、アプリ版、分析のみ / ライブの状態を表示する。
- 共通設定と端末固有設定を分離する。
- 起動バッチで Docker、設定、ポート、必要フォルダを事前検査する。

### V2: 安全な更新配布

- バージョン情報と変更履歴を配布物に同梱する。
- 更新時に `data/`、ログ、端末固有設定を保持する。
- 更新後に設定検証と起動確認を実行する。

### 将来検討

- 端末間のデータ同期。
- 同一口座へのライブ起動を排他制御する共有ロック。
- VPS / クラウド運用。

## 非目標（V1）

- VPS 上での常時稼働。
- 端末間のリアルタイム同期。
- iPad / Android 上での DeltaEngine ローカル実行。

## V1 の設計詳細

### 配布単位

配布単位はリポジトリのルート `DeltaEngine/` とする。`Delta_Engine_Pro4web/` 単体では `ArchitectureRepository/00_Master/CHANGELOG.md` を compose が参照するため不完全である。リリースには `DeltaEngine.bat`、`Delta_Engine_Pro4web/`、`ArchitectureRepository/`、`RELEASE.json` を必ず含める。`RELEASE.json` にはリリース版、作成日時、コミット識別子、設定スキーマ版を記録する。端末設定・データ・ログ・MT5の認証情報は配布物に含めない。

### 端末設定

`Delta_Engine_Pro4web/config/device.example.yaml` を配布し、初回起動時に `config/device.yaml` を作成する。後者はGit管理・更新対象外とする。

```yaml
# config/device.yaml（端末固有、配布しない）
device:
  id: home-pc                 # 英小文字・数字・ハイフンのみ。端末ごとに一意
  display_name: HOME-PC

runtime:
  mode: analysis              # analysis | mt5_live
  web_port: 8080              # 同一PC上で複数コピーを動かす時だけ変更
```

- `id` はDocker Composeのプロジェクト名、ログ名、UI表示の識別子に使う。
- `analysis` はMT5アダプターを強制的に無効化する安全な既定値とする。
- `mt5_live` はMT5設定が有効で、起動時に利用者が明示確認した場合のみ許可する。
- 端末名、稼働モード、版、設定ハッシュをUIと起動ログへ表示する。
- 口座番号、パスワード、APIキーなどの秘密情報は `device.yaml` にも保存しない。

### 起動契約

ルートの `DeltaEngine.bat` を唯一の通常起動口とする。バッチは、自身の場所からプロジェクトルートを求め、`device.yaml` の存在・必須項目・`device.id` の書式を検査し、Docker Desktopを確認する。ライブモードの時は端末名とMT5連携有効を表示して確認を求め、`--project-name deltaengine-<device.id>` と `web_port` を渡してcomposeを起動する。`/health` 応答後だけローカルブラウザを開く。

Composeの公開ポートは次のように変数化し、既定では端末外へ公開しない。

```yaml
ports:
  - "127.0.0.1:${DE_WEB_PORT:-8080}:8080"
  - "127.0.0.1:5555:5555"
```

同一PCで複数コピーを同時実行する場合は `device.id` と `runtime.web_port` をそれぞれ固有にする。MT5ポート5555は、一台のMT5と一つのライブ構成を前提とする。

### データと更新

- `data/` と `logs/` は端末ローカルの運用データであり、自動同期しない。
- 更新パッケージはアプリコード、共通設定の雛形、仕様書だけを更新する。
- 更新前に端末固有の `device.yaml` と `data/` を退避し、更新後に復元する。
- 履歴を混ぜる必要が出た時だけ、エクスポート／インポートを別機能として設計する。共有DuckDBをネットワークドライブで直接開かない。

### 運用上の排他

V1は中央サーバーを持たないため、別PCで同じMT5口座を同時ライブ起動しているかを技術的に完全検知できない。ライブ起動時は端末名・版・ローカルMT5ポートを大きく表示し、同一口座で同時利用しない運用とする。将来、端末を跨ぐ排他が必要になった時だけ、外部共有ロックを導入する。

## 受け入れ条件（V1）

1. 同じリリースを別のWindows PCへ任意のフォルダ名でコピーして起動できる。
2. 各PCはDocker DesktopとMT5をローカルに持ち、他PCやVPSなしで動く。
3. 分析モードではMT5アダプターが待受しない。
4. ライブモードは明示確認がなければ起動しない。
5. UIとログから、端末名・アプリ版・稼働モードを確認できる。
6. 一方の端末の `data/`、`logs/`、`device.yaml` を変更しても、他端末へ影響しない。
7. 通常起動時にWeb UIとMT5ポートをLAN／インターネットへ公開しない。
8. 同一PC上の二つのコピーは異なる `device.id` と `web_port` により並行起動できる。