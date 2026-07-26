# Hook Detector / Trigger Observe — Stage 2A 完了報告

報告時刻: 2026-07-26 13:40 JST
対象: 承認済み `HOOK_DETECTOR_TRIGGER_OBSERVE_DESIGN_PROPOSAL_20260726.md` Stage 2A
状態: **Stage 2A完了、append-only収録中、次段階未着手**

## 1. 結論

Stage 2Aの契約、収録、独立保存、replay基礎、既存Hook adapter、optional pipeline tapを
実装・試験・限定配備した。

- 既存Flow Price Responseの分類、3段チャート、既存UIの動作は変更していない。
- 既存DB、Parquet、JSONLその他の市場記録は削除・修正・上書きしていない。
- 全88 Hookは初期状態 `UNCALIBRATED`。発火件数は0である。
- `PROVISIONAL`、manifest hash不一致、quality不正もfail closedで発火しない。
- `playbooks.yaml`は`OBSERVE`固定、`execution_enabled: false`、Stage 2Aでは空である。
- Flow単体発注、playbook発注、LIVE注文への接続はない。
- raw収録は既存market pipelineから独立したbounded queueへcopyするだけで、
  capture側例外はmarket pipelineを停止させない。

Stage 2B以降はユーザー確認前に開始しない。収録だけはbackgroundで継続する。

## 2. 最低収録期間の見積もり

日数だけで較正可とは判定しない。固定日数、manifest品質、side別標本数のすべてを満たした
Hookだけを較正対象にする。固定期限で条件未達なら自動延長せず、そのHookを
`UNCALIBRATED`のまま報告する。

### 2.1 DOM分布

最低収録期間は **連続72時間（3日）** とする。

現在の期限:

- 開始: 2026-07-26 04:19:39 UTC
- 終了: 2026-07-29 04:19:39 UTC

根拠:

1. 100ms depth差分は理論上72時間で約2,592,000観測となる。
2. P99.5なら約12,960、P99.9でも約2,592の上側観測位置を持ち、初期分位の数値解像度を
   得られる。
3. 72時間でAsia、London、New Yorkの各sessionを3巡し、一時間帯だけの板分布へ固定しない。
4. UTC日別quantileを作り、pooled値だけでなく日別median、IQR、min/maxを比較できる。
5. 設計提案どおり3日未満は`PROVISIONAL`に留める。

72時間に加えて必要な品質・標本gate:

- valid DOM coverage 95%以上
- replay対象のvalid depth diff 2,000,000件以上
- 少なくとも3つのUTC日binが各18時間以上のvalid coverageを持つ
- Snapshot後の初回diffが `U <= lastUpdateId + 1 <= u`
- 以後のdiffが `pu == previous u`、または同等の連続条件を満たす
- queue drop 0、writer error 0、disk guard reject 0
- A17-A20、A23-A24等のepisode型はside別eligible episode 100件以上

上記episode標本数を満たさない個別Hookは、72時間が完了しても発火解禁しない。

### 2.2 清算分布

最低収録期間は **連続14日** とする。

現在の期限:

- 開始: 2026-07-26 04:19:39 UTC
- 終了: 2026-08-09 04:19:39 UTC

根拠:

1. liquidationはDOMより疎でcluster性が強く、3日では静穏相場だけを拾う危険がある。
2. 14日なら平日・週末を含む2つのweekly cycleを観測できる。
3. E01/E02のside別単発分布、E03/E04のactive 1秒window分布、E05/E06の条件付きepisodeを
   分離できる。
4. 現行200件memory bufferは閾値生成に使用せず、今回のappend-only履歴だけを使う。

14日に加えて必要な品質・標本gate:

- valid capture coverage 95%以上
- normalized `forceOrder` 4,000件以上
- long liquidation、short liquidation各1,000件以上
- side別active cascade window 250件以上
- E05/E06およびC09の条件付きeligible episode各30件以上
- 非正値、非有限値、side不正を除外し、raw `E`と`o.T`を保持
- queue drop 0、writer error 0、disk guard reject 0

2026-08-09の固定期限で不足した場合は自動延長しない。E系/C09を
`UNCALIBRATED`のままにし、実件数と不足量を報告して次の判断を求める。

## 3. 実装内容

### Hook共通契約

- `HookCandidate`、`HookThreshold`、`HookEvent`
- source / received / available / detectedのUTC時刻契約
- directionは観測上の意味だけで、注文命令ではない
- 全88 Hook registry
- A17-A20は名称・定義とも`SUSPECTED`
- calibration status、quality status、manifest hash照合
- 決定論的`hook_event_id`、duplicate suppression

### 既存観測adapter

- B01-B08、B11-B12、B15-B16、B19
- C01-C02
- D01-D05。既存Flow stateを再計算せず、state transition edgeだけを変換
- G12
- H04

これらはcandidateを作る独立adapterであり、既存検出器やWebApp payloadを変更しない。

### append-only raw journal

- UTC時間単位のsession固有segment
- exclusive create。既存pathを上書きしない
- full stream: REST Snapshot、全depth diff、trade、forceOrder
- liquidation stream: forceOrderだけを14日間別収録
- receipt time、arrival sequence、record typeを保存
- REST Snapshotは`DEPTH_SNAPSHOT`として分類し、`INITIAL_BOOK_SYNC`／`BOOK_RESYNC`理由を
  auxiliary rawだけへ付加。legacy recorderのpayloadは変更しない
- queue gap、disk guard、writer error、segment hash、件数をmanifest化
- graceful close時だけvalid summaryを作成
- summaryなしsessionは`INVALID_FOR_REPLAY`としてreplayが拒否
- 1GiB free-space guard
- 固定deadlineはcampaign metadataへ永続化し、restartで延長しない
- XZ preset 6。既存gzip sessionはvalid summary付きで保持

### 独立保存とreplay

- Hook専用append-only Parquet background storage
- 既存Parquet/DuckDB tableを変更しない
- gzip/XZ両対応のdeterministic replay skeleton
- SHA-256、segment件数、sequence連続性、session validityを検証

### 稼働系接続

- `LivePipeline.run_async(raw_recorder=None)`としてdefault無効
- legacy `record_path`の件数・挙動を保持
- auxiliary recorder例外をmarket pipelineから分離
- WebAppは明示環境変数がある稼働containerだけでcaptureを開始
- `/api/stats`へcampaign、deadline、accepted/persisted/drop/errorを追加

## 4. 試験結果

### 対象試験

XZ最終実装後:

- Hook契約
- 未較正／暫定／hash不一致fail closed
- DOM同期quality
- Flow transition adapter edge
- append-only XZ round-trip
- invalid session拒否
- Hook専用Parquet
- optional tap
- tap例外時の既存pipeline継続
- 既存LivePipeline、Web API

結果: **36 passed in 7.01s**

### 全体回帰

初回全体suite: **491 passed、1 failed、135.21s**

唯一の失敗は、作業前からdirtyだったUIと既存OI説明testの一時的不一致だった。Hook、
pipeline、storage、API関連の失敗は0。その後の並行UI更新後、当該testだけを再実行し
**1 passed in 0.08s**を確認した。並行UI fileは本作業で編集していない。

### 性能

XZで20,000 eventを連続投入:

- enqueue: 95,689 event/s
- mean: 10.1 us
- p50: 5.7 us
- p95: 13.7 us
- p99: 26.8 us
- full persisted: 20,000 / 20,000
- liquidation persisted: 100 / 100
- queue drop: 0
- writer error: 0
- 圧縮: 5,317,787 bytes → 181,612 bytes（3.42%）

実運用の100ms depth経路に対し、enqueue p99は0.027msである。圧縮とfile I/Oはbackground
writerが担当する。

## 5. 配備・現在状態

限定image:

- `deltaengine_05m-deltaengine-clone:stage2a-20260726`
- image ID: `sha256:11bfb235bbb4...`

配備はStage 2A runtime fileだけを重ねた限定imageで実施した。並行UI更新を検出したため、
recreate直前にhost、running container、staged imageのUI SHA-256がすべて
`4c957529755d...`で一致することを確認した。

2026-07-26 13:39 JST:

- `/api/health`: GREEN
- pipeline exception: 0
- book gap: 0
- event lag: 108ms
- full current session: 463 accepted / 463 persisted
- pending: 0
- queue drop: 0
- writer error: 0
- liquidation stream: accepting
- C: free: 6,771,744,768 bytes
- graceful closed XZ session summary: 2件
- LIVE注文操作: 0

Docker/WSL停止前のXZ sessionはsummaryなしのため無効sessionとして保存した。削除・修正せず、
較正入力から除外する。復旧後sessionは同じcampaign deadlineを引き継いでいる。

## 6. 容量対処

14日収録を止めないため、明示承認のもと次だけを回収した。

- 24時間超かつ未使用のDocker build cache: 11.05GB
- 再生成可能なpytest/test_tmp directory 44個: 1.084GB

市場記録、source、稼働image、Parquet、DuckDB、manual JSONLは削除していない。
pytest artifactはtest再実行、build cacheはimage再buildで再生成できる。

`Optimize-VHD` Fullは管理者権限不足で拒否され、VHD内容は変更されなかった。ただし
Docker/WSLの正常停止・再開で削除済みsparse領域がhostへ返り、C:空きは約2.7GBから
約6.8GBへ増加した。1GiB guardは維持する。

## 7. 次の工程

ユーザー確認後にだけStage 2Bへ進む。収録完了を待つ必要はない。

Stage 2Bでは収録をbackground継続しながら、A01-A24、C03-C09、D06-D08のdetector基礎を
実装・synthetic testする。続く承認済み順序でE/F/Gを進め、DOM 72時間完了時に閾値生成、
清算14日完了時にE/C09閾値生成を行う。

T01-T50のうち46型の宣言・validationは後続Stage 3で行う。T17/T34/T35/T36は
B14/B09/B10/B13不足のため、その実装後まで搭載しない。全型は引き続き`OBSERVE`固定である。
