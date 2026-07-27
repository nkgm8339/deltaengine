# Ingestion Adapter 骨格（代表1型 condition key）完了checkpoint

## 2026-07-27 JST Stage 2完了checkpoint

### 承認範囲

- お館様のStage 1承認書により、MarketStateSnapshot → Tier A condition snapshot の写像層を実装する。
- Tier A のみ。Tier B（STRATEGY_SPECIFIC 合成FLAG）は範囲外（documented gap）。
- Live/detector 直結せず正規化 snapshot 経由。既存検出器・既存strategy_engineファイルは変更しない。
- 閾値ハードコードなし（adapterは生量のみ、閾値はCalibrationBook経由）。
- pushはお館様の指示があるまで行わない。

### 完了済み

- 新規サブパッケージ `Delta_Engine_Pro4web/src/strategy_engine/ingestion/`。
  - `market_state.py`: `MarketStateSnapshot` + `TimeSample` / `BookLevel`（read-only、source非依存）。level列はbest-first、系列はmonotonic time sample。欠測は空列で表現。
  - `condition_adapter.py`: `IngestionAdapter.to_conditions(snapshot) -> {condition_key: Decimal}`。fail-closed（素材不足のkeyは出さない）。
- 出力（Tier A）:
  - adapter計算: `cvd_change_5s` / `cvd_slope_5s`（CVDサンプル窓）、`bid/ask_wall_concentration_top10` / `distance_to_nearest_bid/ask_wall`（book levels）、`open_interest_change_5m` / `open_interest_pct_change_5m` / `price_oi_joint_state_5m`（OI＋price）。
  - 素通し（pre_aggregated）: `bid/ask_refresh_count_1s`、`bid/ask_pull_ratio_1s`、`up/downward_progress_ticks_1s`、`buy/sell_no_progress_ratio_1s`。
- 出力は既存 `PredicateObservation.conditions` にそのまま入り、実evaluatorが消費する。

### documented gap（正本側/将来工程の記録）

- **Tier B 合成FLAG は未生成**: `flow_price_divergence_active`, `bid/ask_absorption_like_active`, `upside/downside_breakout_attempt/failure/follow_through`, `bid/ask_passive_defense_holding/failed`。
  - これらは Tier A ＋ location ＋ price response の合成状態であり、**composite synthesis 層**（将来工程）が必要。
  - 代表1型の反証route（downside_breakout_follow_through 等）はTier Bのため現状snapshotに現れず、evaluatorはfail-closedで「反証なし（veto=False）」と扱う。runtime有効化0の現段階では安全。実データで反証を効かせるには composite synthesis 層が前提。
  - 代表1型の9 classはすべてTier A候補routeを持つため、Tier Aのみで arm→advance×4→terminal を通せる（I6で実証）。
- **pre-aggregated の本計算は未実装**: refresh/pull（DEPTHイベント計数）、progress/no_progress（price×tape秒次計数）はイベント列再構築が必要。将来のreplay/detector統合工程で MarketStateSnapshot を埋める producer 側に実装する。
- **price_oi_joint_state_5m のENUM数値符号化**: `condition_adapter.JOINT_STATE_CODES`（FLAT=0 / UP_UP=1 / UP_DOWN=2 / DOWN_UP=3 / DOWN_DOWN=4）。ENUMをDecimal condition値として扱うための本工程の符号化であり、正本ENUM定義の変更ではない。

### 変更file

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/__init__.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`（新規）
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`（新規）
- `Delta_Engine_Pro4web/tests/strategy_engine/test_ingestion_adapter.py`（新規）
- 本checkpoint（新規）
- 既存 strategy_engine / strategy_contract ファイルは無変更。

### 検証結果（Stage 2完了条件）

1. I1〜I6 全件合格（新規 **8 passed**）。
2. R-a: strategy_engine 既存23件維持（合計 **31 passed**）。
3. R-b: Replay契約拒否試験 **27 passed, 1 skipped** 維持。
4. R-c: 既存516件 全件合格（回帰0件）。
5. 全体回帰: **574 passed, 1 skipped**（＝既存516＋contract 27/1skip＋engine 31）。
- 既存検出器・`strategy_contract`・`strategy_engine`既存ファイル・完成済み機能・正本CSV/ポリシー・raw data 無変更。
- runtime有効化0（Live/Hook/発注系接続なし）、発注権限0、閾値ハードコードなし。

### Blockerの限定範囲

- blockerなし。
- Tier B composite synthesis 層、pre-aggregated本計算、MarketStateSnapshot を replay/detector から埋める producer は本工程の範囲外（将来工程）。

### 未完了（別工程・ユーザー承認前に進めない）

- composite synthesis 層（Tier B 合成FLAG生成）。
- MarketStateSnapshot producer（replay/detector → snapshot）と EventSource の Live/Replay 実装。
- 較正ツールによる閾値確定（DOM収録完了 7/29 後）。
- 他364 variant への一般化。

### 次の再開位置

代表1型が「adapter（Tier A）→ 実evaluator → enforcer → SHORT_READY」まで実素材で通った。
次はユーザー承認のうえ、composite synthesis 層 / snapshot producer（replay統合）/ 較正ツール /
他variant一般化 のいずれを先行するかを決める。

### push状態

- コミット作成済み。**pushはお館様の指示があるまで行わない。**
