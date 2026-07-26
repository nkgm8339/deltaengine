# Replay契約 拒否試験 完了checkpoint

## 2026-07-27 JST Stage 2完了checkpoint

### 承認範囲

- お館様のStage 1承認書（Replay契約 拒否試験 Stage 1 設計提案）により、contract enforcer最小骨格と
  R1〜R8＋GP拒否試験を実装する。
- 契約の構造だけを試験する。runtime有効化、threshold較正、HookEvent解禁、注文は行わない。
- pushはお館様の指示があるまで行わない。

### 完了済み

- 新規隔離パッケージ `Delta_Engine_Pro4web/src/strategy_contract/` を追加。
  - `rejection_codes.py` / `events.py` / `variant_contract.py` / `enforcer.py` / `replay_driver.py`
  - enforcerに発注API無し。TERMINALは`OrderReadyHandoff`（LONG_READY/SHORT_READY）返却のみ（判定契約8）。
  - 正本FSM+binding CSVは読み取り専用ロード。
- 試験 `Delta_Engine_Pro4web/tests/strategy_contract/` を追加。
  - `test_replay_contract_golden_path.py`（GP対照基準）
  - `test_replay_contract_rejection.py`（R1〜R8）
  - `_helpers.py`（ユーザー提示variantのfixture）
- 対照表 `ORDER_FLOW_REPLAY_CONTRACT_REJECTION_MATRIX_V0_1_20260727.md` を作成。
- 各RejectReasonのenum docstring・`REASON_CLAUSE`・テスト内コメントに根拠条項を明記。

### 変更file

- `Delta_Engine_Pro4web/src/strategy_contract/__init__.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_contract/rejection_codes.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_contract/events.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_contract/variant_contract.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_contract/enforcer.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_contract/replay_driver.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_contract/__init__.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_contract/_helpers.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_contract/test_replay_contract_golden_path.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_contract/test_replay_contract_rejection.py`（新規）
- `ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_REPLAY_CONTRACT_REJECTION_MATRIX_V0_1_20260727.md`（新規）
- 本checkpoint（新規）

### 検証結果

- 新規試験: **27 passed, 1 skipped**（skip=R2-b UNDEFINED_BY_CANON、明示）。
- 全体回帰: **543 passed, 1 skipped**。既存516件は全件合格、影響0件（回帰0）。
- source code（既存）、config、runtime、UI、raw data、正本CSV/ポリシー文書の変更0。
- 発注権限0: enforcerに発注API無し。正本25,664 routeは全件`direct_order_authority=NO`・`runtime_route_enabled=NO`をR5-cで固定。
- production採用0、threshold変更0、HookEvent解禁0、注文0。

### Blockerの限定範囲

- blockerなし。
- 【未定義-1】cross-instance の`source_event_id`再利用は正本未定義のため`UNDEFINED_BY_CANON`として
  明示スキップ。正本側の将来更新事項として対照表§3に記録（正本文書は変更せず）。

### 未完了（別工程・ユーザー承認前に進めない）

- historical replayによるvariantの採用／棄却／統合。
- 採用variantのthreshold・時機・枚数・risk/execution gate較正。
- HookEvent解禁、Playbook選抜、check／LIVE移行。

### 次の再開位置

契約の構造は固定された。次はユーザー承認のうえ、historical replayで
ユーザー提示variantを含むvariantを実データ照合し、採用／棄却を判定する工程へ進む。

### push状態

- コミット作成済み。**pushはお館様の指示があるまで行わない。**
