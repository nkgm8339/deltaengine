# Order Flow Strategy Condition Subsets Checkpoint

## 2026-07-27 01:31:12 JST 開始checkpoint

### 承認範囲

- ユーザーの`GO`により、560件のCondition Universeから初期6 Strategyすべてのsubsetを切り出す。
- required、supporting、contradiction、invalidation、execution、positionへ役割分離する。
- 88 Hook registryとStage 2B実装済み56 Hookを照合し、Hook-to-Condition routingを定義する。
- 文書と機械可読matrixの作成・検証まで。runtime、threshold較正、HookEvent解禁、注文は行わない。

### 完了済み

- `PROJECT_MEMORY.md`全800行を全文再確認。
- Candidate Set全403行を全文確認。
- Condition Dictionary 560件・16groupの契約を再確認。
- Hook registry 88件と実装済みdetector 56件を確認。

### 未完了

- 6 Strategyのlong／short subset設計。
- condition role、hard／soft、entry／position phaseの割当。
- Hook-to-Strategy／Hook-to-Condition routing。
- ID実在、一意性、競合Strategy、反証、position経路の検証。
- PROJECT_MEMORYと最終checkpoint更新。

### 変更file

- 本checkpointのみ。

### 検証結果

- source code、config、runtime、UI、raw dataの変更0。
- production Strategy採用0、threshold変更0、HookEvent解禁0、注文0。

### Blockerの限定範囲

- blockerなし。
- B category等の未実装Hookは`REGISTERED_UNIMPLEMENTED`としてrouting仕様へ残し、実装済みと偽装しない。

### 次の再開位置

Condition DictionaryのID／keyを機械抽出し、6 Strategyの方向対称subsetを作る。

---

## 2026-07-27 ユーザー訂正checkpoint

### ユーザー確定事項

- 分足分析との本質的な違いは、Hook後の**状態変化を観察すること**。
- Strategyには観察工程そのものが入る。
- Hook発火時点でentry判定を完結させず、規定された状態遷移を順番に確認して初めて発注する。
- ユーザー提示のSELL例:

```text
Divergence
  -> Absorption
  -> 買い壁が崩れた
  -> OIが減少した
  -> 初めてSELL
```

### 設計変更

- 作成済みCondition subset CSVはStrategy本体ではなく、観察に使う材料索引へ降格する。
- Strategy本体を`Hook -> Observation Instance -> ordered states -> Order Trigger`として定義する。
- 各stateに必要Condition、順序、最大待ち時間、反証、失効、再arm、発注前最終gateを持たせる。
- 同じConditionが最終時点で同時成立しただけではsequence成立としない。

### 未完了

- ユーザー例を含む6 Strategyのordered observation sequence。
- Hook routingへ観察instance開始／更新／失効の責任を追加。
- sequence replayで順序逆転、timeout、途中反証、同一event二重使用を拒否するtest contract。

### 次の再開位置

静的subsetを各Strategyの観察stateへ割り当て、状態遷移仕様を正本として作成する。
---

## 2026-07-27 02:01:53 JST 世界再学習checkpoint

### 承認範囲

- ユーザーの「世界から学べ」という訂正に従い、条件名ではなく、世界のトレーダー／教育者が示す**時系列の観察経路**を収集する。
- Sourceが述べた原型と、DeltaEngine向けに方向・location・確認経路を展開したvariantを混同しない。
- runtime、threshold、Hook、発注経路は変更しない。

### 完了済み

- Jigsawから、reversalの`absorption / buyer fade / sellers jump in`、retestでのfade確認、breakout接近時のmomentum増加とfade時exitを抽出。
- Axiaから、breakoutのinitiative変化、bid absorption後のbid pullによるcut-and-reverse、extreme break後のHVN形成とrange内flick、CVD上昇を伴うfailed breakdown、pullback停止後のcontinuationを抽出。
- ATASから、absorption holdとabsorption failure、stacked imbalanceのhold／failure、delta tailとaggressor exhaustion、unfinished auction、OI build後のfalse break trap／outside holdを抽出。
- Bookmapから、stop runのacceptance／rejection、iceberg hold／depletion、liquidity pull／reform、post-break value migration、news impulse後のabsorption、liquidation cascade継続／終端を抽出。
- 条件名の羅列ではなく、`開始 -> 途中確認 -> 分岐 -> 終端`として約50のsource-grounded原型候補へ整理中。

### 変更file

- 本checkpointのみ。

### 検証結果

- source code、config、runtime、UI、raw dataの変更0。
- 作成済み560 Conditionは材料辞書のまま。Strategy本体としては未採用。
- production Strategy採用0、HookEvent解禁0、注文0。

### Blockerの限定範囲

- blockerなし。
- Binance BTCUSDTではCME MBOのnative stop／iceberg識別はできないため、同じ名称を直接観測と偽装せず、`DIRECT / INFERRED / UNAVAILABLE`を分ける必要がある。
- OIは10秒pollのsnapshotであり、数秒級sequenceの終端確認には遅すぎる可能性がある。OI必須patternは別の観察期限を持たせる。

### 次の再開位置

Source evidence表を先に作り、各原型を開始・遷移・分岐・timeout・invalidation・order terminalへ正規化する。
---

## 2026-07-27 02:10:20 JST Strategy名称台帳完了checkpoint

### 承認範囲

- ユーザー指定の10通称をStrategy Familyの初期正本とし、状態観察、遷移log、replay検証の識別子へする。
- 文書・機械可読台帳のみ。runtime、Hook、threshold、注文経路は変更しない。

### 完了済み

- 10 Familyへ一意なstrategy_family_idを付与。
- 具体的な観察経路へpattern_idとpattern_nameを付ける階層を定義。
- strategy_family_id / pattern_id / strategy_version / observation_instance_id / from_state / to_state / evidence_event_idsを持つappend-only遷移log契約を定義。
- ユーザー例をPAT-CVD-BEAR-ABSFAIL-BIDBREAK-OIUNWIND-001として命名し、6 stateへ分解。

### 変更file

- ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.md
- ORDER_FLOW_STRATEGY_NAME_REGISTRY_V0_1_20260727.csv
- 本checkpoint

### 検証結果

- CSV 10行、family ID 10件一意、family名10件一意。
- example pattern ID存在確認済み。
- CSV SHA-256: D9B0CDBC5652D7AE2C7D5BD9F73DDA5D6718F0C3782A0D9D88D1C386897CB245
- Markdown SHA-256: D2CD730D329CE1596D85DA2A5CBF4F959A44052212566B5F727F414BD8A160FD
- source code、config、runtime、UI、raw dataの変更0。注文0。

### Blockerの限定範囲

- blockerなし。
- 10件はFamily台帳であり、具体Patternは未登録。名称を付けただけで発注可能とはしない。

### 次の再開位置

各Family配下へ世界資料由来のnamed Patternを登録し、各Patternを開始・遷移・分岐・timeout・invalidation・terminalへ分解する。
---

## 2026-07-27 02:39:18 JST named Pattern初版完了checkpoint

### 承認範囲

- ユーザーのGOにより、初期10 Strategy Family配下へ世界資料由来のnamed状態遷移Patternを登録する。
- 開始、順序、terminal、反証、expiry、出典、observabilityの文書化と機械可読化まで。
- runtime、Hook detector、threshold、Order Trigger実装、発注は変更しない。

### 完了済み

- Jigsaw、Axia、ATAS、Bookmapの時系列記述をSource register 26件へ整理。
- 10 Family x 5件、計50 named Patternを登録。
- 49件をWORLD_DERIVED、ユーザー提示経路1件をUSER_DEFINEDとして分離。
- 50 Patternを256 ADVANCE、50 TERMINAL、50 INVALIDATE、50 EXPIRE、計406 edgeへ展開。
- PROJECT_MEMORYへ、Strategyはnamed状態遷移FSMでありCondition subsetではないというユーザー訂正を追記。

### 変更file

- `ORDER_FLOW_WORLD_NAMED_PATTERN_CATALOG_V0_1_20260727.md`
- `ORDER_FLOW_WORLD_NAMED_PATTERN_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_WORLD_NAMED_PATTERN_FSM_V0_1_20260727.csv`
- `PROJECT_MEMORY.md`
- 本checkpoint

### 検証結果

- Family 10、Pattern 50、Pattern ID 50件一意、Pattern名50件一意。
- 全WORLD_DERIVED Patternにsource IDあり。無効source ID 0。
- 全Patternに開始、3件以上のadvance、terminal 1、invalidation 1、expiry 1あり。
- FSM edge 406件すべて一意。検証error 0。
- Family registry SHA-256: `D9B0CDBC5652D7AE2C7D5BD9F73DDA5D6718F0C3782A0D9D88D1C386897CB245`
- Pattern catalog SHA-256: `8A3792C1BD6C2A9D3111F32EF4145AC0E25BCBA2E6BA3E586DA9D73B853CDE6D`
- Pattern registry SHA-256: `16ED17D2DA3E4EBECCAC8294FB73D5CFD271DC10F0176F127ACC66A393B71277`
- FSM SHA-256: `ABBD3854462CCBC80FBBFB7B3219271316EBEB225B26B5D9A7B09FE6F7C8DAA7`
- source code、config、runtime、UI、raw data変更0。production採用0、注文0。

### Blockerの限定範囲

- blockerなし。
- 本版は50の遷移原型であり、ユーザーが求める数百Patternの完成を意味しない。
- native MBOがないためiceberg／stop identityはINFERREDのまま。OI pathは10秒poll制約によりLIMITEDのまま。
- 数値timeout、threshold、枚数、execution gateは未較正。

### 未完了

- 50原型から根拠のある方向、location、confirmation分岐を展開し、数百のnamed Patternへする。
- 各stateへ560 Condition材料を接続する。
- Hook-to-Pattern arm/update/expire routingを作る。
- replayで順序逆転、timeout、反証、同一event二重使用、到達可能性を検証する。

### 次の再開位置

無根拠な直積で件数を増やさず、各source原型に許されるdirection、location、confirmation軸を個別定義してderived variantを生成する。
---

## 2026-07-27 02:52:18 JST derived named variant完了checkpoint

### 承認範囲

- ユーザーのGOにより、50 source-grounded原型を、意味が成立するdirectionとlocationへ展開する。
- confirmationは原型の順序を維持し、無根拠な組合せで件数を水増ししない。
- 文書・機械可読台帳・検証まで。runtime、Hook detector、threshold、Order Trigger実装、発注は変更しない。

### 完了済み

- 50原型を365個の一意なderived named variantへ展開。
- LONG 187、SHORT 178。10 Familyと50原型をすべてcoverage。
- locationをCondition Dictionaryに実在する9分類へ限定。
- 全365件を`BASE_CANONICAL_ONLY`とし、confirmationの自由直積を禁止。
- 365 LOCATION_ARM、1,876 ADVANCE、365 TERMINAL、365 INVALIDATE、365 EXPIRE、
  計3,336 edgeのvariant FSMを作成。
- ユーザー例をVisible Bid Wall contextへ束縛したSHORT variantとして登録。
- PROJECT_MEMORYへ本checkpointの確定事項を追記。

### 変更file

- `ORDER_FLOW_DERIVED_PATTERN_VARIANT_POLICY_V0_1_20260727.md`
- `ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANTS_V0_1_20260727.csv`
- `ORDER_FLOW_DERIVED_NAMED_PATTERN_VARIANT_FSM_V0_1_20260727.csv`
- `PROJECT_MEMORY.md`
- 本checkpoint

### 検証結果

- variant 365、variant ID 365件一意、variant名365件一意、base coverage 50。
- FSM edge 3,336件一意。edge内訳はLOCATION_ARM 365、ADVANCE 1,876、
  TERMINAL 365、INVALIDATE 365、EXPIRE 365。
- 560 Condition ID／key照合error 0。26 source ID照合error 0。
- BUY／SELL固定17原型の反対方向mirror 0。
- 各variantにLOCATION_ARM、TERMINAL、INVALIDATE、EXPIREが各1件。
- 全terminalの`LONG_READY`／`SHORT_READY`とvariant方向が一致。
- `active range boundary`／`round number`混入0。
- `POST_EVENT_BALANCE`は4件すべて`EXT_CALENDAR_REQUIRED`。
- 横断検証error 0。
- Variant registry SHA-256:
  `A77CFC34C527DA9573AC75F56ED210C02DEEBB41DD2075AE0C70303ED8F4EF37`
- Variant FSM SHA-256:
  `01703080A361079BAE5C87CF19CA155ED158DADBDFD7E8D1B2C7A7F3645A1DE2`
- Variant policy SHA-256:
  `46CDA796DA6373F9DAFF3DFEB1CBE5CDECDBF23C180282E0CD033BC434934D2A`
- source code、config、runtime、UI、raw data変更0。production採用0、注文0。

### Blockerの限定範囲

- blockerなし。
- 365件は検証候補であり、勝てるStrategy 365件の確定ではない。
- 4件はexternal calendar未接続中arm不可。
- native MBOなしのiceberg／stop identityはINFERRED、OI pathは10秒poll制約によりLIMITED。
- 数値threshold、timeout、枚数、execution gateは未較正。

### 未完了

- 各variant stateへ560 Condition材料を`required / contradiction / invalidation`として接続する。
- Hook-to-variantのarm／update／expire routingを定義する。
- replayで順序逆転、timeout、途中反証、同一event二重使用、到達可能性を検証する。
- replay成績からvariantを採用／棄却／統合し、threshold、時機、枚数を較正する。

### 次の再開位置

3,336 edgeの各stateへCondition材料を接続するstate-condition binding契約を作り、
その後HookからObservation Instanceを開始・更新・失効させるroutingへ接続する。
---

## 2026-07-27 07:16:20 JST state binding／Hook routing完了checkpoint

### 承認範囲

- ユーザーのGOにより、365 named variantsの全stateを560 Condition Dictionaryへ接続する。
- 既存88 Hookを、asserted eventとsource dependency refreshを区別してnamed variantへ多対多接続する。
- 文書・機械可読設計台帳・横断検証まで。runtime、threshold、Order Trigger実装、発注は変更しない。

### 完了済み

- 37 Predicate Classを定義。
- 236 Observation Predicateと50 Invalidation Predicate、計286件を一意ID化。
- 365 variantの3,336 edgeすべてへstate-condition bindingを作成。
- 前state後のfresh evidenceのみ、同一event再利用禁止、context-only hard advance禁止、
  terminalはdirection READYまでという評価契約を固定。
- 88 Hookへasserted event classとrefresh可能Predicate classを分離して付与。
- 84 Hook x 365 variantへ25,664件のdesign routeを作成。
- PROJECT_MEMORYへ確定事項を追記。

### 変更file

- `ORDER_FLOW_STATE_CONDITION_BINDING_POLICY_V0_1_20260727.md`
- `ORDER_FLOW_OBSERVATION_PREDICATE_CLASS_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_OBSERVATION_PREDICATE_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`
- `ORDER_FLOW_HOOK_VARIANT_ROUTING_POLICY_V0_1_20260727.md`
- `ORDER_FLOW_HOOK_PREDICATE_CAPABILITY_REGISTRY_V0_1_20260727.csv`
- `ORDER_FLOW_HOOK_VARIANT_OBSERVATION_ROUTING_V0_1_20260727.csv`
- `PROJECT_MEMORY.md`
- 本checkpoint

### 検証結果

- Predicate Class 37件一意。
- Predicate 286件一意、Observation 236、Invalidation 50、未分類0。
- State binding 3,336件一意、variant coverage 365、base coverage 50。
- binding edgeはLOCATION_ARM 365、ADVANCE 1,876、TERMINAL 365、
  INVALIDATE 365、EXPIRE 365。FSM edgeとの過不足0。
- 無根拠な空ADVANCE 0。`TEMPORAL_SEQUENCE`の24件だけ市場Conditionなし。
- terminal方向不一致0、Condition ID／key参照error 0。
- Hook capability 88件一意。
- Hook route 25,664件一意、routed Hook 84、variant coverage 365。
- routeなしはG07、G08、G10、G11のみで、全件gap理由あり。
- runtime enabled 0、direct order authority 0。
- ユーザー例route 78、first-state wake 28。
- State Class registry SHA-256:
  `321819782668D02BD660F50FD5293F4094F885D2D8F5E5A6E651A012CE83A3DA`
- Predicate registry SHA-256:
  `6F1A541FA86F68AED9B3B9D015FB190FCDCC4F8E3310BE2593F600606FB958EC`
- State binding SHA-256:
  `23D818128DBFEED1B4F6501936ED282391EA339532258FD3E7C9A33B0E616AE8`
- State binding policy SHA-256:
  `D65FEABF282648CF0EE30755058B44F3C9929058BAF10AC8CA2777FE8625FD60`
- Hook capability SHA-256:
  `7B88B4BC9EDCC07A1AF8352CE3D36D8F4408A96F650C9CB6EDE220CB1EA6D571`
- Hook route SHA-256:
  `1ABD4D01909537B214115484BE8DB98AC3A9C907EFB3BF1BE92D599B187D277D`
- Hook policy SHA-256:
  `EA5D9C1236556F586A18E6228CC6D27927C221A75ED7CAD603E8BDF68C4AD361`
- source code、config、runtime、UI、raw data変更0。production採用0、注文0。

### Blockerの限定範囲

- blockerなし。
- 37 Class、286 Predicate、3,336 Binding、25,664 routeは全件`UNVALIDATED`。
- G07/G08/G11は対応variant location追加までrouteなし。
- G10はround-number専用Condition追加までblocked。
- external calendar、native MBO、OI 10秒pollの既知制約は継続。
- comparator、threshold、window、timeout、枚数、execution gateは未較正。

### 未完了

- replay event契約とObservation Instance state storeを定義する。
- 順序逆転、同一event再利用、timeout、途中反証、context-only hard advance、
  Hook direct orderを拒否するnegative test fixtureを作る。
- historical replayでvariantを採用／棄却／統合する。
- 採用variantだけthreshold、時機、枚数、risk／execution gateを較正する。

### 次の再開位置

replay event schema、Observation Instance append-only transition log、拒否理由codeを先に固定し、
ユーザー提示variantをgolden path／negative pathの最初のfixtureにする。