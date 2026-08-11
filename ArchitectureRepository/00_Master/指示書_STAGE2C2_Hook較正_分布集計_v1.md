# 指示書: Stage 2C-2 DOM系Hook threshold較正（調査＋分布集計）

目的: 収録済みfull streamデータ（72時間分）をリプレイし、DOM系を含む全Hook候補の測定値分布を集計する。集計結果はレポートとして出力し、threshold値の決定はClaude (web)が行う。

**禁止事項**:
- hook_thresholds.yamlを変更しない（この指示書では分布集計のみ行い、threshold書き込みは次の指示書で行う）
- 収録データの削除・修正・truncateを行わない
- playbooks.yaml、UIを変更しない
- 稼働中のliquidation収録に影響を与えない

---

## Phase 1: コードベース調査（read-only）

較正に必要な仕組みを確認する。以下の各項目について、該当ファイル名・クラス名・メソッド名・行番号を報告する。

### 1.1 リプレイの仕組み

収録されたfull streamデータを読み込んでパイプラインに再投入する仕組みを調査する。

```
調査対象:
- src/ 配下にreplay、journal、captureに関連するモジュールがあるか
- JournalReplay クラス（Stage 2B報告書で言及）の場所、インターフェース、使い方
- 収録データのフォーマット（XZ圧縮frame、manifest）の読み出しAPI
- リプレイ時にHook検出器を走らせる方法（既存のテストやスクリプトから推定）
```

### 1.2 Hook検出器のインターフェース

Stage 2B-Dで実装された56 Hook候補の検出器がどう構成されているかを確認する。

```
調査対象:
- 各detector（A/C/D/E/F/G）のモジュール場所
- 検出器が測定値（candidate value）を生成する仕組み
- ThresholdBookとの連携方法（UNCALIBRATED時に何が起きるか）
- 検出器がパイプラインのどの段階で呼ばれるか
```

### 1.3 ThresholdBookの構造

```
調査対象:
- ThresholdBookクラスの場所とインターフェース
- hook_thresholds.yamlの読み込み方法
- UNCALIBRATED状態でのfail-closed挙動の実装
- threshold判定のロジック（パーセンタイルベースか、固定値か）
```

### 1.4 既存の較正ツール

```
調査対象:
- tools/ 配下にhook較正用のスクリプトがあるか
- tools/calibrate_refs.py、tools/calibrate_cvd.py のインターフェース（参考として）
- 較正結果をyamlに書き出す仕組みが既にあるか
```

### 1.5 収録データの構造

```
調査対象:
- data_05M/hook_observer/campaigns/stage2a_20260726_xz/full/ 配下のsessionの構造
- 各sessionのmanifest、frame、summary のファイル構成
- 1 frameに含まれるデータの種類（DOM snapshot、aggTrade等）
```

Phase 1の調査結果をレポートの冒頭にまとめる。

---

## Phase 2: 分布集計スクリプトの作成と実行

Phase 1の調査結果に基づき、以下の要件を満たすスクリプトを作成して実行する。

### 2.1 要件

- 収録済みfull streamの全session（29 session）をリプレイする
- リプレイ中に全Hook検出器（A01-A24、C03-C09、D06-D08、F01-F05、G01-G11）を走らせる
- 各Hookについて、測定値（candidate value）を全件収集する
- E01-E06はliquidation依存のため対象外（データなし）
- C09（liquidation absorption）も対象外

### 2.2 出力する分布統計

各Hookについて以下を計算する:

- Hook ID
- 標本数（count）
- min / max
- mean / median（p50）
- p5 / p10 / p25 / p75 / p90 / p95 / p99
- 標準偏差

### 2.3 出力形式

結果をmarkdownの表形式でレポートファイルに出力する。1行1 Hook。

追加で、標本数が100未満のHookを「標本不足」として別途リスト化する。

### 2.4 性能制約

- リプレイは稼働中のliquidation収録と同一コンテナで実行しない。ホスト側のPythonで実行するか、別コンテナで実行する
- メモリ使用量に注意する。917MBの圧縮データを全展開すると大きくなる可能性があるため、session単位で逐次処理する

### 2.5 スクリプトの配置

```
tools/calibrate_hooks.py
```

dry-run（集計のみ、yaml書き込みなし）をデフォルトとする。`--write`フラグは今回使用しない（仮に実装しても実行しない）。

---

## 出力

Phase 1の調査結果とPhase 2の分布集計結果を1つのレポートにまとめて以下に保存する:

```
ArchitectureRepository/00_Master/トリガー作成指示書群/HOOK_STAGE2C2_DISTRIBUTION_REPORT_20260730.md
```

ヘッダ:

```markdown
# Stage 2C-2 Hook測定値分布レポート
実行日時: （実行時のJST日時）
実行者: Codex
対象データ: stage2a_20260726_xz/full（全session）
```

スクリプト`tools/calibrate_hooks.py`もcommit対象とする。commitメッセージ:

```
feat(tools): add hook threshold calibration script (dry-run only)
```

リプレイ実行中にエラーが発生した場合は、エラー内容を記録して続行可能なsessionだけで集計する。全sessionが失敗した場合はPhase 1の調査結果のみ報告する。
