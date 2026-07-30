# Bookmap系ヒートマップ開発 指示書
**Version: 1.5 / 作成日: 2026-07-29 / 最終更新: 2026-07-30 / 管理者: Claude(本チャット) / 承認者: お館様**

---

## 0. 本書の位置づけ

- 本書は開発の統制文書。Claude Code への指示は必ず本書のルールに準拠する。
- 更新は本チャットの Claude が行い、お館様の承認をもって確定する。
- 第1章は **CLAUDE.md に丸ごと追記する統制ルール**。第2章以降は計画・管理用。

---

## 1. Claude Code 統制ルール(CLAUDE.md追記用)

以下をプロジェクトの CLAUDE.md に追記すること。

```markdown
## ヒートマップ開発 統制ルール

### 停止条件(最優先)
- 同一テスト・同一コマンドの失敗が2回連続したら、修正リトライを停止し、
  原因の切り分け報告のみ行って指示を待つ。
- タイムアウト発生時は再実行禁止。以下の3分類で原因を報告する:
  ① データ取得待ち(API/WebSocket) ② 処理・描画の重さ ③ テスト側の制限時間設定

### テスト方針
- テストにライブ接続(取引所API/WebSocket)を使用することを禁止する。
- テストは必ず録画済みスナップショット(fixtureファイル)またはモックで行う。
- ライブ接続の動作確認は「手動確認タスク」として人間が実行する。
- 描画テストは小規模データ(価格ビン50×時間100程度)で行い、
  フルサイズ描画は成果物確認時のみ実行する。

### 実行統制
- 実装・変更前に計画(変更ファイル・変更内容・想定リスク)を提示し、承認後に着手する。
- 1タスク完了ごとに報告し、次タスクへ勝手に進まない。
- 探索的な試行錯誤(パラメータを変えて何度も実行等)は事前申告し、上限回数を決める。

### 報告フォーマット
- [完了/失敗/停止] タスク名
- 実行コマンドと結果(要点のみ)
- 次のアクション案(実行はしない)
```

---

## 2. プロジェクト概要

| 項目 | 内容 |
|---|---|
| 目的 | Bookmap 相当の板情報ヒートマップ(価格×時間×指値厚み)を自前実装し、CVD等と重畳可能にする |
| 対象銘柄 | BTCUSDT(Binance Futures 永続先物) |
| データソース | Binance Futures WebSocket `@depth`(既存接続を流用) |
| 技術スタック | DeltaEngine現行構成: Python/asyncio/FastAPI + DuckDB/Parquet + HTML/Canvas 2D + WebSocket配信 |
| 成果物 | ①板スナップショット録画(orderbook記録の有効化) ②ヒートマップ描画(Canvas) ③リアルタイム配信 |

**DeltaEngine既存設計との整合(遵守必須):**
- ADR-003: 単一ループ非同期モデル(asyncio、スレッド禁止)
- `float()`禁止: Decimal→str変換のみ
- ADR-011「全量記録の原則」: orderbook記録は`record_path`指定で有効化する既存設計に乗せる
- `@depth`ストリームはネット変化量のみ返す(追加と取消の分離不可)。ローカル板の再構築にはREST深度スナップショット+差分適用の標準手順が必要
- Replay/Liveパイプラインの二重構造: 両パスに同一変更が必要

---

## 3. フェーズ計画

### Phase 0: 現状調査(最初のタスク)= 完了
- 既存コードの棚卸し(ファイル一覧・各役割・現在の実装状態)
- 現在発生しているタイムアウトの原因特定(3分類のどれか)
- 報告のみ。修正はしない。

### Phase 1: データ層の分離 = 完了
- 板スナップショット取得を独立モジュール化
- 録画ファイル形式の定義(1行 = 生depth/snapshotイベント、NDJSON)
- 短時間の実データ録画 → テスト用 fixture として保存

### Phase 2: 描画層(静的)
- **Phase 2-0(データ層是正)= 完了**。詳細は §5 参照。
  - 2-0-a: PROJECT_MEMORY読取(Windows 1312回避)
  - 2-0-b: Phase 1記録物の現物提出・連続性検証(snapshot接続FAIL 2件を検出)
  - 2-0-c: 初期同期の現物調査(並行raceを特定)・是正計画
  - 2-0-d-1: depth初期同期state machine実装(strict bridge検証)
  - 2-0-d-2: manifest V2・max_bytes配線・検証録画(snapshot接続FAIL→PASSを実証)
- **Phase 2-1: 再構築器設計(次の着手対象)**
  - 録画データ → 板state再構築(OrderBookStateManager前提)
- **Phase 2-2: 描画器設計**
  - 再構築した板 → ヒートマップ静的描画
  - ダウンサンプリング実装(価格ビン集約・時間間引き)を必須とする
  - 描画時間の計測をログ出力(既存の失敗: x座標-185.25px、p95予算16ms超過を繰り返さない)

### Phase 3: リアルタイム化
- ライブ接続 + 逐次描画更新
- 接続断・再接続処理

### Phase 4: 拡張
- CVD重畳、約定バブル表示、大口指値ハイライト等
- 8パターン参照カード(CVD×Price×Delta)との連携検討
- 注記: 記録データは trade を含む複合記録のため、約定バブルの素材は同一ファイルに既存(2-0-b §3.1)

**原則: Phase 順に進める。前 Phase 完了・承認前に次 Phase に着手しない。**

---

## 4. タイムアウト対処標準

| 分類 | 症状 | 標準対処 |
|---|---|---|
| ① データ取得待ち | 接続・受信でハング | テストから排除しfixture化。ライブは手動確認へ |
| ② 処理・描画の重さ | 実行はされるが長時間 | ダウンサンプリング。データ量を先にログで確認 |
| ③ テスト側制限時間 | 処理正常・時間だけ超過 | タイムアウト値の妥当性を報告し承認後に変更 |

---

## 5. 進捗管理表(Claudeが更新)

| # | タスク | Phase | 状態 | 備考 |
|---|---|---|---|---|
| 1 | 指示書v1.0作成 | - | 完了 | 本書 |
| 2 | CLAUDE.mdへ統制ルール追記 | - | 完了 | 2026-07-29 |
| 3 | 現状調査・タイムアウト原因報告 | 0 | 完了 | 2026-07-29報告受領。完成主張は撤回された |
| 4 | 是正(文書無効化+git証拠保全) | 0.5 | 完了 | v1→v2方式変更。コミット`1ebdc7b`、63件 |
| 5 | PROJECT_MEMORY.md差分の検証・破棄 | 0.5 | 完了 | GO-H0〜H6/PD0〜PD6の未コミット完成主張を発見・破棄。パッチ保存済み(SHA-256: 110C107C...) |
| 6 | Phase 1 データ層設計・指示書作成 | 1 | 完了 | P1-0設計前提→P1-1実装→P1-1-b配線→P1-2/P1-3ライブ確認 |
| 7 | Phase 2-0-a PROJECT_MEMORY読取 | 2 | 完了 | Windows 1312をNET直接読取で回避。27,563 byte/439行受領 |
| 8 | Phase 2-0-b 記録物現物提出・連続性検証 | 2 | 完了 | snapshot接続FAIL 2件、pu連続、リポジトリ構造確定 |
| 9 | Phase 2-0-c 初期同期調査・是正計画 | 2 | 完了 | 並行race特定。strict同期state machine計画 |
| 10 | Phase 2-0-d-1 同期state machine実装 | 2 | 完了 | depth_sync.py新規。strict bridge検証。707 passed |
| 11 | Phase 2-0-d-2 manifest V2・録画検証 | 2 | 完了 | snapshot接続FAIL→PASS実証。34セグ/33境界PASS |
| 12 | Phase 2-1 再構築器設計・指示書作成 | 2 | 未着手 | 録画データ→板state再構築。次の着手対象 |
| 13 | Phase 2-2 描画器設計・指示書作成 | 2 | 未着手 | 再構築板→ヒートマップ静的描画 |

### Phase 2-0 系 完了記録(2026-07-30)

**到達点**: strict同期でsnapshot接続を保証し、rotationがrecordを落とさず、manifestが実データと符合する
全量記録器が確立した。描画層の土台となる「正しい板履歴」を現物で保証。

- **2-0-a**: AGENTS.md必須のPROJECT_MEMORY.md読取が`Get-Content`のプロセス生成でWindows error 1312。
  `[System.IO.File]::ReadAllText()`(NET直接読取、プロセス生成なし)で回避成立。27,563 byte/439行。
  重要発見: PROJECT_MEMORY記載コミット5件は`proposed-origin/master`にのみ包含され、Heatmapラインと
  共通祖先なし(別履歴)。PROJECT_MEMORYの記述をコード根拠にしてはならない。

- **2-0-b**: Phase 1記録物(2セグメント14,201行、float 0)を現物検証。
  検証スクリプト`tools_p20b/verify_depth_history.py`作成。セグメント内puチェーン全成立。
  **重大発見: snapshot接続条件`U <= u_snapshot+1 <= u`が2件ともFAIL**(欠落 約10,175/約14,300 update ID)。
  原因はorderbook.py:233-242のlenient受理と同根で、記録の再構築で欠落levelが誤値のまま残る。
  記録は trade 9,102行を含む複合記録(Phase 4約定バブル素材が同一ファイルに既存)。

- **2-0-c**: 現行初期同期はconnector/receiver/supervisorの**並行race**であることを現物特定
  (pipeline.py:1482-1498のtask生成順は購読barrier ではない)。統括の当初仮説(直列順序問題)を
  Codexが現物で否定。REST snapshot先着時にsnapshot直後diffと繋がらない窓が生じる。
  是正計画: strict bridge検証state machine、pre-sync diff全量記録(ADR-011)、板apply単一化(ADR-003)。

- **2-0-d-1**: `src/acquisition/depth_sync.py`新規。state machine
  (WAITING_FOR_FIRST_DEPTH→FETCHING→VERIFYING_BRIDGE→SYNCED、上限でSYNC_FAILED)。
  最初の有効depthをbarrierにし、`U <= u_snapshot+1 <= u`のbridge成立とpu連続を検証。
  板applyをmain consumer単一コルーチンに集約。pre-sync diffも全量記録。707 passed。
  統括側で検証器プロトタイプを実データ突き合わせし、FAIL→PASS判定の正しさを事前検算済み。

- **2-0-d-2**: manifest V2(schema_version/sync_events/sync_failures、V1後方互換loader)、
  `DEPTH_HISTORY_MAX_BYTES`配線(constructor>環境変数>64MiB、float/0/負値/bool拒否)、
  rotation物理close遅延でsync metadata同セッション格納。webapp/main.py・compose不変。
  80 passed、float 0。
  **検証録画(300秒、max_bytes=524288、34セグメント/28,084行)で snapshot接続 1/1 PASS、
  境界 33/33 PASS、chain mismatch 0、float 0、manifest実測突き合わせ全項目一致**。
  2-0-bのFAILが是正後にPASSへ転じたことを現物で実証。BOOK_RESYNC 0件は短時間録画のため正常。
  録画後`DEPTH_HISTORY_ENABLED=false`復帰確認。常時記録の恒久有効化は未実施(Phase 2-1以降で別途判断)。

### Phase 1 完了記録(2026-07-29)

- 新規記録器`DepthHistoryRecorder`実装(src/acquisition/depth_history_recorder.py)。取得層raw_recorderタップに接続。生depthイベント(U/u/pu)とsnapshot(u=lastUpdateId保持)を到着順・文字列価格のまま全量記録。ADR-011準拠
- writer設計: バッファ書込+1秒周期flush、fsyncはセグメントクローズ時のみ、サイズローテーション+SHA-256 manifest、単一ループ(スレッド不使用)、SafeRecorderで障害隔離(R5)、RecorderTeeでhook_capture併用
- 主要コミット: `f94822a`(記録器本体)、`a7f107d`(テスト閾値修正)、`28d656c`(配線)、`091b20c`(composeコメント復元)、`e358a0f`(RecorderTee.close)
- ライブ実証(P1-2): 約7分で11,975行記録、depth全量、float混入0、manifest一致。健全性GREEN、既存機能(板/tape/CVD)劣化なし
- クローズ確認(P1-3): 正常shutdown、最終セグメント`.part`残存なし、manifest全項目一致、closed_reason=close
- 検出・是正した欠陥3件(いずれも統括起因): テスト閾値ミス、composeコメント消去、RecorderTee.close欠如。すべて修正済み
- 注記: Phase 1完了時のsnapshot接続検証は未実施だった。2-0-bで検証を追加しFAILを検出、2-0-d系で是正した。統括の検証設計の網羅性の課題として記録

### Phase 0.5 追加確定事項(2026-07-29)

- PROJECT_MEMORY.mdの未コミット差分にGO-H0〜GO-H6、PD0〜PD6の一連の完成主張が発見された。Phase 0確定事実と矛盾するため証拠保存の上で破棄(パッチ: discarded_project_memory_diff_20260729.patch)
- 別件VWAP無断変更Git証跡文書(VWAP_GIT_EVIDENCE_SUBMISSION_20260729_V2.md)を受領。Heatmapライン一区切り後に分析着手予定

### Phase 0 確定事項(2026-07-29)

- タイムアウト真因: UIテストがEdge headlessで実WebSocket接続を待機(分類①)。統制ルールのライブ接続禁止で再発防止
- 現行Heatmapコードは土台として無条件継承しない。根拠: 描画p95 31.8ms/112.1ms(予算16ms超過)、x座標-185.25pxバグ、ADR-011違反(50段サンプリング)、ADR-003違反(毎フレーム同期write+fsync)

---

## 6. Phase 2-1 着手にあたっての確定前提(次セッション向け)

Phase 2-1(再構築器設計)の指示書を書く際、以下は現物確定済みの前提として使ってよい。

- **入力**: `data_05M/depth_history_raw/symbol=BTCUSDT/`(Phase 1記録)および検証録画
  `data_05M/phase2_0_d2_validation/.../depth_history_raw/`のJSONLセグメント + manifest V2。
- **スキーマ**: depthは`e:"depthUpdate"`,`U`/`u`/`pu`,`b`/`a`(文字列価格)。
  snapshotは`e:"depthSnapshot"`,`u`(=lastUpdateId),`_capture_reason`。
- **manifest V2**: `schema_version:2`、`sync_events`(snapshot_u/bridge_U/bridge_u/epoch/reason/attempts)、
  `sync_failures`。再構築器はmanifestの`sync_events`から検証済みbridgeを起点にできる。
- **既存資産**: `OrderBookStateManager`(orderbook.py:97、gap検出244-268)。snapshot+diff再構築の土台に使う。
  ただしlenient受理(233-242)を未検証diffの穴隠しに使わない(2-0-c/d-1で確立した契約)。
- **未判断事項**: 常時記録の恒久有効化(運用開始)。描画が実データを要する段で別途判断する。本タスクでは触らない。
- **保護対象(未コミット差分、精査前)**: webapp/main.py、docker-compose.yml、tests/webapp/test_book_update.py、
  webapp/static/index.html(別系統Heatmap UI差分)。Phase 2-1で触れる必要が生じたら停止・確認。
- **残置fail**: `test_dom_tape_fusion_ui.py`(Phase 5 UI契約テスト、本ライン無関係)。将来Phase 5側で別対応。

---

## 7. 未確定事項(要提供)

- 現在該当なし。Phase 2-1着手前に必要な現物は §6 に集約済み。

---

## 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 1.0 | 2026-07-29 | 初版作成 |
| 1.1 | 2026-07-29 | 対象銘柄・スタックをDeltaEngine現行構成に確定。DeltaEngine設計制約を追記 |
| 1.2 | 2026-07-29 | Phase 0報告受領を反映。Phase 0確定事項を追記 |
| 1.3 | 2026-07-29 | 是正完了・PROJECT_MEMORY.md差分破棄を反映。Phase 0.5確定事項とVWAP証拠文書受領を追記。Phase 1着手 |
| 1.4 | 2026-07-29 | Phase 1(データ層)完了を記録。記録器実装・配線・ライブ実証・クローズ確認、検出欠陥3件の是正を反映。Phase 2着手前 |
| 1.5 | 2026-07-30 | Phase 2-0系(データ層是正、2-0-a〜2-0-d-2)完了を記録。snapshot接続FAIL検出→strict同期state machine是正→検証録画でFAIL→PASS実証。進捗管理表を2-1/2-2粒度へ分割。Phase 2-1着手前提を§6に集約。Phase 0/1確定事項を圧縮 |
