# Hook / Trigger 実市場検証・継続PDCA仕様 v1（承認案）

作成日: 2026-07-26 20:10 JST

状態: **仕様承認待ち。実装未承認。**

対象: Hook catalog 88件、Trigger catalog T01-T50、Stage 2C以降のobserve工程

## 0. この仕様で直す問題

現行Stage 2Cの

`収録完了 → threshold較正 → replay発火頻度確認 → HookEvent解禁`

だけでは、次を確認できない。

1. 各Hookが、生データ上で主張する市場現象を本当に捉えているか。
2. そのHookが一部の期間、side、sessionだけで成立する偶然や実装癖ではないか。
3. 検出したHookを、どの順序、時間窓、確認条件、否定条件で意思決定へ接続するか。
4. 市場・実装・データ品質が変化した後も、同じ検証を反復し、旧版と比較して戻せるか。

したがって、88件の登録、detectorの実装、unit test合格、発火頻度の適正化のいずれも、
それだけではHookの実市場妥当性を証明したものと扱わない。

この仕様は、HookとTriggerを一度で完成させる仕様ではない。生データを正本として、
仮説、検証、observe、見直しを版管理付きで繰り返せる状態を完成条件とする。

## 1. 改訂後の工程

Stage 2Cは、承認後に次の順へ改訂する。

1. **2C-1 収録完全性・coverage gate**
   - 現行のfull／liquidation個別判定を維持する。
   - journal、hash、sequence、欠落、停止延長、データ品質、容量を検証する。
2. **2C-H1 Hook主張仕様化**
   - 88 IDを「実装済みだから正しいHook」ではなく「検証対象の仮説」として全件監査する。
   - 各IDが何を観測したと主張するか、何を主張しないかを固定する。
3. **2C-H2 Hook独立照合**
   - detectorとは独立したreference判定を、生データから作る。
   - 検出例だけでなく、未検出例、near miss、反例、除外例も照合する。
4. **2C-H3 Hook実市場耐性検証**
   - 日、session、side、regime、データ品質別に成立範囲と崩れる範囲を確認する。
   - `VALIDATED`、`CONDITIONAL`、`REJECTED`、`UNVERIFIABLE`を判定する。
5. **2C-H4 threshold較正・holdout検証**
   - H2/H3を通過したHookだけを較正する。
   - 較正期間と未使用holdout期間を分離し、holdoutを見て再調整しない。
6. **2C-H5 HookEvent observe**
   - ユーザー承認済みHook版だけをobserve発火させる。
   - 根拠を追跡できないHookEventは出さない。
7. **2C-T1 Trigger主張仕様化**
   - T01-T50を検証対象の仮説として監査する。
   - primary、confirmation、順序、時間窓、context、veto、失効、再armを明示する。
8. **2C-T2 Trigger独立replay検証**
   - Trigger実装とは独立した期待判断と照合する。
   - 正例だけでなく、順序違い、期限切れ、veto、重複、near miss、欠損を検証する。
9. **2C-T3 Trigger shadow observe**
   - 注文へ接続せず、判断候補と全理由だけをappend-onlyで保存する。
   - 旧版と新版を同じ入力で並走比較する。
10. **2C-P 継続PDCA**
    - drift、誤検出、見逃し、仕様変更を入力としてH1/T1へ戻る。
    - 再検証、比較、承認、昇格、rollbackを同じ手順で反復する。

工程の関係は次のとおりとする。

```text
immutable raw journal
        |
        v
2C-1 integrity / coverage
        |
        v
Hook claim -> independent validation -> robustness -> threshold -> holdout
        |                                                    |
        +---------------- evidence --------------------------+
                                                             v
                                                     HookEvent observe
                                                             |
                                                             v
Trigger claim -> independent validation -> shadow comparison
        ^                                      |
        +--------------- PDCA / rollback ------+
```

## 2. 用語と責任境界

### 2.1 Feature

生データから計算できる値。例はimbalance、cancel/add比、sweep量、回復時間である。
Feature値が計算できただけではHook成立とはしない。

### 2.2 Hook claim

「どの観測事実が、どの時間範囲で、どの条件を満たしたため、この現象が成立した」と
生データまで遡って反証可能な主張である。

Hookが人間の意図を直接観測できない場合、意図を事実として主張してはならない。
`spoofing`、`bait`、`engineered`等のsuspected Hookは、観測可能な注文・約定・取消・価格反応の
signatureだけを検証対象とし、隠れた主体や意図の断定は対象外とする。

### 2.3 Context

判断の成立範囲を限定する状態であり、それ単独ではHookEventやTrigger判断を発火させない。
catalog上の項目が実際にはContextやFeatureなら、IDを残したまま役割を訂正する。

### 2.4 Trigger claim

検証済みHookとContextを、定めた時系列・時間窓・否定条件で組み合わせ、
`BUY_CANDIDATE`、`SELL_CANDIDATE`、`NO_ACTION`のいずれを出すべきかという主張である。
Triggerは注文ではなく、理由を持つ意思決定候補である。

### 2.5 実行との分離

HookEvent、TriggerDecision、Playbook、発注は別の責任とする。本仕様の範囲では
`execution_enabled: false`を維持し、注文可否、勝敗、損益をHook妥当性の代用品にしない。

## 3. 88 Hook全件監査

登録済み88 IDは、件数維持を目的にしない。各IDを同じ台帳で全件監査し、必要なら
split、merge、Feature化、Context化、rename、reject、retireする。ただし履歴追跡のため、
元IDは削除・再利用せずaliasと変更理由を残す。

Stage 2Bで実装した56 Hook候補は、detector実装範囲を示すだけで妥当性証明ではない。
未実装IDも含む88件を監査するが、全IDの実装・採用・合格を目標にしない。
`REJECTED`、`UNVERIFIABLE`、Feature／Contextへの訂正も正当な監査結果である。

各Hook版は最低限、次を持つ。

| 項目 | 必須内容 |
|---|---|
| hook_id / hook_spec_version | IDと不変の仕様版 |
| claim | 観測したと主張する現象を一文で記載 |
| non_claim | 意図、原因、方向など、証拠から言えないこと |
| role | FEATURE / HOOK / CONTEXT / SUSPECTED_SIGNATURE |
| raw_sources | depth、aggTrade、forceOrder、Flow等の正本入力 |
| eligibility | 判定可能になる最低入力と品質条件 |
| event_time | 市場上で現象が成立した時刻 |
| available_time | システムが利用可能になった時刻 |
| clauses | 成立に必要な個別条件 |
| counterexamples | 非成立、near miss、反例の定義 |
| episode / duplicate | 同一現象のまとめ方と重複抑止 |
| expiry | 現象の有効期限 |
| reference_method | detectorを呼ばずに生データから照合する方法 |
| dimensions | side、session、regime等の耐性確認軸 |
| status | 妥当性状態。threshold状態とは別管理 |
| dependencies | 利用するFeature／Hookの版 |
| owner_reason | 変更理由、承認、証拠report ID |

`registry.py`の名称、`direction_hint`、`suspected`はcatalog情報にすぎない。
`direction_hint`だけをTrigger方向へ流用してはならず、Triggerごとに方向対応を検証する。

## 4. Hook独立検証

### 4.1 正本

正本はcommit済みのraw journal、coverage ledger、frame hash、sequenceである。
収録データを検証結果に合わせて削除、修正、truncateしてはならない。

### 4.2 独立性

reference判定は次を満たす。

- production detectorの関数、候補結果、threshold判定結果を入力にしない。
- detectorと同一の中間booleanを共有しない。
- raw recordから各claim clauseを別経路で再計算する。
- detector版とreference版を証拠に記録する。
- reference自体の既知の限界と判定不能条件を明記する。

これはdetectorをdetector自身で正解判定する循環を防ぐためである。

### 4.3 照合集合

発火した窓だけを確認してはならない。各Hookについて次を含める。

- detector発火かつreference成立
- detector発火かつreference不成立
- detector未発火かつreference成立
- detector未発火かつreference不成立
- threshold直前／直後のnear miss
- data gap、stale、sequence異常等の判定不能・除外
- side反転、時系列反転、duration不足、回復前／後等の反例

rare eventは対象期間のeligible episodeを原則全件照合する。common eventを抽出する場合は、
結果を見る前にsession、side、時刻帯、強度帯、data quality別の抽出規則を固定する。
都合のよい発火例だけを選ばない。

### 4.4 照合結果

単純なpassed件数ではなく、最低限次を保存する。

- reference成立／不成立／判定不能
- detector発火／未発火
- clause別の期待値と実測値
- false positive、false negative、near miss、exclude reason
- event_time、available_time、検出遅延
- episode ID、重複数、失効後発火数
- 対応するraw session、frame、sequence範囲、hash

決定的なclaimは、判定不能を除く全照合対象でreferenceとdetectorの一致を要求する。
不一致はテスト失敗として隠さず、仕様誤り、reference誤り、detector誤り、時刻意味の相違の
いずれかに原因分離する。解消できないHookを`VALIDATED`にしない。

### 4.5 証拠packet

1件の判定を次の情報から再現できるappend-only evidence packetを作る。

```yaml
evidence_id:
hook_id:
hook_spec_version:
detector_version:
reference_version:
threshold_version:
input_manifest_hash:
sessions:
frame_and_sequence_ranges:
event_time:
available_time:
eligibility:
clause_expected_actual:
reference_result:
detector_result:
classification:
episode_id:
dimension_bins:
exclude_reason:
review_status:
```

## 5. 実市場耐性

Hookは全期間を混ぜた総数だけで判定しない。利用可能な範囲で次を分割する。

- buy-side / sell-side、またはup / down
- Asia / London / New Yorkとsession境界
- UTC日、平日／weekend
- activity、volatility、spread、depth、Flow stateの各帯
- 通常品質、遅延、stale直前、再接続後
- strength、duration、recoveryの各帯

各binでeligible数、成立数、false positive、false negative、判定不能、遅延、重複を報告する。
対象が存在しないbinは合格扱いにせず、`NO_COVERAGE`とする。

Hookの成立条件が特定の範囲だけで再現する場合は、失敗を平均で隠さず
`CONDITIONAL`として適用条件と禁止条件を仕様に固定する。適用条件を説明できない、
または独立期間で再現しない場合は`REJECTED`または`UNVERIFIABLE`とする。

## 6. Hookの状態とgate

Hookは一つのstatusに全責任を押し込まず、三軸で管理する。

1. **claim validity**
   - `HYPOTHESIS`
   - `SPECIFIED`
   - `VALIDATING`
   - `VALIDATED`
   - `CONDITIONAL`
   - `REJECTED`
   - `UNVERIFIABLE`
   - `RETIRED`
2. **threshold calibration**
   - 現行の`UNCALIBRATED` / `PROVISIONAL` / `CALIBRATED` / `DISABLED`
3. **promotion**
   - `OFF` / `SHADOW` / `OBSERVE_APPROVED`

gateは次のとおりとする。

- unit test合格は実装回帰gateであり、claim validityを上げない。
- coverage gate合格は検証可能性gateであり、claim validityを上げない。
- 発火頻度が適正でもclaim validityを上げない。
- `VALIDATED`、または適用条件を機械判定できユーザーが個別承認した`CONDITIONAL`だけが
  threshold較正へ進める。
- `CALIBRATED`かつholdout合格かつユーザー承認済みの版だけがHookEventを出せる。
- 依存HookまたはFeature版が変わった場合、影響するHookを自動的に再検証待ちにする。

## 7. threshold較正とholdout

thresholdはHookを正しく見せるために調整するものではない。claim validity確定後に、
観測強度の境界とobserve量を決める別工程とする。

- calibration manifestで使用session、期間、除外、Hook版、Feature版を固定する。
- パーセンタイル候補と採用理由をHookごとに示す。
- 同じholdoutを見ながらthresholdを反復調整しない。
- thresholdを変更したら新しい版とし、旧版を上書きしない。
- calibration期間と、調整に一度も使用していないholdout期間を分離する。
- replayでは発火頻度だけでなく、false positive、false negative、失効、重複、遅延を再確認する。
- holdout不合格時は、Hook claim、適用条件、thresholdのどこへ戻るかを原因別に記録する。

## 8. Trigger仕様

T01-T50も完成済みTriggerではなく仮説である。各Trigger版は最低限、次を持つ。

| 項目 | 必須内容 |
|---|---|
| trigger_id / version | 不変のIDと仕様版 |
| decision_claim | 何の証拠が揃えば何の候補判断を出すか |
| primary | 起点Hook IDと許容版／状態 |
| confirmations | 独立した追加証拠。必要数と版 |
| order | Hook間の前後関係 |
| windows | 各証拠の待機時間、有効時間、最大age |
| persistence | 継続時間またはepisode条件 |
| context | 成立を限定する条件。発火源にしない |
| veto / hard reject | 成立を止める条件と優先順位 |
| direction mapping | 各HookをBUY/SELLへ結ぶ明示根拠 |
| conflict rule | 相反Triggerが同時成立したときの処理 |
| duplicate / re-arm | 同一判断の抑止と再成立条件 |
| expiry | 判断候補の失効時刻 |
| data quality | 不足・stale・sequence異常時のfail-closed |
| evidence | 判断に使ったHookEvent IDとclause |
| state | validity、promotion、承認情報 |

複数条件を一つの不透明なscoreへ潰してはならない。各条件の成立、不成立、未確定、vetoを
reason codeで残す。registryの`direction_hint`だけで売買方向を決定しない。

Triggerは、要求するHookの版と状態を固定する。Hookが再較正、条件付き化、reject、retireされたら、
依存Triggerをそのまま有効にせず再検証待ちへ戻す。

## 9. Trigger独立検証

Trigger validatorはproduction Trigger engineの結果を正解にしない。同一のHook evidence列から、
仕様の状態遷移を別実装で再計算し、期待判断と実判断を照合する。

必須ケースは次のとおり。

- 全条件が正しい順序と時間窓で成立する正例
- primaryだけ、confirmation不足、context不一致
- 同じHookの重複を複数確認と数える誤り
- 条件は同じだが順序が逆
- window直前／直後、失効後、re-arm前
- vetoとhard rejectの発生前／同時／発生後
- BUY/SELL反転、相反Trigger同時成立
- stale、欠損、sequence異常、再接続境界
- available_timeより未来のデータを使うlook-ahead
- detector版、threshold版、Hook適用条件の不一致

各TriggerDecisionは次を再現可能にする。

```yaml
decision_id:
trigger_id:
trigger_version:
candidate: BUY_CANDIDATE | SELL_CANDIDATE | NO_ACTION
event_time:
decision_time:
expires_at:
input_hook_event_ids:
hook_spec_and_threshold_versions:
condition_trace:
veto_trace:
state_transitions:
reference_expected:
engine_actual:
classification:
input_manifest_hash:
```

Trigger検証の合格は、仕様どおりの意思決定候補を、未来情報なし、重複なし、根拠欠落なしで
再現できたことを意味する。勝敗や損益の評価とは混同しない。

## 10. 継続PDCA

### Plan

- 誤検出、見逃し、判定不能、drift、仕様曖昧箇所をissue化する。
- 変更するclaim、clause、threshold、Trigger条件を一つの版差分として事前記録する。
- 使用するcalibration期間、holdout、比較軸を結果を見る前に固定する。

### Do

- raw journalは変更せず、新版を別versionとして実装する。
- 同一input manifestに旧版と新版をreplayする。
- observe中は旧版を停止せず、新版を`SHADOW`で並走できるようにする。

### Check

- 旧版／新版の発火差、false positive、false negative、判定不能、遅延、重複を比較する。
- Hookはclaim clauseと市場耐性bin、Triggerはcondition traceと時系列を確認する。
- untouched holdoutと、直近のdrift監視期間を分けて報告する。

### Act

- ユーザー承認により昇格、条件付き採用、棄却、継続観察、rollbackを選ぶ。
- rollbackは旧版へのactive pointer切替で行い、証拠やraw dataを消さない。
- 採用後も旧版、比較report、承認記録を保存する。

再検証を起動する条件は最低限、次を含む。

- raw stream schema、normalization、clock、sequence処理の変更
- 依存Feature、Hook、detector、threshold、Triggerの版変更
- session／side／regime別の誤検出・見逃し・判定不能の偏り
- 発火頻度、遅延、重複、data-quality rejectの持続的変化
- 市場構造変化により既存の適用条件を外れる観測

再検証は定期実行だけでなく、任意のHook ID、Trigger ID、version、input manifestを指定して
on-demandで開始できなければならない。observe中の誤検出報告だけに依存せず、raw journal全体を
referenceで走査し、productionが発火しなかった見逃し候補も継続的に抽出する。

### PDCA機構自体の受入条件

- 同一raw input manifestと同一version集合を2回実行し、同じevidence／report hashを得る。
- active旧版とcandidate新版を同じ入力で実行し、差分をHook／Trigger／reason単位で出せる。
- candidate実行が旧版の証拠、設定、active pointerを上書きしない。
- 依存version変更時、影響するHook／Triggerだけを再検証待ちにできる。
- 処理中断後、既存evidenceを重複させずcheckpointから再開できる。
- promotion失敗時、raw dataと証拠を変更せず旧版へrollbackできる。
- rollback後も、誰が、どのreportを根拠に、どの版を切り替えたか追跡できる。

## 11. 成果物

実装工程では次を作る。ファイル名は実装着手時にrepository構造へ合わせて確定する。

1. 88 Hook全件のclaim manifestと役割監査表
2. detector非依存のHook reference validator
3. append-only Hook evidence packetとvalidation report
4. bin別市場耐性matrixと`NO_COVERAGE`一覧
5. versioned threshold manifestとcalibration／holdout report
6. T01-T50のTrigger claim manifest
7. Trigger reference validator、truth cases、decision trace
8. 旧版／新版shadow比較report
9. dependency graph、drift report、rollback記録

YAML、JSONL、reportは証拠の運搬形式であって、作成しただけでは検証完了にしない。
生データから独立再計算でき、反例と見逃しを含めて照合できることを完成条件とする。

## 12. 承認checkpoint

次は自動昇格しない。各checkpointで証拠reportを提示し、ユーザー承認を得る。

1. 88 Hook claim監査とreference方式
2. full側Hookの独立照合・市場耐性結果
3. full側threshold案とholdout結果
4. liquidation側Hookの独立照合・市場耐性結果
5. liquidation側threshold案とholdout結果
6. Trigger claimと独立検証結果
7. HookEvent observe解禁対象
8. Trigger shadow observe対象
9. 新版の昇格またはrollback

Hookごと、Triggerごとに結果が異なるため、全件一括合格を要求しない。
不合格・未coverageの項目をfail-closedで残し、合格項目の独立工程は進められる。

## 13. 禁止事項

- pytest合格、catalog登録、実装完了、発火頻度だけを妥当性証明にしない。
- detectorの出力をreference正解として使わない。
- 発火例だけを抽出し、未発火例、反例、near missを除外しない。
- holdoutを見ながら同じ版を調整しない。
- `UNCALIBRATED`または妥当性未確認HookをTrigger判断に使わない。
- 隠れた主体や意図を、observable signatureから事実として断定しない。
- 不透明な合算scoreだけでTrigger判断を出さない。
- 既存のFlow Price Response、3段チャート、8パターンを変更しない。
- 収録データを削除、修正、truncateしない。
- `execution_enabled`を`true`にしない。
- check移行、LIVE注文、発注ロジックへ接続しない。

## 14. 現行Stage 2Cへの適用境界

- 2C-1の収録と完全性判定は、そのまま継続する。
- 現行承認書は履歴正本として変更しない。
- 本仕様が承認された時点で、現行の「2C-1から直接2C-2 threshold較正へ進む」順序を停止し、
  `2C-1 → 2C-H1 → 2C-H2 → 2C-H3 → 2C-H4`へ置き換える。
- 仕様承認前は、manifest、validator、runtime、config、HookEvent、TriggerDecisionを変更しない。
- 仕様承認後は、収録期限を待たずに88 Hook claim監査と独立validator実装を開始できる。
- full期限ではfull依存Hook、liquidation期限ではE01-E06／C09を個別に検証する。
- Trigger実装・shadow開始は、依存Hookの妥当性とthresholdの承認後に限る。

この順序により、「検出器が動くこと」「Hookが市場現象として正しいこと」
「HookからTrigger判断が正しいこと」「注文を許可すること」を混同しない。
