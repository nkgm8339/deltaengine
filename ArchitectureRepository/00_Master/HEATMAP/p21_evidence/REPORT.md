# [完了] Phase 2-1着手前 現物収集

- 完了時刻: 2026-07-30 07:15:31 +09:00
- 承認範囲: 指定現物のコピー、構造/Git/test情報の収集、非ライブ全体pytest 1回、REPORT作成、ZIP作成。
- 完了済み:
  - 必須pathのread-only確認。
  - Git状態の基準値取得。
  - S1〜S3/S5のコピー（S4 loaderはS3内）。
  - 検証録画manifest 34件のコピー。
  - D2 full segment 2件のコピー。
  - Phase 1 manifest 2件のコピー。
  - 直接関連test 6件のコピー。
- 未完了: なし（本REPORT確定後に同folderをZIP化し、外部auditする）。
- 変更file: `ArchitectureRepository/00_Master/HEATMAP/p21_evidence/`配下の成果物だけ。
- 検証結果: コピー件数とD2元fileのbyte/行/SHA-256を確認済み。
- blocker: なし。
- 次の再開位置: 本REPORTを含む`p21_evidence/`をZIP化し、archive audit後に提出する。

## T1 checkpoint

- 実行: `python -m pytest -q -p no:cacheprovider`
- deselect: なし。fixture/mock/FakeConnect駆動であり、ライブ接続なし。
- 結果: `1 failed, 727 passed, 1 skipped in 85.44s (0:01:25)`
- failure: `tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation`
- 判断: 既知のPhase 5 UI契約fail。本収集タスクでは修正・再実行を行わない。
- 次の再開位置: inventory作成とGit基準値再比較。

## D2 暫定選定記録

- sync segment: `raw_depth.20260729T193154.046959Z.jsonl`
  - 527899 byte / 813行
  - SHA-256: `58048404F36A7FCB4A2487CB87D8C9A9F95386D624C3D4BCCB1C21B227747DD6`
- 直後segment: `raw_depth.20260729T193201.309417Z.jsonl`
  - 535833 byte / 1019行
  - SHA-256: `1AAF0643344A30338CFB8E7BCED642A83751C52A95008C488B91C93E13741A6D`
- 選定根拠: 最初のsegmentのmanifest V2にepoch 1 / `INITIAL_BOOK_SYNC`の
  `sync_events`があり、その直後にfilename時系列で連続するsegmentを境界確認用として選定した。

## 1. 収集対象と実パス

### S1〜S5

| ID | 元fileの実パス | ZIP内path | 結果 |
|---|---|---|---|
| S1 | `Delta_Engine_Pro4web/src/orderflow/orderbook.py` | `sources/Delta_Engine_Pro4web/src/orderflow/orderbook.py` | 収集済み |
| S2 | `Delta_Engine_Pro4web/src/acquisition/depth_sync.py` | `sources/Delta_Engine_Pro4web/src/acquisition/depth_sync.py` | 収集済み |
| S3 | `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py` | `sources/Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py` | 収集済み |
| S4 | S3内 `load_depth_history_manifest()`（85行付近） | S3と同一 | 別fileなし |
| S5 | `ArchitectureRepository/00_Master/HEATMAP/tools_p20b/verify_depth_history.py` | `sources/ArchitectureRepository/00_Master/HEATMAP/tools_p20b/verify_depth_history.py` | 収集済み |

### 指示pathとの差異

- S1: 指示の`src/acquisition/orderbook.py`は不存在。探索1回目で
  `Delta_Engine_Pro4web/src/orderflow/orderbook.py`を発見し、
  `OrderBookStateManager`定義（97行）を確認してこちらを収集した。
- S4: V1/V2 loaderはS3内にあるため、追加fileはない。
- S5: 実物はapp rootの`tools_p20b/`ではなくArchitectureRepository側にある。

### D1〜D3

| ID | 元path | ZIP内path | 収集内容 |
|---|---|---|---|
| D1 | `Delta_Engine_Pro4web/data_05M/phase2_0_d2_validation/20260730T043059/depth_history_raw/symbol=BTCUSDT/*.manifest.json` | `data/validation/manifests/` | manifest V2 全34件 |
| D2 | 同directoryの先頭2 segment | `data/validation/segments/` | full JSONL 2件 |
| D3 | `Delta_Engine_Pro4web/data_05M/depth_history_raw/symbol=BTCUSDT/*.manifest.json` | `data/phase1/manifests/` | Phase 1 manifest 全2件 |

D2はいずれも5MiB未満（527899 byte / 535833 byte）のため、
head/tail抽出ではなく元segmentを全文コピーした。

### D2選定根拠

対応するmanifest V2の`sync_events`:

```json
{
  "attempts": 1,
  "bridge_U": 11165393550921,
  "bridge_u": 11165393566438,
  "epoch": 1,
  "reason": "INITIAL_BOOK_SYNC",
  "snapshot_u": 11165393552876,
  "sync_verified": true
}
```

- sync segment: `raw_depth.20260729T193154.046959Z.jsonl`
- 直後の連続segment: `raw_depth.20260729T193201.309417Z.jsonl`
- 1本目のmanifestは`closed_reason: "rotate"`であり、2本目とのrotation境界を確認できる。

## 2. 構造情報

- C1: `structure/src_tree.txt`
- C2: `src/replay/` directoryは不存在。`structure/src_replay.txt`に記録。
  なお別物として`src/acquisition/replay.py`は存在する。
- C3: `structure/git_status_porcelain.txt`、`structure/git_diff_stat.txt`
- C4: `structure/git_log_oneline_5.txt`
- Git差分基準fingerprint: `structure/git_baseline_fingerprint.txt`

保護対象4fileはC3のstatus/stat確認だけに用い、コピー・編集していない。

## 3. T1 全体test

実行コマンド:

```powershell
python -m pytest -q -p no:cacheprovider
```

ライブ接続のdeselect: なし。
WebSocket/REST関連testはfixture、mock、FakeConnect、fake transportを使用する構成で、
取引所API/WebSocketへのライブ接続は発生しなかった。

末尾summary:

```text
1 failed, 727 passed, 1 skipped in 85.44s (0:01:25)
```

failure:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

既知のPhase 5 UI契約failureであり、本ラインとは無関係。
指示どおり修正・再実行を行っていない。timeoutなし。

## 4. T2 depth関連test

以下6件を相対pathを保ってコピーした。

1. `Delta_Engine_Pro4web/tests/acquisition/test_binance_rest.py`
2. `Delta_Engine_Pro4web/tests/acquisition/test_depth_history_recorder.py`
3. `Delta_Engine_Pro4web/tests/acquisition/test_depth_sync.py`
4. `Delta_Engine_Pro4web/tests/orderflow/test_orderbook.py`
5. `Delta_Engine_Pro4web/tests/test_book_resync.py`
6. `Delta_Engine_Pro4web/tests/test_live_pipeline.py`

保護対象`tests/webapp/test_book_update.py`はコピーしていない。

## 5. 収集物inventory

以下はREPORT自身を除く全payload fileの相対path・行数・byte数・SHA-256。
REPORTは内容確定後に外部auditし、ZIPのSHA-256とともに最終報告する
（REPORT内にREPORT自身のhashを埋める自己参照は行わない）。

| Evidence path | Lines | Bytes | SHA-256 |
|---|---:|---:|---|
| `data/phase1/manifests/raw_depth.20260729T110911.036557Z.jsonl.manifest.json` | 1 | 295 | `ABF5CAE10DED6CB2E8D2AEF999572CD3CD9CBF98505BAE85E356B079DDF3F4C4` |
| `data/phase1/manifests/raw_depth.20260729T113705.315567Z.jsonl.manifest.json` | 1 | 294 | `0CE9EDF6ED7FDF6A6BB8234ED968896D5AB616B5ACDDBF459E9213C9EBA9629B` |
| `data/validation/manifests/raw_depth.20260729T193154.046959Z.jsonl.manifest.json` | 1 | 522 | `3D8F5E97672ECB0A3FB832CBCDC0C9F62951A8107956F2CCDFD86804A5E7335D` |
| `data/validation/manifests/raw_depth.20260729T193201.309417Z.jsonl.manifest.json` | 1 | 356 | `F87B3CE5654D27A9A9D78A0A6CE5F226F02F00A60E2543FF53E4901EBC6BEAE9` |
| `data/validation/manifests/raw_depth.20260729T193207.936510Z.jsonl.manifest.json` | 1 | 355 | `0DAA47F9A084C19BFA4B6D5112F9901E2EBDF0EB67EF85C413353DE44AD424C7` |
| `data/validation/manifests/raw_depth.20260729T193215.790120Z.jsonl.manifest.json` | 1 | 355 | `DBCA7A05C48238D9751747B09C4601D375A1F08C137B104404B70733BBC013A2` |
| `data/validation/manifests/raw_depth.20260729T193226.297145Z.jsonl.manifest.json` | 1 | 355 | `C08EDB79023C85B9A72B8A785DD81BAB44A792AB6DE5F4FC03AEB67419327FF4` |
| `data/validation/manifests/raw_depth.20260729T193235.259351Z.jsonl.manifest.json` | 1 | 355 | `A2A0B7D289F07090B738A7CAF32CF1EB3F52C05ED5E805E4A2E0DA624E732DDE` |
| `data/validation/manifests/raw_depth.20260729T193243.737595Z.jsonl.manifest.json` | 1 | 355 | `F897BA3BB5080D654E89665934AE6DCED312502D6C82C414D40F7EF1CB041EEF` |
| `data/validation/manifests/raw_depth.20260729T193255.493715Z.jsonl.manifest.json` | 1 | 355 | `7168D0D494F4B9F889742C39BD08CDFA7397977024A07E244BF522E09F0767C4` |
| `data/validation/manifests/raw_depth.20260729T193303.935062Z.jsonl.manifest.json` | 1 | 355 | `989BD889A282B75F56B508F8F359C6DF002853A2ACC4920806EC779BEADB3E90` |
| `data/validation/manifests/raw_depth.20260729T193313.208341Z.jsonl.manifest.json` | 1 | 356 | `C3D44D20E0C2257CEA92B20BA8ECFA956CC79F417B0AC306A2599E321432C9CC` |
| `data/validation/manifests/raw_depth.20260729T193319.564627Z.jsonl.manifest.json` | 1 | 355 | `0204FC48ECE2BF19EF0BBFA29C0AF57B566DD0C41CFC41631A1E29F27C6E7EA5` |
| `data/validation/manifests/raw_depth.20260729T193327.357648Z.jsonl.manifest.json` | 1 | 356 | `4F0F73A86904C49C2915B1C8173E419C7B120A48C3AC976F30733136EDEFBF49` |
| `data/validation/manifests/raw_depth.20260729T193330.818457Z.jsonl.manifest.json` | 1 | 355 | `C34A723C240AD60407CF508352E8980FD8889B8F8FA649A17F8F3A44E4ED6272` |
| `data/validation/manifests/raw_depth.20260729T193341.396258Z.jsonl.manifest.json` | 1 | 355 | `DC21A67A7D6CC54288300B9EAF9C138C0F2FF2A5656015F7A77809DCA5E246A0` |
| `data/validation/manifests/raw_depth.20260729T193351.301390Z.jsonl.manifest.json` | 1 | 355 | `A681ADFEE6812ACD1F2349027C0C4DB41D50D54594CADCEABF40BB45A09F717D` |
| `data/validation/manifests/raw_depth.20260729T193359.580460Z.jsonl.manifest.json` | 1 | 356 | `36C80E9BA15865D34B5D381DF12E362BC77D31D08C758F657CDCC773DEDACB67` |
| `data/validation/manifests/raw_depth.20260729T193405.999303Z.jsonl.manifest.json` | 1 | 355 | `0B5D6B7A8B89BC892FF275ABFDB334F46AD051B3240B4A370069A45C715C1D6D` |
| `data/validation/manifests/raw_depth.20260729T193410.656550Z.jsonl.manifest.json` | 1 | 355 | `344DF0317B8C1176CB4D80973C2CBBA4BBD78144B21B23B32861F6196995D6F8` |
| `data/validation/manifests/raw_depth.20260729T193417.604225Z.jsonl.manifest.json` | 1 | 356 | `D0AFD646C91EABBA6212D8A1A20689604CCC9D5C74672D8213DE682A6D9EAF90` |
| `data/validation/manifests/raw_depth.20260729T193424.030018Z.jsonl.manifest.json` | 1 | 355 | `97CD66CE2948E6C175803B31A4D229DD1AE8FB86A10A68704D88CC09A76EFAF4` |
| `data/validation/manifests/raw_depth.20260729T193431.811899Z.jsonl.manifest.json` | 1 | 355 | `F0CA5D4C650B0195AA3CBE5405CDABBE4E03ED164C55B96950CFDC45A743418F` |
| `data/validation/manifests/raw_depth.20260729T193440.224873Z.jsonl.manifest.json` | 1 | 355 | `37AA443C126F1147962ABD477F3C540B6EF1A4EDBF0C194BD33604873913DB08` |
| `data/validation/manifests/raw_depth.20260729T193451.435394Z.jsonl.manifest.json` | 1 | 355 | `F921CDB5431A9661AB3BC077EC7BE6F7312923B8554AF062A86AC4D999BAD174` |
| `data/validation/manifests/raw_depth.20260729T193501.543033Z.jsonl.manifest.json` | 1 | 355 | `1EEC7CA6B901095184B8F00EDC4D3F787D7F25729BFC4CEA782CAD2F802C1E6E` |
| `data/validation/manifests/raw_depth.20260729T193512.150766Z.jsonl.manifest.json` | 1 | 355 | `B49E7D99FCCCB221F4E5B1D6BDECEB1E878B903212E42B223F9E48C58C41C349` |
| `data/validation/manifests/raw_depth.20260729T193522.699724Z.jsonl.manifest.json` | 1 | 355 | `D29560C26CB0E02A7B0DCDFDA68E7E41188E16ACDDA065C967FDAE5A8CF8FA2D` |
| `data/validation/manifests/raw_depth.20260729T193534.949801Z.jsonl.manifest.json` | 1 | 355 | `F2C4F84B305CA24FF0A40C119A1B2C7A91CE46B232475E9743F33B8E10201685` |
| `data/validation/manifests/raw_depth.20260729T193549.278358Z.jsonl.manifest.json` | 1 | 355 | `9661F706464D7C9B62115FD26CDAE92340F58D785CFA51E3389223CF44107BF6` |
| `data/validation/manifests/raw_depth.20260729T193602.913092Z.jsonl.manifest.json` | 1 | 355 | `D5D991A8F1D3288DBB5FC33E16721D9B43B5DE7C3A4689610177F31609D54D6F` |
| `data/validation/manifests/raw_depth.20260729T193615.710341Z.jsonl.manifest.json` | 1 | 355 | `29BFB1A70D915E54D8CFC012BBFC1F077F809FAF3F06C84A5DACEF3629D30166` |
| `data/validation/manifests/raw_depth.20260729T193623.912893Z.jsonl.manifest.json` | 1 | 355 | `74704F526521A209049403B05F0C7C38DC8A7727515E83BAC9F4D7C708E0C9AF` |
| `data/validation/manifests/raw_depth.20260729T193630.783699Z.jsonl.manifest.json` | 1 | 355 | `5A1ADE65F904CEB5ED1700B49B92F7F1BB61EA5A7A9ED318BC66EE81008C47E4` |
| `data/validation/manifests/raw_depth.20260729T193639.671392Z.jsonl.manifest.json` | 1 | 355 | `E425C1D49F2A2C2039F61FAC9DAAF55CE5520C713952A5C3129E2E666C66C3BC` |
| `data/validation/manifests/raw_depth.20260729T193652.336710Z.jsonl.manifest.json` | 1 | 353 | `58FE457A66661E2D923DF056A204C4CB955365C554A725C988DFEFB8BDD9EEF5` |
| `data/validation/segments/raw_depth.20260729T193154.046959Z.jsonl` | 813 | 527899 | `58048404F36A7FCB4A2487CB87D8C9A9F95386D624C3D4BCCB1C21B227747DD6` |
| `data/validation/segments/raw_depth.20260729T193201.309417Z.jsonl` | 1019 | 535833 | `1AAF0643344A30338CFB8E7BCED642A83751C52A95008C488B91C93E13741A6D` |
| `sources/ArchitectureRepository/00_Master/HEATMAP/tools_p20b/verify_depth_history.py` | 253 | 8459 | `E394997B6883C2E4DE69073943F1C55F982A6128565F1F0134732268C6C36EE3` |
| `sources/Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py` | 348 | 12886 | `5BB3C42F110720E6A64DB0F63E0CAC91460EE9BB98377761BED2EAC2F408BE7A` |
| `sources/Delta_Engine_Pro4web/src/acquisition/depth_sync.py` | 383 | 14264 | `131B0B773712E983179789316E8562DDDC41B7330D8DF23330FF5B871DEBB576` |
| `sources/Delta_Engine_Pro4web/src/orderflow/orderbook.py` | 290 | 11295 | `291D46612AEBE09CD4B7A60E46F30CB9E8602FDD53817A3D01170F669D424C05` |
| `structure/git_baseline_fingerprint.txt` | 14 | 559 | `B27B45A7E0BDB104912D59623B6ED657079DC20F6C7F1966A2DCE0E6C28E42D3` |
| `structure/git_diff_stat.txt` | 21 | 1126 | `F182411E102A63D9B689852098C091E505F96FED31E020D948E2C907BB698D6B` |
| `structure/git_log_oneline_5.txt` | 6 | 396 | `30A81D3C936A8122D10AD21C5C914BD0535DE48F4234F2DC21BC60830E0063D0` |
| `structure/git_status_porcelain.txt` | 63 | 4216 | `04897F27559F944F86D4B8797BAC3888456DF78743AFA54FF2C5E866F591131E` |
| `structure/src_replay.txt` | 8 | 274 | `614EB742786E0BD4B5852A6A2FE0A749A5B39FF381F3FA7F9A3C62D4404FCDD0` |
| `structure/src_tree.txt` | 100 | 5205 | `F13AC0A0B52ACE4942DBD43505276C4F2E28715D308E8D14D3FDAEB9BBB05BDC` |
| `tests/Delta_Engine_Pro4web/tests/acquisition/test_binance_rest.py` | 269 | 10608 | `93BFD9312A290E94C54C501E002C42AE4D5E9BBB335CBB0CAC3CC5411B078C85` |
| `tests/Delta_Engine_Pro4web/tests/acquisition/test_depth_history_recorder.py` | 373 | 12345 | `74A4E2AE02E1B9567553F1043A8017013857184807D003EC1E5BE92DB047882C` |
| `tests/Delta_Engine_Pro4web/tests/acquisition/test_depth_sync.py` | 278 | 9120 | `7398261143EF1BEDABFDE4050874742F03C62A2B8DAF73514881DF5076849F2F` |
| `tests/Delta_Engine_Pro4web/tests/orderflow/test_orderbook.py` | 245 | 8263 | `421AA84713CAFF538CFF4BF997E6B4547D277B785A76BE7420A0EF88A6441C5A` |
| `tests/Delta_Engine_Pro4web/tests/test_book_resync.py` | 219 | 6327 | `678D7EAC7B22A1E585964B26ACCA2C975EF18F1F9FB6FACB26B0F94F7BBAB280` |
| `tests/Delta_Engine_Pro4web/tests/test_live_pipeline.py` | 666 | 23468 | `49D3713B9B1E3C304605C05FEE4ACA8C76F283A4D5426BD5061B020F9D73EAE6` |
| `tests/depth_related_test_files.txt` | 11 | 461 | `D7A0DD9713FB801AA4BD1649D307CCDCA01B0F59A456561DCFC3AAAADC173F17` |
| `tests/pytest_summary.txt` | 20 | 613 | `4C57055AD9B24F57626DFBA6BA2CF612E23D30DF219E3DD4111F584C475BF35E` |

## 6. 実行コマンドと結果

1. Git root・必須path・manifest loader・testのlive indicatorをread-only探索 — 成功。
2. S1探索1回目: `rg --files src | rg orderbook.py`とclass検索 — 実パスを発見。
3. 成果物path衝突確認 — folder/ZIPとも不存在。
4. `git status --porcelain=v1 -uall`、`git diff --stat`、`git log --oneline -5` — 成功。
5. manifest/segment件数とsync manifest探索 — 成功。
6. 指定成果物directory作成と`Copy-Item`によるコピー — 成功。
7. D2元fileの行数・byte数・SHA-256取得 — 成功。
8. 構造/Git/checkpoint文書作成 — 成功。
9. `python -m pytest -q -p no:cacheprovider` — exit 1。
   既知のPhase 5 UI契約test 1件のみfail。727 passed、1 skipped。再実行なし。
10. 全payloadの行数・byte数・SHA-256算出 — 成功。
11. ZIP作成＋archive audit初版 — PowerShell ParserErrorで失敗。
    mismatch表示用文字列の`$entryName:`が不正な変数参照と解釈された。
    parser段階の失敗でありZIPは未生成。同一コマンドは再実行せず、
    format演算子を使う別コマンドへ切り替えた。
12. format演算子へ修正した別コマンドでZIP作成＋archive audit — 成功。
    folder 57 file、ZIP 57 file entry、byte/SHA-256 mismatch 0。
    REPORTへ本結果を追記後、REPORT entryをarchiveへ同期して最終auditする。

同一コマンド2回連続失敗、timeout、ライブ接続は発生していない。

## 7. 発見事項

- 指示pathと異なるのはS1とS5。正しい現物pathは§1に記載。
- `src/replay/` directoryは存在しないが、`src/acquisition/replay.py`は存在する。
- 現在のHEAD直近5件はPhase 1 line（`e358a0f`〜`f94822a`）。
- T1の唯一のfailureは指示書記載済みのPhase 5 UI契約failure。
- PROJECT_MEMORY.mdは収集・参照・報告根拠に使用していない。

## 8. 次のアクション案（実行しない）

統括が本ZIPの現物だけを根拠に、Phase 2-1再構築器の設計・実装指示書を作成する。
本収集タスクではPhase 2-1本体、常時記録有効化、既存code修正へ進まない。

## 9. ZIP前最終監査

- 監査時刻: 2026-07-30 07:13:54 +09:00
- approved output 2pathを除くstatus行数: 70
- status SHA-256:
  `7221C4BB1B02C5C7D196EED5DB049713EB9E693DBC9DD4E8119A16B4D1A4C472`
- baseline status SHA-256: 同値
- `git diff --stat` SHA-256:
  `59259F9599FED4DC0E5678C494F77BF771BF0AED81DA5006126A6A0F34CC2036`
- baseline diff stat SHA-256: 同値
- 判定: PASS。元リポジトリへの新規変更なし。
- blocker: なし。
- package初回audit: folder 57 file / ZIP 57 entry / mismatch 0。
- 次の再開位置: 本REPORT entryをZIPへ同期し、全entry最終auditを行う。
