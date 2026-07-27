# Composite Synthesis 層（Tier B 合成FLAG）Stage 1 設計・停止checkpoint

更新時刻: 2026-07-27 11:49:31 JST  
対象branch: `ui-refresh-v2`  
状態: **Stage 1調査・設計提案完了。Stage 2実装は正本不足／判定経路未定義のためNO-GO。お館様承認前に進めない。**

## 1. 承認範囲

- 必読文書、機械可読正本、`src/strategy_engine/`、`src/strategy_contract/`をread-onlyで照合する。
- 代表1型が参照するTier B key、正本に存在する合成定義、未定義点を列挙する。
- 配置案、変更予定file、試験案を提示する。
- Stage 1では実装、正本変更、runtime接続、Live／Hook／発注接続、commit、pushを行わない。
- 完成済みFlow Price Response、3段チャート、8パターン、OI、UI、収録基盤、raw dataを変更しない。

## 2. 読了・照合済み

指定順で次を読了した。

1. `ORDER_FLOW_STRATEGY_ENGINE_HANDOVER_TO_CODEX_20260727.md`
2. `PROJECT_MEMORY.md` 全955行
3. `ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md`
4. `ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md`
5. Condition Dictionary G16全48行、Predicate Class Registry、Predicate Registry、Variant State Binding
6. `Delta_Engine_Pro4web/src/strategy_engine/` 全10 file
7. `Delta_Engine_Pro4web/src/strategy_contract/` 全6 file
8. Stage 1試験設計に必要な `tests/strategy_engine/` 全file

機械集計実測:

- Predicate Class: 37行
- Predicate Registry: 286行
- Variant State Binding: 3,336行
- 代表1型binding: 8行（E00/E01/E02/E03/E04/E90/E98/E99）

件数はbinding policy記載値と一致した。

## 3. 正本照合結果

### 3.1 一致している事項

- Strategyは同時snapshotのscoreではなく、fresh evidenceによるordered state transitionである。
- candidate Conditionは材料のOR routeであり、全ID同時PASS／独立加点ではない。
- contradiction ConditionはIDだけで正負を決めず、較正済みcomparatorで評価する。
- `INVALIDATE`はnamed guard成立時にObservation Instanceを終了する。
- Hookはstate成立やOrder Triggerではなく、current stateの再評価をwakeする。
- runtime enabled 0、direct order authority 0、全binding `UNVALIDATED`を維持する。

### 3.2 齟齬・不足（Stage 2 blocker）

#### A. 指定されたCondition Dictionary機械可読CSVが存在しない

Git追跡fileを全検索したが、Condition Dictionaryは
`ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`だけで、CSVは0件だった。
Class Registry／Predicate Registry／Binding CSVは存在する。

Condition Dictionary本文は「各行は材料Conditionの`depends_on`を保持」と記すが、
G16表の列は `ID / condition_key / type / window / source / 定義 / independence_lineage`
だけで、具体的な`depends_on`列や論理式はない。

#### B. G16は現象の意味を定義するが、実行可能な合成契約を定義していない

正本から確認できるのは、source family、自然言語の現象定義、independence lineageまでである。
次は全13 keyで未定義であり、推測して実装できない。

- Tier A材料keyの確定集合とside解決
- AND／OR／否定の論理式
- comparator、threshold参照名、window、継続時間、必要sample数
- location／referenceの種類、価格、identity、freshness
- `attempt -> follow-through / failure`の時間順序、保持state、reset／expiry
- `holding -> failed`の先行状態、補充停止の判定、支持／抵抗breakの基準
- 素材完備かつ不成立時に`0`を出すかkeyを省略するか
- 同一名称FLAGを異なるvariant referenceへどう束縛するか

閾値をCalibrationBookへ移しても、上記の論理構造自体が未定義のため、
「閾値だけ未較正」の状態ではない。

#### C. 現MarketStateSnapshotだけでは時間順序とreference identityを保持できない

現snapshotはCVD／OI／price sample、bid／ask levels、tick size、
任意`pre_aggregated`だけを持つ。breakout後の継続、reference復帰、補充停止、
支持／抵抗breakを判定するための、Observation Instance固有referenceと先行状態がない。

G16のwindowが`STRATEGY_SPECIFIC`である以上、単一のglobal FLAGとして合成すると、
どのlocation／wall／referenceに対するFLAGかを失う。

#### D. 「反証成立でINVALIDATE」の呼出契約が未確定

代表1型のE01/E02/E03にある主なTier B反証は次である。

- E01: `downside_breakout_follow_through`
- E02: `bid_passive_defense_failed`
- E03: `downside_breakout_failure`

これらは各ADVANCE predicateの`contradiction_condition_ids`である。
現`RealPredicateEvaluator`ではcontradiction成立時に`holds=False`となり、
現`StrategyEngine`ではcalibrated ADVANCEの`holds=False`は`STAY`になる。
反証だけでE98を自動評価して`INVALIDATE`する経路はない。

E98（INV-005）のTier B candidateは
`bid/ask_passive_defense_holding/failed`であり、
`downside_breakout_follow_through`と`downside_breakout_failure`は含まれない。
したがって、Stage 2統合試験は次のどちらかを正本で確定する必要がある。

1. **現契約維持案**: contradictionはADVANCEを`STAY`させる。E98に束縛された較正済みnamed guardを
   `INVALIDATION_RECHECK` eventで明示評価した場合だけ`INVALIDATE`する。
2. **自動INVALIDATE案**: ADVANCE contradiction成立をE98へ変換する新契約を正本へ追加する。
   これは現binding／Engine semanticsの変更であり、現指示範囲では実装不可。

#### E. 引き継ぎ書のHEAD記載は1 commit古い

引き継ぎ書は最新commitを`e001031`と記すが、実測HEADは`d795dec`である。
`d795dec`のparentは`e001031`、subjectは
`docs: handover Strategy Engine work to Codex`であり、Strategy Engine最新code commitは
`e001031`のままである。code内容の分岐ではないが、Stage 2基準HEADは
`d795dec`と明示して承認を得る。

## 4. 代表1型がliteral bindingで参照するTier B key

代表variant:
`VAR-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-SHORT-VISIBLE_BOOK_WALL-001`

candidate／contradictionの和集合は13件。side selectorで実際に選ぶrouteは正本未定義であり、
13件同時成立を意味しない。

| ID | condition key | 使用edge | 正本にある合成定義 | 実行可能定義 |
|---|---|---|---|---|
| CD-G16-048 | `flow_price_divergence_active` | E01 candidate | aggressive flow方向とprice response方向が乖離。AGGTRADE+PRICE_RESPONSE+DELTA | 未定義 |
| CD-G16-001 | `bid_absorption_like_active` | E02 candidate | bid側でsell aggressionに対し下方進行が止まる。DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 未定義 |
| CD-G16-002 | `ask_absorption_like_active` | E02 candidate | ask側でbuy aggressionに対し上方進行が止まる。同source family | 未定義 |
| CD-G16-019 | `upside_breakout_attempt` | E03 candidate | 上側referenceをinitiative buyで試行。DEPTH+AGGTRADE+LOCATION+PRICE_RESPONSE | 未定義 |
| CD-G16-020 | `downside_breakout_attempt` | E03 candidate | 下側referenceをinitiative sellで試行。同source family | 未定義 |
| CD-G16-021 | `upside_breakout_follow_through` | E01 contradiction | 上抜け後もbuy participationとprice progress継続。同source family | 未定義 |
| CD-G16-022 | `downside_breakout_follow_through` | E01 contradiction | 下抜け後もsell participationとprice progress継続。同source family | 未定義 |
| CD-G16-023 | `upside_breakout_failure` | E03 contradiction | 上抜け後にacceptanceせずreference下へ復帰。同source family | 未定義 |
| CD-G16-024 | `downside_breakout_failure` | E03 contradiction | 下抜け後にacceptanceせずreference上へ復帰。同source family | 未定義 |
| CD-G16-035 | `bid_passive_defense_holding` | E03/E98 candidate | bid補充と価格保持が継続。同source family | 未定義 |
| CD-G16-036 | `ask_passive_defense_holding` | E03/E98 candidate | ask補充と価格保持が継続。同source family | 未定義 |
| CD-G16-037 | `bid_passive_defense_failed` | E02/E03/E98 candidate/contradiction | bid補充が止まり支持価格を下抜け。同source family | 未定義 |
| CD-G16-038 | `ask_passive_defense_failed` | E02/E03/E98 candidate/contradiction | ask補充が止まり抵抗価格を上抜け。同source family | 未定義 |

Class／bindingから関連Tier A候補として読めるものは次である。ただし合成式ではない。

- divergence: `cvd_change_5s`, `cvd_slope_5s`,
  `upward_progress_ticks_1s`, `downward_progress_ticks_1s`
- absorption: `buy_no_progress_ratio_1s`, `sell_no_progress_ratio_1s`
- breakout: `upward_progress_ticks_1s`, `downward_progress_ticks_1s`
- wall／defense: `bid/ask_wall_concentration_top10`,
  `distance_to_nearest_bid/ask_wall`, `bid/ask_refresh_count_1s`,
  `bid/ask_pull_ratio_1s`

## 5. 正本確定後の配置・file構成案

### 5.1 新規file

- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/composite_synthesis.py`
  - `CompositeSynthesizer`
  - 較正済みruleだけを評価
  - clause内AND、clause間OR、欠測／非finite／未較正はkey非出力
  - temporal ruleは明示的なreference contextとmonotonic stateを使用
  - Live／Hook／発注APIを持たない
- `Delta_Engine_Pro4web/tests/strategy_engine/test_composite_synthesis.py`
  - 13 keyの単体・境界・欠測・時間順序試験
- `Delta_Engine_Pro4web/tests/strategy_engine/test_engine_composite_invalidation.py`
  - adapter形式snapshotからTier Bを生成し、正本で確定したE98経路でINVALIDATEする統合試験

### 5.2 変更承認が必要な既存file

- `src/strategy_engine/predicate_eval.py`
  - CalibrationBookへcomposite rule較正を追加する。
  - threshold値、window値、reference許容幅はここへ注入し、production hardcodeを禁止する。
- `src/strategy_engine/ingestion/condition_adapter.py`
  - Tier A生成後にCompositeSynthesizer出力をmergeする。
  - 同名key衝突時のfail-closed規則を追加する。
- `src/strategy_engine/ingestion/market_state.py`
  - 正本が要求する場合だけ、reference identity／reference price／temporal contextを追加する。
  - 追加内容は正本確定前に決めない。
- `src/strategy_engine/ingestion/__init__.py`
  - Tier B gap記述を更新し、新APIをexportする。
- `tests/strategy_engine/_helpers.py`
  - test-only composite calibration fixtureを追加する。

`src/strategy_contract/`、既存検出器、Live pipeline、Hook runtime、発注系は変更しない。
現契約維持案なら`engine.py`と`real_predicate_eval.py`も変更しない。
自動INVALIDATE案を選ぶ場合は正本更新と別Stage 1が必要である。

## 6. 正本へ必要な最小追加契約

各Tier B keyについて、少なくとも次を機械可読に確定する必要がある。

- stable condition ID／key／rule version
- side selectorとreference selector
- 入力Tier A keyと必須／任意区分
- AND clause／OR route／否定条件
- comparatorとCalibrationBook内threshold名
- window、persistence、最小sample、freshness
- temporal prerequisite、reset、expiry
- active／inactive／unknownの出力表現
- Observation Instance／referenceへのscope
- predicate contradictionとnamed invalidationの対応

Codexは正本CSV／policyを変更しない。Claude webの検証とお館様の決定を受けた正本を入力として実装する。

## 7. 試験案

1. **13 key coverage**: 各keyの成立、直前境界不成立、side対称性。
2. **sequence**: attemptなしのfollow-through/failureは非出力、正しい順序だけ成立、
   reset／expiry後は非出力。
3. **fail-closed**: 必須素材を1つずつ欠測、reference欠測、stale、非finite、
   未較正rule、空CalibrationBookでkey非出力。
4. **CalibrationBook**: threshold値を変えると境界だけが変わり、production codeに数値定数がない。
5. **merge**: Tier Aを保持、Tier Bを追加、同名pre-aggregated key衝突は正本規則どおりfail-closed。
6. **predicate veto**: `downside_breakout_follow_through`,
   `bid_passive_defense_failed`, `downside_breakout_failure`が該当ADVANCEを進めない。
7. **Engine INVALIDATE**: 正本で確定したE98 Tier B guardを実データ形式snapshotから合成し、
   `INVALIDATION_RECHECK`でE98成立、phase `INVALIDATED`、以後復活なし、handoff 0、order_intents 0。
8. **回帰**: strategy_engine、strategy_contract、既存516件、全体suiteを維持する。

## 8. 検証結果

code変更前の個別suite実測:

- `tests/strategy_engine`: **31 passed**
- `tests/strategy_contract`: **27 passed, 1 skipped**
- 合同実行: **58 passed, 1 skipped**

全体suiteはcode failureではなく、現在のWindows ACLで完走不能だった。

- repository root実行: 既存のaccess-denied directory 2件をcollectionできず停止。
- `tests/`限定: **458 passed, 1 skipped, 116 setup errors**。
  errorsはpytest一時root `C:\Users\user\AppData\Local\Temp\pytest-of-user`への
  `PermissionError`で、test assertion failureではない。
- workspace内basetemp再試行もsandbox ACLで拒否された。
- 再試行でCodexが作成した一時directoryは、その正規化絶対pathがworkspace内であることを確認後、
  当該directoryだけ削除済み。

Stage 2完了時は、利用可能な一時rootを確保して全574基準を再実測する。

## 9. 変更file

- 本checkpointのみ新規。
- source、test、正本CSV／policy、runtime、config、raw dataは変更なし。
- 既存の未追跡fileはユーザー所有物として変更なし。

## 10. Blockerの限定範囲

blockerはComposite SynthesisのStage 2実装と、その新規試験だけに限定される。
Hook Stage 2A/2B収録、Flow Price Response、3段チャート、既存Strategy Engine、
既存回帰suiteを停止・変更する理由にはしない。

## 11. 未完了と次の再開位置

未完了:

- 13 keyの実行可能な機械可読合成rule
- reference／temporal state契約
- contradictionとINVALIDATEの対応確定
- Stage 2実装、全試験、documented gap更新、commit

再開条件:

1. お館様が本Stage 1報告を確認する。
2. 正本不足A〜Dについて、正本追加または既存契約の解釈を明示する。
3. 既存file変更範囲（§5.2）を承認する。

再開位置:

`composite_synthesis.py`の実装前。正本ruleを読み取り専用でロードし、
最初に空／未較正CalibrationBookのfail-closed試験から着手する。

commit未作成、pushなし。

## 12. Stage 1承認受領後の再開条件再照合

確認時刻: 2026-07-27 12:04:01 JST

Claude web検証・お館様決定として、次を受領した。

- Stage 1: APPROVED
- Stage 2: §4の全条件を満たした場合に再開許可
- INVALIDATE方針: 現契約維持案
  - contradiction成立は`holds=False -> STAY`
  - `INVALIDATE`はE98 `INVALIDATION_RECHECK` named guardだけ
  - `engine.py`、`real_predicate_eval.py`、`strategy_contract/`は変更しない

承認受領直後にworkspace正本をread-onlyで再照合した結果:

1. `ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`の代表1型E98は
   従来行のままである。`bid_passive_defense_failed`は既存のcandidate／contradictionにあるが、
   `downside_breakout_follow_through`と`downside_breakout_failure`はcandidate／contradictionの
   どちらにもなく、§3.1の正本更新完了は確認できなかった。
2. `ORDER_FLOW_CONDITION_DICTIONARY_V0_1_20260726.md`のG16は従来の自然言語7列のままで、
   Tier A材料、論理式、side解決を定める追記は確認できなかった。
3. `トリガー作成指示書群/`に新規のComposite rule正本／policy／CSVは存在しなかった。
4. HEADは`d795dec`のままで、正本更新commitも存在しなかった。

したがってStage 2再開条件1・2は未充足であり、source実装とtest追加は未着手のまま停止する。
blockerはComposite Synthesis Stage 2だけに限定する。次の再開位置は、正本更新後の
E98行とG16合成式の再照合である。