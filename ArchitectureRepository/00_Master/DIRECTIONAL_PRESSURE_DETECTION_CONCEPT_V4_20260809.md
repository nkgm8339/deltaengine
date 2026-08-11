# 方向性圧力検出 — 設計コンセプト v4

## 0. なぜこれを作るのか

大口を見つけて、その方向に乗って、利益を取る。これがオーダーフロートレードの目的であり、DeltaEngineの存在理由である。

DeltaEngineにはAbsorption、Imbalance、Flow Price Response、DOMなど、大口がいることで起きる現象を観測する機能がある。しかし肝心の「大口を見つける」機能がない。原因を見ずに結果だけ見ている。大口が見つからなければ、吸収も偏りも方向判断も、すべて宙に浮く。

この文書は、その欠落を埋めるための設計コンセプトである。実装指示書は本文書の承認後に別途作成する。

## 1. Binance先物における大口検出の制約

### 1.1 なぜ個別約定のサイズでは見つからないか

Binance先物では大口は注文を分割して投入する。個々の約定サイズは雑魚と区別がつかない。同方向の約定が集中しても、1人の大口の分割執行か50人の雑魚の偶然の集中かを、公開データからは区別できない。

### 1.2 では何を見つけるのか

相乗りする側から見れば、大口1人か雑魚50人かの区別は不要である。方向が通るなら乗る対象になる。

見つけるべきは「大口本人」ではなく「市場を動かしている方向性の圧力」である。大口がいる可能性が高い痕跡を複数のデータソースから集め、圧力が成立しているかを判定する。

### 1.3 正直な自己定義

このシステムは2つの段階で構成される。

**Pressure Detection** — どちら側からどれだけ攻撃が来ているかを検出する。

**Pressure Outcome** — その圧力によって価格が実際に通ったか（continuation）、それとも受け止められたか（absorption/failure）を観測する。

この2つは別の事象である。強烈な買い圧力が存在しても、上に巨大な受動売りがいれば価格は通らない。「BUY PRESSURE DETECTED + CONTINUATION_FAILED」は完全に正常な状態であり、むしろオーダーフローではこの失敗そのものが重要な情報になる。

5痕跡の枠組みを採用する正当化は、「単純なdelta/momentumベースラインに対して増分予測力があるか」で立証する必要がある。立証できなければ、この枠組みは不要であり、deltaだけで足りる。

## 2. 観測可能な痕跡の分類

### 2.1 Directional Flow（方向あり）

aggTradeとdepthから、方向性のある攻撃を検出する。ここで2つの独立した情報を分離する。

**trade_intensity** — 単位時間あたりの総約定量。「異常なactivityが発生しているか」を測る。方向は問わない。

**delta_imbalance** — 買い約定量と売り約定量の偏り。「そのactivityがどちら側に偏っているか」を測る。

この2つは別の情報である。trade_intensityが高くdelta_imbalanceが低ければ、双方向の激しい戦いであり、一方的な圧力ではない。trade_intensityが高くdelta_imbalanceも高ければ、一方的な攻撃が来ている。

保存するのはraw/continuous値を一次データとし、ラベル（HIGH等）は派生とする。

```
# 一次データ（必ず保存）
trade_volume: "152.300"
trade_notional: "9138000.00"
trade_count: 47
trades_per_second: "78.3"
volume_percentile: "99.2"
notional_percentile: "99.4"
robust_z_score: "4.72"
delta: "+128.500"
delta_ratio: "+0.844"

# 派生ラベル（一次データから計算、判定に使わない）
trade_intensity_label: HIGH
```

加えて、累積notionalが分布の外れ値かどうかを評価する。

**板の変化** — 約定側・反対側それぞれの板の変化を記録する。ただし板の変化には複数の原因があり、一括りにしない。

板の観測分類は、BUY/SELLについて対称な構造を持つ。内部的にはdirection-normalized表現を併用する。

BUY pressureの場合:

| raw分類 | direction-normalized | 意味 |
|---|---|---|
| ASK_CONSUMED | AGGRESSOR_SIDE_CONSUMED | 攻撃側の板が約定で食われた |
| ASK_CANCELLED | AGGRESSOR_SIDE_CANCELLED | 攻撃側の板がキャンセルで消えた |
| ASK_REPLENISHED | AGGRESSOR_SIDE_REPLENISHED | 攻撃側の板が回復した |
| BID_ADDED | SUPPORT_SIDE_ADDED | 支持側の板が増加した |
| BID_CANCELLED | SUPPORT_SIDE_CANCELLED | 支持側の板が減少した |

SELL pressureでは完全に鏡像になる（ASK↔BID）。direction-normalized表現を使えば、BUY/SELLを区別せずに分析できる。

初期実装で原因の判別ができない場合:

- BOOK_REDUCED_UNCLASSIFIED — 板が減少したが原因を判別できない
- BOOK_MOVED — 板が別価格帯に移動した
- BOOK_UNOBSERVED — 板snapshotが取得できなかった
- BOOK_DATA_INVALID — depth再同期中、sequence gap、stale期間

初期実装ではBOOK_REDUCED_UNCLASSIFIED / BOOK_UNOBSERVED / BOOK_DATA_INVALIDから始めてよい。判別ロジックの追加で分類を細分化できる構造にしておく。

**清算の方向** — forceOrderが出た方向。ただし後述の従属性制約あり。

### 2.2 Reinforcement（方向なし補強）

- **OI変化** — 未決済建玉の増減。増加は「新規マネーが入っている」、減少は「既存ポジションの決済」を示す。しかし買い新規か売り新規かはOI単独では判らない。方向判定の対象に含めない。方向なしの補強として記録する。
- **約定間隔の規則性** — 約定の時間間隔が統計的に規則的かどうか。アルゴリズム執行の推定には使わない。INTERVAL_REGULARITYとして記録する。

### 2.3 独立／従属の分離

清算（forceOrder）はaggTradeストリームにも成行注文として出現する。約定の方向集中と清算は独立した痕跡ではなく、一部が同一事象である。独立な痕跡として重み付けすると過大評価になる。

清算は次のように扱う。

- 約定集中の構成要素として二重計上しない
- 有無と方向のみを弱シグナルとして記録する（LIQUIDATION_PRESENT / LIQUIDATION_ALIGNED / LIQUIDATION_OPPOSITE / LIQUIDATION_UNOBSERVED）
- Binanceの@forceOrderはスロットリングで間引かれ、全清算を配信しない【要確認: 1symbol/1件 per ~1000ms程度】ため、「量」は信頼しない

### 2.4 板反応の観測制約

depth差分ストリームは純増減しか与えない。ある価格の板が減った理由が「約定で食われた」のか「キャンセルで逃げた」のかを区別するには、depth差分とaggTradeの突合（reconciliation）が必要である。この突合ロジックは本設計の最難関の一つである。

観測に必要な定義:

- 観測対象の価格帯: cluster約定が発生した価格帯
- 約定前の基準数量: T_start直前のdepth snapshot（source_time基準で直前のdepth event。received_timeではなくsource_timeを使う）
- 回復判定の時間窓: 定義必要（未決）
- 価格移動時の追跡: cluster完了時の最良気配を基準に再定義
- staleガード: depth再同期中（既存のsync ownership / rearm failures問題と直結）はBOOK_DATA_INVALIDとして板証拠を無効化する

partial depth（top-N levels）の場合、窓外の補充は観測できない。この制約を明記する。

## 3. 時間モデル

### 3.1 問題

4つのデータソースの時間解像度が桁で異なる。

| ソース | 粒度 | 配信方式 |
|---|---|---|
| aggTrade | ミリ秒 | イベント駆動 |
| depth | ~100ms差分 | ストリーム |
| OI | 数秒〜数十秒 | REST poll |
| forceOrder | イベント駆動 | ストリーム（スロットリング有） |

「同一時間帯に痕跡が重なる」の「時間帯」を定義しなければ、痕跡の照合は成立しない。

さらに、「市場でいつ圧力が成立したのか」と「DeltaEngineがいつそれを知ることができたのか」と「知ったあと価格はどれだけ残っていたのか」は3つの別の問いであり、1つのT₀で代表してはならない。

### 3.2 4つの時刻

episodeの時間軸は4つの時刻で構成する。

```
T_start ─── T_trigger ─── T_detect ─── T_end
```

**T_start** — cluster構成開始。最初のtrade event_time。この時点ではシステムはclusterだと知らない。

**T_trigger** — 条件が初めて成立したsource_time。例えば累積delta imbalanceが閾値に達した瞬間のtrade event_time。市場上でここから先が「圧力が成立した後」の世界。

**T_detect** — DeltaEngineが実際に判定可能になったreceived_time。通信遅延・処理遅延を含む。実際に相乗り可能になるのはここから。

**T_end** — episode終了。終了条件（Section 4.4参照）に到達した時刻。

### 3.3 時刻の用途分離

| 用途 | 使う時刻 |
|---|---|
| Pressure Detection特徴量 | T_trigger以前のsource_time情報のみ |
| リアルタイム性能評価 | T_detect以降 |
| 市場構造研究 | T_start → T_trigger（別途分析） |
| signal age | T_detect - T_trigger |

signal age（= T_detect - T_trigger）を記録することで、「400ms確認すると精度+8%だがMFEの35%を既に失っている」のような速度 vs 確度の評価が可能になる。

### 3.4 時間窓照合

T_triggerを基準に前後に時間窓を切り、各ソースの観測値をその窓へ写像する。

```
[T_trigger - Δt_pre] ─── T_trigger ─── [T_trigger + Δt_post]
        前区間                基準                後区間
```

各痕跡は3区間のいずれに属するかを記録する。

- **前区間**: T_trigger以前の状態（板の初期値、OIの初期値）
- **基準**: T_start〜T_triggerのcluster特徴量
- **後区間**: T_trigger以降の変化（板の回復有無、OI変化、清算発生）

### 3.5 OIの帰属不能問題

OIはREST pollであり、poll窓内に複数のclusterが発生した場合、OI変化を特定のclusterに帰属できない。

この問題を「脚注」として流さない。設計上の構造的制約として扱う。

OIの状態は次のように定義する。

- OI_UP — poll間でOIが増加した
- OI_DOWN — poll間でOIが減少した
- OI_FLAT — 変化なし（閾値定義必要）
- OI_UNATTRIBUTABLE — poll窓内に複数事象があり、当該clusterへの帰属不能
- OI_UNKNOWN — poll失敗、データ欠損

OIは方向なし・帰属不能な場合がある弱い補強として位置づける。圧力判定の必須条件にしない。

### 3.6 各イベントの時刻フィールド

全イベントに次の時刻を持たせる。

- source_time — データソース側のタイムスタンプ
- received_time — DeltaEngineがデータを受信した時刻
- alignment_window_sec — 照合に使用した窓幅
- data_quality — COMPLETE / PARTIAL / STALE / MISSING
- missing_reason — 欠損理由（該当時のみ）

market-event timelineはsource_time基準で構築する。received_timeは遅延・品質評価に使う。source_time順序とreceived_time順序が逆転した場合の扱いは未決事項とする。

## 4. pressure episodeモデル

### 4.1 episodeの定義

個々の痕跡検出ではなく、pressure episodeを判定の単位とする。

episodeは開始トリガーで始まり、終了条件で閉じる。

### 4.2 開始トリガー

clusterを唯一の入口に固定しない。以下のいずれかでepisodeを開始できる。

- TRADE_CLUSTER_TRIGGER — 同方向の約定累積が分布の外れ値に達した
- BOOK_CHANGE_TRIGGER — 板の一方的な減少が閾値を超えた
- LIQUIDATION_TRIGGER — 清算が発生した
- OI_CHANGE_TRIGGER — OIの急変が閾値を超えた

初期実装でTRADE_CLUSTER_TRIGGERのみに限定する場合、文書に「cluster起点以外の圧力は初期対象外。取りこぼす圧力パターンとして、長時間の緩やかな偏り、板が先に動くケース、OIや清算が先行するケースがある」と明記する。

### 4.3 episodeの構造: Pressure Detection → Price Response → Outcome

episodeは3層で構成される。

```
                MARKET DATA
                     │
        ┌────────────┴────────────┐
        │                         │
   Directional Flow          Reinforcement
        │                         │
 aggTrade / depth          OI / liquidation
        │                         │
        └────────────┬────────────┘
                     ↓
              PRESSURE EPISODE
                     │
             BUY / SELL pressure
                     │
                     ↓
              PRICE RESPONSE
              /            \
        EFFICIENT          INEFFICIENT
           │                   │
     continuation       absorption / failure
           │                   │
           └────────┬──────────┘
                    ↓
                 OUTCOME
             1m / 3m / 5m
              MFE / MAE
```

**第1層: Pressure Detection** — 圧力の存在を検出する。どちら側からどれだけ攻撃が来ているか。

**第2層: Price Response** — その圧力に対して価格がどう反応したか。ここで圧力効率を測る。

**第3層: Outcome** — 固定horizonでの結果を記録する。

この3層は時間的に順に発生する。第1層で圧力を検出しても、第2層で価格が動かなければcontinuation failureであり、それ自体が重要な情報である。「BUY PRESSURE DETECTED + CONTINUATION_FAILED」は正常な状態として扱う。

### 4.4 episode終了条件

episodeは以下のいずれかで終了する。

- MAX_EPISODE_DURATION — 最大持続時間に到達（値は未決）
- INACTIVITY_TIMEOUT — 同方向のtrade activityが一定時間途絶えた（値は未決）
- DIRECTION_REVERSAL — 反対方向のdelta imbalanceが閾値を超えた
- NEW_OPPOSITE_TRIGGER — 反対方向のトリガーが発火した

例えば、

```
BUY cluster → 200ms静か → BUY cluster → 300ms静か → BUY cluster
```

をINACTIVITY_TIMEOUTの設定によって1 episodeとするか3 episodesとするかが変わる。この選択は統計に直接影響する。

episode merge/split条件（近接する同方向episodeを統合するか）は未決事項とする。

### 4.5 圧力効率（Pressure Efficiency）

同じdelta +100 BTCでも、価格が+$150動いた場合と+$3しか動かなかった場合では意味が全く異なる。後者は大量に買われているのに価格が動かない——受動側に吸収されている。

圧力効率は単一の値に潰さず、計算元のraw値を保存する。式は研究段階で定義する。

```
# 一次データ（必ず保存）
directional_volume: "128.500"
directional_notional: "7710000.00"
net_delta: "+128.500"
delta_ratio: "+0.844"

response_100ms: "+12.30"
response_250ms: "+28.70"
response_500ms: "+45.10"
response_1s: "+62.40"

# 研究段階で定義する派生指標の例
# efficiency_h = return_h / normalized_directional_flow
```

データを先に保存し、式は後から決める。

圧力効率は既存のAbsorption / Flow Price Responseとの接続点になる。圧力効率が低い episode（大量に攻撃したが価格が動かない）は、Absorptionと整合的な状態を示す。圧力効率が高い episodeは、Flow Price Responseが反応している状態と整合的である。「同一」とは断定しない。

市場で本当に重要なのは「誰が何BTC買ったか」だけではなく「その攻撃に対して価格がどれだけ動いたか」である。攻撃側だけでなく、受け止めている側の大口も見える。

### 4.6 証拠ベクトル

痕跡を単一スコアに圧縮しない。数えない。episodeごとに証拠ベクトルとして保存する。

```
episode_id: "..."
trigger: TRADE_CLUSTER_TRIGGER
direction: BUY

# 時間モデル
T_start: "2026-08-09T18:00:00.000Z"
T_trigger: "2026-08-09T18:00:00.600Z"
T_detect: "2026-08-09T18:00:00.612Z"
T_end: "2026-08-09T18:00:01.200Z"
signal_age_ms: 12

# Directional Flow（一次データ）
trade_volume: "152.300"
trade_notional: "9138000.00"
trade_count: 47
trades_per_second: "78.3"
volume_percentile: "99.2"
notional_percentile: "99.4"
robust_z_score: "4.72"
delta: "+128.500"
delta_ratio: "+0.844"

# Book（direction-normalized）
book_aggressor_side: BOOK_REDUCED_UNCLASSIFIED
book_support_side: SUPPORT_SIDE_ADDED
book_data_quality: PARTIAL

# Reinforcement
oi_state: OI_UP
oi_attributable: false
liquidation: LIQUIDATION_ALIGNED
liquidation_independent: false
interval_regularity: LOW

# Price Response（raw値）
response_100ms: "+12.30"
response_250ms: "+28.70"
response_500ms: "+45.10"
response_1s: "+62.40"

# Data Quality
data_quality: PARTIAL
contradictions: []
```

evidence_countは持たない。証拠は等価ではなく、数で判定するとSection 5の統計検証の意味が薄れる。判定ラベル（PRESSURE_SUPPORTED等）を後から付ける場合も、条件を固定ルールで定義し、元の証拠ベクトルを必ず残す。

## 5. 検証設計

### 5.1 ラベル漏洩の排除

**致命的制約:** トリガー特徴量と評価アウトカムを時間的・変数的に厳密分離する。

トリガーに「価格が一方向に進行し続ける」を含めると、「候補後に価格が進行したか」という検証は価格の自己相関を測っているだけになる。

分離ルール:

- トリガー特徴量: T_trigger以前にsource_time上で利用可能な情報のみ
- 評価アウトカム: T_trigger以降の固定horizonでの価格変化のみ
- トリガー期間と評価期間は重複しない

評価は2つの基準で行う。

**理論上の予測能力:** 市場データ自体にsignalがあるか。T_trigger基準で評価する。

**実システムの予測能力:** 通信・処理遅延込みでもsignalが使えるか。T_detect基準で評価する。

この分離により、「市場構造上はedgeがあるがDeltaEngineの遅延で利用不能」と「遅延込みでも使える」を区別できる。

### 5.2 ベースライン

比較対象:

- **無条件ベースライン**: ランダム時刻からの価格変化分布
- **matched baseline**: 同一セッション・同一volatility regime・類似spread・類似流動性からサンプリングしたランダム時刻の価格変化分布。「単にボラが高い時間に検出しているだけ」を排除する
- **deltaのみベースライン**: delta集中が閾値を超えた時点からの価格変化分布
- **本システム**: 痕跡複数重なり時点からの価格変化分布

本システムの正当化は「deltaのみベースラインに対する増分予測力」の有無で判定する。増分がなければ、5痕跡の枠組みは不要であり、deltaだけで足りる。

### 5.3 評価指標

**固定horizon:** 1分後、3分後、5分後の価格変化（追加可）

**MFE（Maximum Favorable Excursion）:** 評価期間内にdirection方向へ最大どこまで進んだか。

**MAE（Maximum Adverse Excursion）:** 評価期間内に逆方向へ最大どこまで振れたか。

**time_to_MFE:** MFEに到達するまでの時間。

**time_to_MAE:** MAEに到達するまでの時間。

**MFE/MAE ratio:** 有利方向への最大進行と不利方向への最大振れの比率。

固定horizonだけでは相乗り性能を正しく測れない。MFE/MAEはエントリーロジックの設計ではなく、検出した圧力の後に市場がどう動いたかを正確に評価するための指標である。time_to_MFE/MAEは速度 vs confirmationの研究にも使える。

- 基準価格: T_trigger時点の最良気配仲値（理論評価）/ T_detect時点の最良気配仲値（実システム評価）
- episode内重複: 同一episodeから複数候補が出た場合、episode単位で1回のみ評価する
- 候補連続時の独立性: 前のepisodeの評価窓と次のepisodeのトリガーが重なる場合、後者を除外するか、重複をフラグする
- データ欠損: 評価horizon内にデータ欠損がある場合は除外し、除外数を記録する
- 時間帯・流動性別: 評価結果を分割して集計する

### 5.4 過学習防止

痕跡の組み合わせ × 時間帯 × 流動性帯をlive蓄積データで探索すると、多重比較で偽相関を拾う。

規定:

- out-of-sample分割: 蓄積データの時系列順で学習期間と評価期間を分離する。未来データを学習に使わない
- 最小サンプル数: 各条件の評価に必要な最小episode数を定義する（未決）
- 更新頻度: 検出条件の更新は最短でも定義必要な期間ごと（未決）
- 有意性: 増分予測力の有意性検定方法を定義する（未決）
- フィッティング結果の扱い: 「改善された」条件は仮説として記録し、次のout-of-sample期間で確認するまで適用しない

## 6. 遅延と実効性のトレードオフ

### 6.1 問題

「相乗りする」が目的であれば、確認を増やすほど参入が遅れる。OIのpoll待ち＋板の回復窓確認を終える頃には、動きが終わっている可能性がある。

一方で、cluster発生直後に入ったら、吸収されて死ぬかもしれない。速度とconfirmationのトレードオフ自体が検証対象である。

### 6.2 二層分離

早期トリガー（低遅延）と事後確証（高確度）を分離する。

**早期トリガー層:**

- aggTradeのtrade_intensityとdelta_imbalanceで発火
- 低遅延候補としてリアルタイム利用可能

**事後確証層:**

- OI変化、板反応、清算との照合
- 取得遅延を記録する
- episodeの記録と検出条件の改善に使用

事後確証のどこまでがリアルタイム利用可能かは、検証結果に基づいて決定する。「早期トリガーしかエントリーに使えない」とは断定しない。

signal age（= T_detect - T_trigger）を使い、各確認段階でのMFE残存率を測定することで、速度 vs confirmationの最適点を検証する。

## 7. 既存システムとの関係

### 7.1 既存機能との接続

圧力効率（Section 4.5）は既存のAbsorption / Flow Price Responseとの接続点である。

- 圧力効率が低い → Absorptionと整合的な状態
- 圧力効率が高い → Flow Price Responseが反応している状態と整合的

本システムは、これらの既存機能にepisode単位の文脈（「その吸収はどれだけの圧力に対してなのか」）を追加する。

### 7.2 既存の未解決問題との接続

depth再同期中（sync ownership / rearm failures）は板データがstaleになる。stale期間中はBOOK_DATA_INVALIDとして板証拠を無効化する。RTUIF問題が未解決の間、板証拠の信頼性は制限される。

### 7.3 分布の非定常性

「分布の外れ値」の判定に使う分布窓は、ボラティリティ、ファンディングレート、セッション（アジア/欧州/米国）で特性が変わる。静的閾値はドリフトする。regime依存の定義が必要（未決）。

### 7.4 depth×aggTrade突合

板が食われたのかキャンセルで逃げたのかの区別には、depth差分とaggTradeの突合が必要である。これは本設計の最難関であり、partial depth（top-N levels）の制約もある。突合ロジックの設計は別途行う。source_time基準でmarket-event timelineを構築し、received_timeは遅延・品質評価に使う。

## 8. 実装順序

deltaだけを超えなければ全部不要——と文書自身が宣言している。したがって最初にdelta-only baselineを完成させ、その後に痕跡を一つずつ追加してincremental valueを測る。

1. Event time model — 全データソースのsource_time / received_time / data_qualityを統一する。T_start / T_trigger / T_detect / T_endの記録基盤を作る
2. Raw event persistence — 一次データの保存形式を確定し、永続化する
3. TRADE_CLUSTER_TRIGGER — 初期トリガーを実装する。trade_intensityとdelta_imbalanceを分離して記録する（cluster起点以外の圧力は初期対象外と明記）
4. Episode lifecycle — episodeの開始・終了・状態遷移を実装する
5. Outcome tracker — episode単位でT_trigger/T_detect以降の固定horizon + MFE/MAE + time_to_MFE/MAEを追跡する。基準価格はT_trigger時点（理論）とT_detect時点（実システム）の両方で記録する
6. Baseline evaluator — 無条件 + matched + deltaのみベースラインを構築し、delta-onlyに対する増分を評価する

**ここでdelta-only baselineとの比較を行う。増分が確認されなければ、以降のステップの必要性を再評価する。**

7. Book — 板反応を観測分類として照合する（BOOK_REDUCED_UNCLASSIFIEDから開始）。staleガード必須。delta + bookの増分を測定する
8. OI — 方向なし・帰属不能ありの弱い補強として照合する。delta + book + OIの増分を測定する
9. Liquidation — 有無・方向のみの弱シグナルとして照合する（aggTradeとの二重計上を排除）。delta + book + OI + liquidationの増分を測定する
10. Pressure Efficiency研究 — raw値から圧力効率の定義を探索する
11. 速度 vs confirmation — signal ageの各段階でのMFE残存率を比較する
12. 条件別・流動性別に成績を集計する。out-of-sample分割と最小サンプル数を適用する
13. 増分予測力が確認された場合のみ、検出条件を仮説として記録し、次のout-of-sample期間で確認する

## 9. 未決事項

### 時間モデル
- T_start / T_trigger / T_detect / T_endの厳密なイベント定義
- source_time順序とreceived_time順序が逆転した場合の扱い
- late event許容時間
- signal ageの測定方法

### Episode
- cluster検出の窓幅・終了条件・分布パラメータ
- trade_intensityの異常度閾値
- delta_imbalanceの閾値
- episode終了条件の各パラメータ（MAX_EPISODE_DURATION, INACTIVITY_TIMEOUT等）
- episode merge/split条件
- 初期実装でcluster以外のトリガーを含めるか

### 時間窓照合
- Δt_pre / Δt_postの値
- OI pollの帰属不能判定の窓幅
- 板回復判定の時間窓

### 検証
- MFE/MAE計測の最大期間
- 最小サンプル数
- out-of-sample分割の期間
- 検出条件更新の最短間隔
- 増分予測力の有意性検定方法
- matched baselineの条件定義（session / vol regime / spread / liquidity）

### 圧力効率
- price_responseの測定horizon
- directional_flowの正規化方法
- raw特徴量とderived labelの保存方針

### 既存システム
- regime（ボラ/ファンディング/セッション）の分割定義
- depth×aggTrade突合ロジックの設計
- staleガードの判定条件（RTUIF問題との接続）
- direction-normalized book representationの実装方式

## 10. この文書で扱わないこと

- 実装の詳細（ファイル配置、関数設計、テスト項目）
- 既存コードの変更差分
- Codexへの指示
- パラメータの確定値
- エントリー・エグジットのロジック
- 売買シグナルや注文実行への接続
