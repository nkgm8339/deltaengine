# Phase 0 Capture Preflight Readiness

## Document control

- Audit ID: `DE-SEP-001-P0-003`
- Plan: `DE-SEP-001-RUN-1`
- Policy: `ISOLATION_POLICY.md` `v1.5-review`
- Captured UTC: `2026-07-23T07:29:27.471Z`
- Captured JST: `2026-07-23T16:29:27.471+09:00`
- Verdict: `READY_WITH_CRITICAL_USER_DECISION`
- Gate 0A-R: `NOT_REQUIRED_UNDER_CURRENT_RUNTIME_STATE`

## 1. Authorization boundary

ユーザーの`じゃーやるか`を、Plan 1、Gate 0A、audit ID `DE-SEP-001-P0-003`、提案済み外部保全先の
実行承認として記録した。製品source、config、元runtime、process、Git refs／indexは変更していない。

1M／observerの停止、再起動、checkpoint、migration、Phase 1以降の実装、service起動、EA配備、
注文、destructive削除は未承認であり実施していない。

## 2. Interrupted audit reconstruction

| Audit | 実測状態 | 扱い |
|---|---|---|
| `P0-001` | 16,899,649 bytesのmanifest 1件だけ | 未完了forensic evidence。変更・再利用禁止 |
| `P0-002` | 13 fileの途中成果物 | 未完了forensic evidence。変更・再利用禁止 |

P0-002記録上、`ONE_M_HISTORY.bundle`と`ONE_M_WORKTREE_FORENSIC.zip`はverify／restore PASSである。
runtime完全保全、Gate 0A-R提案、Gate 0B packageは未完成である。

## 3. Git and product state

- Outer repository HEAD: `c133792031dca308e01b6c4824facc283bec3426`
- 1M gitlink: mode `160000`, object `895a160c321f6d56d668b5a67774c89662242199`
- Outer `.gitmodules`: absent
- 1M HEAD／branch: `895a160c321f6d56d668b5a67774c89662242199`／`master`
- 1M status: modified 3、untracked 9。P0-002記録と一致
- 30M: 148 file、1,137,377 bytes、独立`.git`なし
- Phase 1: not started

## 4. External destination validation

Approved path:

```text
I:\マイドライブ\DeltaEngine_Preservation\DE-SEP-001-P0-003\
```

- 開始時にtargetは存在せず、上書きなしで新規作成した。
- drive rootからtargetまでの全componentにjunction、symlink、reparse pointなし。
- FAT32 read-write volumeでremote storage対応。volume account名は成果物へ記録しない。
- ACLは現在のWindows userだけにFullControlを明示付与。
- `PREFLIGHT_MARKER.md`のwrite、read、SHA-256取得に成功。
- Marker SHA-256: `16192246118790E73540ED23DED1E85BA3D1FBCC320D6A588BC7201A20F1EEA8`
- 空き容量: 13,375,188,992 bytes
- 現在の1M data: 56,944 file、1,068,559,074 bytes
- payload見積: 1,074,134,992 bytes
- archive、作業領域、復元展開、50%安全余裕込み必要量: 3,759,472,472 bytes
- headroom: 9,615,716,520 bytes
- Capacity verdict: `PASS`

第2回では、各外部artifactのlocal hash検証に加え、cloud-backed volumeへのwrite完了後に再readして
SHA-256を照合する。C:とのphysical disk identityはrestricted CIM権限で直接比較できなかったが、I:は
remote storage対応volumeとして確認できた。この制約を残存riskへ記録する。

## 5. Current processes and runtime activity

| PID | 所有 | 状態 |
|---:|---|---|
| 20356 | 1M uvicorn `127.0.0.1:8080` | process alive、pipeline task dead |
| 13760 | execution-cost observer | active |
| 19328 | latency collector PID file | stale、processなし |
| 18376 | latency watchdog PID file | stale、processなし |

14秒間、1Mの57,207 fileを前後比較した結果は次の通り。

- CHANGED: 3
- ADDED: 0
- REMOVED: 0

変更中file:

1. `data/execution_costs/quotes_go1_20260723_094459.csv`
2. `data/execution_costs/status.json`
3. `data/latency/webapp_brushup.stderr.log`

pytest temporary directoryのAccess Denied 6件は権限付きread-only確認で全て空だった。通常fileを含まず、
分類E候補として扱える。

## 6. Critical operational observation

`/api/health`は`RED`であり、pipeline taskは次の保存失敗後にdeadとなっている。

- OI Parquet temporary fileからhour fileへのatomic renameでWindows Access Denied
- DB／Parquetの最終mtimeは2026-07-23 03:05:23 UTC付近
- storage queue pending 0
- web processとobserverは生存

storage workerは例外時の`finally`でDuckDB writerをcloseする実装である。DuckDBの17秒前後SHA-256は
一致し、Parquet 56,888 file／224,469,382 bytesも件数、size、最新mtimeが不変だった。

これは分離preflightの変更対象外である。1Mの停止、再起動、修正は行っていない。

## 7. Live-safe capture method for Run 2

### 7.1 Capture file set

第2回開始時に通常file集合を再列挙し、その時点をcapture file-set boundaryとする。第1回のhash、size、
Git statusをbaselineへ流用しない。capture開始後に新規生成されたruntime fileはpost-boundaryとして別記録し、
開始時集合へ暗黙追加しない。

### 7.2 Source and stable data

- 分類A、B、Dはarchive前後のpath、size、SHA-256一致を必須とする。
- DuckDB、Parquet、閉じたreport／recordingはstable候補として前後hashを検証する。
- DuckDB directoryにWAL／sidecarはなく、DB本体と過去ZIPだけが存在する。
- Parquet配下に残存temporary／WAL fileは見つからなかった。
- DBは元fileをopenせず、外部復元copyだけでschema、主要table、読取り、件数、期間を検証する。

### 7.3 Active append-only files

observer CSVとwebapp stderr logはshared-read可能で、file増加中でも固定prefix SHA-256が5秒後に一致した。
第2回では次の方法を使う。

1. shared-readで現在lengthを取得する。
2. そのlength以前の最後のnewlineをcutoffとする。
3. cutoffまでを外部snapshotへcopyする。
4. source prefix hashをcopy前後に再計算する。
5. source prefix hash、copy hash、length、cutoff、取得時刻をmanifestへ記録する。
6. CSVはheaderと最終完全row、logは最終newlineを検証する。

これによりprocessを停止せず、後続appendと独立した完全prefixを保存できる。

### 7.4 Atomic JSON

observer statusは`.tmp`へ完全JSONを書いた後にatomic replaceする実装である。shared-readでbytesを取得し、
JSON parse、SHA-256、`updated_at`、row countを検証した単一versionをsnapshotとする。

### 7.5 Gate 0A-R fallback

現在はGate 0A-R不要。ただし第2回開始時に次のいずれかがあれば、該当captureだけを止めて再提案する。

- DuckDB／Parquet write再開または前後hash不一致
- active fileのshared-read失敗
- 固定prefix hash不一致または非append変更
- atomic JSON parse失敗がretry後も継続
- 未知writer、新規WAL／sidecar、説明不能なruntime file

## 8. Decision required before Run 2

技術的には現在状態を停止なしで完全保全できる。ただし1M pipelineはすでにRED／deadである。
ユーザーは第2回開始前に次のどちらかを選ぶ必要がある。

1. 現在のRED状態をそのまま時点原本としてcaptureし、運用障害をbaselineへ明記する。
2. 分離作業とは別に1Mを修復し、修復後の新しい時点をP0-004以降としてpreflightし直す。

どちらを選んでもP0-001、P0-002、P0-003既存成果物を上書きしない。

## 9. Run 2 exact start sequence

1. ユーザー判断とRun 2承認をcheckpointへ記録する。
2. Phase 0成果物と外部markerのhashを再確認する。
3. Git、process、health、file集合、data sizeを再測定する。
4. live-safe条件を再判定する。
5. capture前hashからA～C archive、復元検証、capture後hash、最終manifestまで同一回で完結する。
