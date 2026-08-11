# DeltaEngine05M core backup restore note

この文書は、2026-08-02時点の現行coreをGoogle Driveへ保存するZIPの復元境界を示す。

## 収録範囲

- `Delta_Engine_Pro4web` のsource、WebApp、config、test、tool、script、build／compose定義
- `ArchitectureRepository` の正本文書、仕様、設計台帳、checkpoint
- repository rootの起動、復旧、agent／handoff文書
- Gitで未commitの現行source／test／文書を含む
- ZIP内の `MANIFEST_SHA256.txt` に収録fileのSHA-256を記録する
- ZIP内の `BACKUP_INFO.txt` に作成時刻、branch、HEAD、dirty状態を記録する

## 意図的な除外

- `.git` directory、stash、Git object／history
- raw market data、DuckDB、Parquet、runtime log、cache、temporary test artifact
- 既存backup ZIP、PDF、画像、screen capture、compiled binary
- 大型runtime preservation manifest／investigation evidence
- `.env`、credential、private key等の秘密情報

このZIP単体は市場データやGit履歴の完全backupではない。core sourceと設計正本を別環境へ
復元し、dependencyを再構築するための保存物である。

## 復元時の基本手順

1. ZIPを空directoryへ展開する。
2. `MANIFEST_SHA256.txt` と展開fileのSHA-256を照合する。
3. rootの `AGENTS.md` と `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` を全文読む。
4. `Delta_Engine_Pro4web/RESTORE.md`、`README.md`、compose／requirementsを確認する。
5. runtime dataとsecretはbackup外から明示的に用意し、いきなりLIVE発注へ接続しない。
6. testを実行し、保存時checkpointに記録された既知baselineとの差を確認する。

## 保存時のGit基準

- branch: `feature/footprint-dom-tape`
- HEAD: `7552bc3487a3539dca9c7830e92de7cca8884c4f`
- 現行worktreeはdirtyであり、このZIPはHEADだけでなく収録対象の未commit変更も含む。
