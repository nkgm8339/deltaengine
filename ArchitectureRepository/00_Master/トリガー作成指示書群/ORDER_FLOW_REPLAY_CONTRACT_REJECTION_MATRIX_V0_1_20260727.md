# Replay契約 拒否試験 対照表 v0.1

作成日: 2026-07-27 JST
状態: **未較正の契約構造試験。runtime有効化0・発注権限0。production採用・発注許可ではない。**

## 0. 目的

Strategy Engineが将来実装されたとき、設計ポリシーが定めた判定契約に違反する入力・遷移・
発注経路を確実に拒否することを、決定論リプレイ上の試験として先に固定する。実装より先に契約
試験を作ることで、後続実装が契約を破ったら即座にテストが落ちる状態を作る。

本試験が対象とするのは**契約の構造**のみ。閾値・comparator・window・timeoutの数値較正は範囲外。

## 1. 契約検証の最小骨格（contract enforcer）

Strategy Engine本体ではなく、edge遷移の受理/拒否判定だけを行う最小層。

| file | 役割 |
|---|---|
| `Delta_Engine_Pro4web/src/strategy_contract/rejection_codes.py` | `RejectReason` enum と根拠条項マッピング `REASON_CLAUSE` |
| `Delta_Engine_Pro4web/src/strategy_contract/events.py` | `ContractEvent`（合成イベント：event_id / source_event_id / source_time / received_time / engine_time_ns / calibration_status / detector_status / route_role / hard_source_status / arm gate flags） |
| `Delta_Engine_Pro4web/src/strategy_contract/variant_contract.py` | 正本FSM+binding CSVから1 variant契約を**読み取り専用**ロード |
| `Delta_Engine_Pro4web/src/strategy_contract/enforcer.py` | `ContractEnforcer`（Observation Instance state machine）。**発注APIを持たない**。TERMINALは`OrderReadyHandoff`（LONG_READY/SHORT_READY）をgateへ返すのみ |
| `Delta_Engine_Pro4web/src/strategy_contract/replay_driver.py` | 合成イベント列・journal record両対応の決定論ドライバ。`order_intents`は構造的に常に0 |

golden path / negative pathのfixtureはユーザー提示variant
`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`（判定契約4の例）。
FSM構造（E00 arm → E01–E04 advance → E90 terminal / E98 invalidate / E99 expire、E04がOI hard state）は
正本CSVから読み取り専用でロードし、イベントのみ合成する。

## 2. 対照表（試験名 × 根拠条項 × RejectReason × 結果）

正本根拠の略記:
- 判定契約N = `ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md` §2
- policy§N = 同文書 §N
- routing§N = `ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md` §N

| カテゴリ | 試験関数 | 根拠条項 | RejectReason（拒否）/挙動 | 結果 |
|---|---|---|---|---|
| R1 順序逆転 | `test_R1a_older_source_time_is_rejected` | 判定契約2 | `STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION` | PASS |
| R1 遅延到着 | `test_R1b_delayed_arrival_out_of_order_is_rejected` | 判定契約2 | `STALE_EVIDENCE_BEFORE_PRIOR_TRANSITION` | PASS |
| R2 同一event再利用 | `test_R2a_same_event_id_reuse_within_instance_is_rejected` | 判定契約3 | `SOURCE_EVENT_ID_REUSED` | PASS |
| R2 別instance再利用 | `test_R2b_cross_instance_reuse_is_undefined_by_canon` | 判定契約3（未定義） | **UNDEFINED_BY_CANON** | SKIP（明示） |
| R3 反証後advance/terminal | `test_R3a_advance_and_terminal_after_invalidation_are_rejected` | 判定契約6 | `INSTANCE_TERMINATED_BY_INVALIDATION` | PASS |
| R3 反証後の復活不可 | `test_R3b_valid_evidence_after_invalidation_does_not_revive` | 判定契約6 | `INSTANCE_TERMINATED_BY_INVALIDATION` | PASS |
| R4 deadline後advance | `test_R4a_advance_after_deadline_is_expired` | 判定契約7 | `INSTANCE_EXPIRED` | PASS |
| R4 EXPIREでOI無し | `test_R4b_expire_edge_produces_no_order_intent` | 判定契約7 | handoff None / order_intents 0 | PASS |
| R4 monotonic判定 | `test_R4c_expiry_uses_monotonic_engine_time_not_wall_clock` | 判定契約7 | 壁時計巻き戻しに非依存 | PASS |
| R5 発注API不在 | `test_R5a_no_order_send_api_exists_on_enforcer_or_handoff` | routing§0 | 型/APIとして存在しない | PASS |
| R5 発注経路不在 | `test_R5a_package_source_has_no_order_send_path` | routing§0 | source上に発注symbol無し | PASS |
| R5 terminal handoff | `test_R5b_terminal_hands_off_direction_ready_not_an_order` | 判定契約8 | SHORT_READY handoffのみ | PASS |
| R5 正本発注権限0 | `test_R5c_canon_routing_has_zero_direct_order_authority` | routing§0 | 全25,664 routeが`direct_order_authority=NO`・`runtime_route_enabled=NO` | PASS |
| R6 context-only advance | `test_R6a_context_only_route_cannot_advance` | routing§5 | `CONTEXT_ONLY_CANNOT_ADVANCE_HARD_STATE` | PASS |
| R7 未較正edge | `test_R7a_uncalibrated_edge_cannot_fire` | policy§5 | `UNCALIBRATED_EDGE` | PASS |
| R7 provisional edge | `test_R7a_provisional_edge_cannot_fire` | policy§5 | `UNCALIBRATED_EDGE` | PASS |
| R7 未実装route | `test_R7b_registered_unimplemented_route_is_runtime_disabled` | routing§5 | `ROUTE_RUNTIME_DISABLED` | PASS |
| R7 hard source stale/unknown | `test_R7c_oi_state_rejects_unknown_or_stale_hard_source[UNKNOWN/STALE]` | 判定契約9 | `HARD_SOURCE_UNKNOWN_OR_STALE` | PASS |
| R7 hard source OK（対照） | `test_R7c_oi_state_accepts_ok_hard_source` | 判定契約9 | 受理 | PASS |
| R8 arm前提不足 | `test_R8a_arm_requires_location_first_predicate_and_freshness[4 case]` | routing§2 | `ARM_REQUIRES_LOCATION_FIRST_PRED_FRESHNESS` | PASS |
| R8 arm成立（対照） | `test_R8a_arm_succeeds_when_all_conditions_hold` | routing§2 | armed | PASS |
| GP 正常経路（対照基準） | `test_golden_path_reaches_short_ready_handoff` | 判定契約4/8 | SHORT_READY handoff / order_intents 0 | PASS |
| GP 正本ロード | `test_contract_loads_user_example_variant_from_canon` | 判定契約4 | E04のみhard source | PASS |
| meta | `test_every_reject_reason_has_a_clause_citation` | — | 全RejectReasonに根拠条項 | PASS |

試験結果集計: **27 passed, 1 skipped（UNDEFINED_BY_CANON）**。
全体回帰: **543 passed, 1 skipped**（既存516件は全件合格、影響0件）。

## 3. 未定義点（正本側の将来更新事項）

- **【未定義-1】cross-instance の `source_event_id` 再利用**
  判定契約3は「同じ`source_event_id`を**複数state**の成立証拠として再利用しない」と定義し、
  **同一Observation Instance内**の再利用のみを禁止している。**別instanceにまたがる**再利用の
  可否は正本に定義がない。
  - 本試験では同一instance内の再利用のみを`SOURCE_EVENT_ID_REUSED`として固定し、
    cross-instanceは`UNDEFINED_BY_CANON`として明示スキップした（勝手に仕様を決めない）。
  - 観測（契約として断定しない）: 現enforcerは再利用検出をinstance単位でscopeするため、
    別instanceは同一idを受理する。これが正しいかは正本未定義。
  - 正本側で扱いを定義する場合の将来更新事項として記録する（本作業では正本文書を変更しない）。

## 4. 制約遵守

- runtime有効化0・発注権限0を維持（enforcerに発注API無し／既存runtime非接続／正本CSV読み取り専用）
- 完成済みFlow Price Response・3段チャート・8パターン・OI・UI・既存runtime・raw dataは変更なし
- 収録中のHook Stage 2A/2B観測基盤は停止・変更なし（新規隔離パッケージのみ追加）
- 正本CSV/ポリシー文書は読み取りのみ（変更なし）
- 閾値・comparator・window較正は範囲外（契約の構造だけを試験）

## 5. 位置づけ

本試験は契約の構造を固定したものであり、以下は別工程:

- historical replayによるvariantの採用／棄却／統合
- 採用variantのthreshold・時機・枚数・risk/execution gate較正
- HookEvent解禁、Playbook選抜、check／LIVE移行

これらはユーザー承認前に進めない。
