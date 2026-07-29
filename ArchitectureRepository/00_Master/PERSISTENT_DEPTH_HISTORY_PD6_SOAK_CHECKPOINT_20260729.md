# Persistent Depth History PD6 soak checkpoint

開始: 2026-07-29 08:18 JST  
承認: user instruction to proceed with next PD6 stage

Scope: 30-minute production-writer soak and retention safety observation. No purge, schema migration, or retention deletion is authorized.

Every 30 seconds collect health state, pipeline／Tape／gap／reconnect, depth-history file count／bytes／closed manifests／open parts, and free disk. Stop only on explicit user instruction or safety failure.

完了: 2026-07-29 08:48 JST

結果: 30分観測を完了。最終ヘルス GREEN、sequence gap 0、WS reconnect 0、pipeline exceptions 0、Tape dropped 0／pending 0／send failures 0、event lag 436ms、RSS 612MB。履歴は closed JSONL 10、manifest 10、open `.part` 1、全21ファイル・13,350,873 bytes、C: 空き 97,350,770,688 bytes。観測期間中のコンテナ異常ログは検出なし。purge／削除は実施していない。

判定: PD6 30分 soak PASS。未完了は長時間（24h）保持観測、保持期限／purge 実装、replay API、ブラウザ hydration のみ。再開位置は保持ポリシー確定後の PD7。
