# 指示書 Phase 2-0-d-2: manifest V2・max_bytes 配線・検証録画による同期/rotation 実データ確認

**Version: 1.0 / 作成日: 2026-07-29 / 宛先: Codex / 発行: Claude(統括)**

---

## 0. 背景と本指示書の範囲

Phase 2-0-d-1 で depth 初期同期 state machine(depth_sync.py)を実装し、strict bridge 検証で
snapshot 接続を保証する経路を確立した(707 passed、残 fail 1件は本ライン無関係の Phase 5 UI 契約テスト)。

本指示書 (2-0-d-2) の範囲は以下に限定する。

1. manifest V2: 同期検証結果を manifest に記録する。
2. `DEPTH_HISTORY_MAX_BYTES` 配線: 検証録画で rotation 境界を意図的に発生させられるようにする。
3. **短時間の検証録画**を実施し、snapshot 接続 PASS と rotation 境界の pu 連続を実データで確認する。

**常時記録の有効化(運用開始)は本指示書では行わない。** 検証録画は短時間・限定条件のみ。
統括承認済み方針: 是正記録器を実データで一度検証してから本番投入する。

## 1. 報告書・成果物の出力先(厳守)

- 報告書: `ArchitectureRepository/00_Master/HEATMAP/Phase_2-0-d-2_manifest_録画検証報告.md`
- 変更対象: `Delta_Engine_Pro4web/src/acquisition/depth_history_recorder.py`(manifest V2)、
  max_bytes 配線に必要な config/環境変数読取箇所(Phase 2-0-c で報告済みの現状経路に従う)。
- 新規/更新テスト: manifest V2 と max_bytes のユニットテスト。
- 検証録画データ: 既存記録を破棄せず新規ディレクトリに保存。パスを報告書に明記。
- 検証スクリプトは Phase 2-0-b の `tools_p20b/verify_depth_history.py` を再利用してよい(read-only)。

## 2. 統制(厳守)

- 実装前に §4 の manifest V2 スキーマと max_bytes 配線方針で問題ないか計画を1度提示し、統括承認を待つ。
- **検証録画はライブ接続を伴う。これは「手動確認タスク」として扱う。** テストにライブ接続は使わない。
  録画実施のコマンドと時間・条件を報告書に明記し、テストコードからは呼ばない。
- 同一テスト・同一コマンドの失敗が2回連続したら停止し、原因切り分けのみ報告して指示を待つ。
- 1タスク完了ごとに報告し、勝手に Phase 2-1 へ進まない。
- 常時記録の恒久有効化(compose の `DEPTH_HISTORY_ENABLED` 恒久 true 化)は禁止。
  検証録画のためだけの一時有効化に留め、録画後に false へ戻すことを報告書で確認する。
- 既存未コミット差分(webapp/main.py、docker-compose.yml、tests/webapp/test_book_update.py、
  および 2-0-d-1 全体回帰で判明した index.html の別系統差分)は保護する。触れる必要が生じたら停止して報告する。

## 3. sandbox 制約への対応

既存追跡ファイルを `apply_patch` で直接編集できない場合は、変更を `.patch` として新規出力し
`git apply --recount` で適用する分岐を用いる。両対応で進め、いずれも失敗したら停止して報告する。
(2-0-d-1 では直接編集が成立したが、環境依存で揺れるため両対応を維持する。)

## 4. 実装設計

### 4.1 manifest V2

現行 manifest(SHA-256・record_count・byte_size・closed_reason 等)に、同期検証結果を追加する。

追加フィールド(すべて整数 ID・文字列・真偽値。float 禁止):

1. `schema_version`: manifest スキーマ版数(整数。V1 との区別用)。
2. 各同期確立イベントごとに1エントリを持つ配列 `sync_events`。各要素:
   - `epoch`: 正整数(起動=最初の epoch、各 gap resync で増加)。
   - `reason`: `"INITIAL_BOOK_SYNC"` または `"BOOK_RESYNC"`。
   - `snapshot_u`: 採用した snapshot の lastUpdateId(整数)。
   - `bridge_U` / `bridge_u`: strict 検証を通した bridge diff の U / u(整数)。
   - `sync_verified`: `true`(strict PASS のみ記録。FAIL は下記 `sync_failures` へ)。
   - `attempts`: 確立までに要した attempt 数(正整数)。
3. `sync_failures` 配列(SYNC_FAILED に至った場合。各要素に epoch・reason・failure_reason・attempts)。

manifest V1 で記録された既存データを壊さないこと(読み出し側が schema_version で分岐できるようにする)。
manifest 生成は depth_sync coordinator の返却値(DepthSyncAction)から組み立てる。coordinator が
板 state を持たない契約(2-0-d-1)を壊さず、記録器側で coordinator の verified 結果を受け取る経路にする。

### 4.2 max_bytes 配線

Phase 2-0-c で報告された現状の max_bytes 経路に従い、`DEPTH_HISTORY_MAX_BYTES`(環境変数)で
セグメントローテーションのサイズ上限を指定できるようにする。

- 未指定時は現行のデフォルト動作を維持(既存挙動を変えない)。
- 検証録画時に小さい値(例: rotation が数回発生する程度)を指定して境界を意図的に作る。
- 値は正整数としてパースする。float・負値・0 は拒否してエラーにする。

### 4.3 触らないもの

- depth_sync.py の coordinator ロジック(2-0-d-1 で確定)。返却契約は変更しない。
- orderbook.py。
- Replay pipeline。
- 常時記録の恒久有効化。

## 5. テスト(全 fixture 駆動、ライブ接続禁止)

1. manifest V2 が sync_events を正しく含む(fixture の coordinator 結果から生成)。
2. manifest V1 データが schema_version 分岐で壊れず読める(後方互換)。
3. `sync_verified: true` のみ sync_events に入り、SYNC_FAILED は sync_failures に入る。
4. `DEPTH_HISTORY_MAX_BYTES` の正整数指定でセグメントが分割される。
5. max_bytes に float・負値・0 を与えるとエラー。
6. manifest V2 の全フィールドに float 型が混入しない。

## 6. 検証録画(手動確認タスク)

実装・テスト完了・統括承認後に実施する。

1. `DEPTH_HISTORY_ENABLED` を一時 true、`DEPTH_HISTORY_MAX_BYTES` を rotation が数回発生する小さい値に設定。
2. 新規ディレクトリへ短時間(5〜10分程度)録画。既存記録は破棄しない。
3. 録画停止後、`DEPTH_HISTORY_ENABLED` を false へ戻す。
4. `verify_depth_history.py` を録画データに対して実行し、以下を確認して報告書に出力全文を貼付:
   - SNAPSHOT_CONNECTION: 全 snapshot が **PASS**(2-0-d-1 の是正が実データで効いていること)。
   - SEGMENT_BOUNDARY: 全境界が **PASS**(rotation が record を落とさず pu 連続)。
   - DEPTH_UPDATE_CHAIN_MISMATCH_COUNT: 0(セグメント内連続)。
   - FLOAT_NUMBER_LINE_COUNT: 0。
5. manifest V2 の sync_events / sync_failures を現物で貼付し、snapshot_u と bridge_U/bridge_u が
   verify スクリプトの SNAPSHOT_CONNECTION 実測と一致することを確認する。

**snapshot 接続が1件でも FAIL の場合、または境界 FAIL の場合は、修正せず停止して報告する。**
(是正が実データで効いていない可能性を意味するため、統括が原因を判断する。)

## 7. 報告フォーマット

- `[完了/失敗/停止] Phase 2-0-d-2 manifest_録画検証`
- 変更・新規ファイルのパス一覧
- manifest V2 スキーマの実装要点(ファイル:行番号)
- max_bytes 配線の実装要点(ファイル:行番号)
- 追加/更新テスト名と検証項目の対応
- 検証録画の条件(時間・max_bytes 値・保存先)と verify_depth_history.py 出力全文
- manifest V2 現物(sync_events / sync_failures)
- `DEPTH_HISTORY_ENABLED` を false へ戻したことの確認
- float 混入チェック結果
- 既存保護差分を触っていないことの確認
- 実行した全コマンドと結果(失敗コマンドも隠さず記載)

---

以上。報告受領後、統括が検証録画の実データ(snapshot 接続 PASS・rotation 境界 PASS)を確認し、
Phase 2-0 系(データ層是正)の完了を確定させた上で、Phase 2-1(再構築器設計)指示書を発行する。
