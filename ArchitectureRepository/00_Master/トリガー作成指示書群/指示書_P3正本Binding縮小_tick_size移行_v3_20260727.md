# 指示書: P3 正本binding縮小 + tick_size config移行 v3

作成日: 2026-07-27
改訂者: Claude web
原案作成: Codex（v2）
対象ブランチ: ui-refresh-v2
前提: P2完了（580 passed, 1 skipped）およびP3 Stage 1調査完了
参照: `P2_PIPELINE_WIRING_CHECKPOINT_20260727.md`、`指示書_P3正本Binding縮小_tick_size移行_v2_20260727.md`

---

## 0. 本書の位置づけ

本書はお館様の決裁を仰ぐための承認要求書である。決裁前にStage 2実装を開始してはならない。

### 0.1 v2からの変更点

| 項目 | v2 | v3 |
|---|---|---|
| 来歴 | 作成者: Claude web | 原案Codex、改訂Claude web |
| スコープ | binding縮小とtick_size移行を1本で扱う | P3-a / P3-b / P3-c に3分割 |
| producer新規実装（A案群） | Stage 2内に含意、完了基準と矛盾 | P3-cへ切り出し、P3から除外 |
| E02 | 決裁項目なしに変更対象へ記載 | D0として決裁項目化 |
| key生産可否 | 一部keyのみ記載（虫食い） | 突合表を成果物として必須化 |
| tick_size default | 未記載 | D4で3点（値・欠落時挙動・後方互換）を確定 |
| before/after | 行番号のみ | アンカー文字列ベースを必須化（§4.2） |
| 検証手順 | 「実測確認する」のみ | コマンドと期待値を明記（§6） |

### 0.2 web側の未検証範囲

本書§2の事実記述はv2（Codex作）からの継承であり、Claude webは実ファイル・正本CSVを
参照していない。行番号と内容の一致は**web未検証**である。
Stage 2着手時にCodexが再確認し、相違があれば実装前に報告すること。

---

## 1. スコープ分割

v2は「producer新規実装を伴うA案」と「既存検出器・収録基盤は無変更」という完了基準が
同一Stage内で衝突していた。以下に分割してこれを解消する。

### P3-a: tick_size config移行
binding決裁に依存しない。D4承認のみで単独実行可能。

### P3-b: 正本binding縮小
突合表作成 → D0-D3決裁 → CSV更新。producer実装は含まない。
未生産keyは正本から除去または「欠測omit」として明示するのみ。

### P3-c: producer新規実装
D1のA案（price response key追加）、D2のA案（wall差分producer）、
D3のA案（OI sample供給経路）に相当する作業。
**P3のスコープ外**とし、別指示書で扱う。

---

## 2. Stage 1調査の継承（web未検証）

### 2.1 正本binding

binding正本は
`ArchitectureRepository/00_Master/トリガー作成指示書群/ORDER_FLOW_VARIANT_STATE_CONDITION_BINDINGS_V0_1_20260727.csv`
である。

代表variantの現行行（v2記載、web未検証）:

- E01: CSV:363。candidateは`flow_price_divergence_active`、`cvd_change_5s`、
  `cvd_slope_5s`、`upward_progress_ticks_1s`、`downward_progress_ticks_1s`。
  contradictionは`upside_breakout_follow_through`、`downside_breakout_follow_through`。
- E02: CSV:364。candidateは`bid_absorption_like_active`、
  `ask_absorption_like_active`、`buy_no_progress_ratio_1s`、
  `sell_no_progress_ratio_1s`。contradictionはbid/ask passive defense failed。
- E03: CSV:365。candidateはbreakout attempt、progress、wall、refresh/pull、
  passive defenseの16 key。contradictionはbreakout failureとpassive defense failed。
- E98: CSV:368。candidateはOI、wall、refresh/pull、passive defenseの16 key。
  contradictionは`open_interest_change_5m`、`open_interest_pct_change_5m`、
  `bid_passive_defense_failed`、`ask_passive_defense_failed`。

### 2.2 P1/P2実生成keyとの突合（v2記載分）

- Producerは完全window時の`cvd_slope_5s`を生成する
  （`src/strategy_engine/ingestion/snapshot_producer.py:154-180`）。
- ProducerはFlowResponseから`trade_delta_30s`／`trade_delta_5m`を生成するが、
  300s `price_change`および`flow_price_divergence_active`は生成しない
  （同:144-152、214-219）。
- `bid_absorption_like_active`は`BUY_ABSORPTION`時にDecimal `1`として生成する
  （同:68-83）。
- Adapterはbook snapshotから`bid_wall_concentration_top10`を比率、
  `distance_to_nearest_bid_wall`をtick単位で生成する
  （`src/strategy_engine/ingestion/condition_adapter.py:65-87`）。
- OI keyはOI samplesがある場合のみ生成される
  （同:89-111）。P2 pipelineはOI samplesを供給していない。

### 2.3 v2で生産可否が未記載のkey

以下は代表variantのbindingに含まれるが、v2では生産可否が記載されていない。
これらを未確認のまま縮小判断を行うことはできない。

- E01: `cvd_change_5s`、`upward_progress_ticks_1s`、`downward_progress_ticks_1s`、
  `upside_breakout_follow_through`、`downside_breakout_follow_through`
- E02: `ask_absorption_like_active`、`buy_no_progress_ratio_1s`、
  `sell_no_progress_ratio_1s`、bid/ask passive defense failed（正確なkey名も未確定）
- E03: 16 keyの個別列挙が存在しない
- E98: 16 keyの個別列挙が存在しない

### 2.4 E98承認文書

`承認文書_E98修正版_20260727.md:17-20`で、
`downside_breakout_failure`はcandidate、`downside_breakout_follow_through`はcontradiction。
反映時期はSnapshot Producer完成後、Composite Synthesis Stage 2と合わせる（同:31-34）。

---

## 3. 決裁事項

### D0: E02の扱い（v2で欠落していた項目）

v2 §3-1はE02を変更対象に含めながら、決裁項目を用意していなかった。
次のどちらかを選ぶ。

- A案: E02もP3-bの縮小対象に含める。突合表でE02全keyの生産可否を確認した上で判断する。
- B案: E02は今回対象外とし、現行bindingを据え置く。

### D1: E01 price response key

- A案: `FlowResponseSnapshot(300s).price_change`用の新Tier A keyを正本に追加する。
  → **P3-c扱い**。P3-bではE01のprice response条件を現状のまま据え置き、変更しない。
- B案: E01を`cvd_slope_5s`と生産確認済みkeyだけの縮小bindingにし、
  price response条件を後続へ延期する。

推測でkey名・単位・thresholdを決めてはならない。

### D2: E03 wall崩壊差分

- A案: 前snapshot差分のproducerを追加する。差分window・freshness・reset契約が必要。
  → **P3-c扱い**。P3-bではE03の当該条件を据え置く。
- B案: E03を現行のpoint-in-time wall keyだけへ縮小し、崩壊差分を後続へ延期する。

既存の`bid_wall_concentration_top10`と`distance_to_nearest_bid_wall`を差分keyへ
無言で読み替えてはならない。

### D3: E98 OI供給

- A案: OI sample供給経路を追加し、E98をOI key中心に維持する。
  → **P3-c扱い**。P3-bではE98を据え置く。
- B案: OI keyも現行producer経路では欠測omitとし、E98縮小bindingを正本へ反映する。

### D4: tick_size config schema

`config.market.tick_size`をDecimal文字列として追加することを承認する。

**v2で欠落していた確定必要事項3点:**

- D4-1 default値: 現行`_BTCUSDT_TICK_SIZE`（`pipeline.py:637`）の実値を採用するか。
  実値は【要実測】であり、推測で埋めてはならない。
- D4-2 config欠落時の挙動: schema必須としてload時に例外を投げるか、
  defaultへフォールバックするか。
- D4-3 後方互換: `market`セクションを持たない既存config.yamlの扱い。

**変更候補:**

- `src/config.py:230-234`（SCHEMA）
- `config/config.yaml:9-12`（default）
- `ArchitectureRepository/40_Reference/YAMLReference_v3.4.md:22-25`（canonical sample）
- `tests/test_config.py:29-33`、`tests/webapp/test_push_broker.py:607-624`（fixture）
- `src/pipeline.py:384-400,935-949`（from_config供給）

既存の`Decimal(str(...))`変換パターン（`pipeline.py:966-969`）に合わせ、
`float()`は禁止する。

---

## 4. P3-a 実装手順（D4承認後のみ）

### 4.1 手順

1. D4-1〜D4-3の決定に従い、`src/config.py`のSCHEMAへ`market.tick_size`を追加する。
2. `config/config.yaml`へdefaultを追加する。
3. `ArchitectureRepository/40_Reference/YAMLReference_v3.4.md`のcanonical sampleを更新する。
4. `tests/test_config.py`、`tests/webapp/test_push_broker.py`のfixtureを更新する。
5. `src/pipeline.py`の`from_config`でconfigからDecimal tick sizeを取得し、
   Replay／Live双方のクラスへ渡す。**両クラスに同一の変更が必要**。
6. `_BTCUSDT_TICK_SIZE`の定義（`pipeline.py:637`）と全参照
   （同:552,603,1303,1463）を除去する。
7. `tests/test_pipeline_snapshot_wiring.py`へconfig tick sizeの供給確認テストを追加する。

### 4.2 before/afterの形式

**行番号単独の指示は不可**。Codexは各変更箇所について、
実ファイルから採取したアンカー文字列を含むbefore/afterコードブロックを
本指示書に埋め込んでから実装に入ること。外部参照は禁止する。

【要実測】以下の各アンカーは実ファイル確認後に埋めること。

- `src/config.py` SCHEMA定義のアンカー: 【要実測】
- `config/config.yaml` marketセクションのアンカー: 【要実測】
- `src/pipeline.py` `_BTCUSDT_TICK_SIZE`定義行のアンカー: 【要実測】
- `src/pipeline.py` Replay側`from_config`のアンカー: 【要実測】
- `src/pipeline.py` Live側`from_config`のアンカー: 【要実測】
- 参照4箇所（552,603,1303,1463）のアンカー: 【要実測】

---

## 5. P3-b 実装手順（D0-D3承認後のみ）

### 5.1 Step 1: 突合表の作成（決裁より先）

`/mnt/user-data/outputs/突合表_代表variant_key生産可否_20260727.csv` の
テンプレートを埋める。E01/E02は既知分を転記済み、E03/E98は行の追加が必要である。

全candidate/contradiction keyについて、以下を埋めること。

- 正本CSVの該当行番号
- 生産経路（producer / adapter / 未生成）
- 根拠のファイル:行番号
- 単位
- 欠測時の挙動

この表を提出し、お館様のD0-D3決裁を受けてからStep 2へ進む。
**表が未完成の状態でCSVを編集してはならない。**

### 5.2 Step 2: 正本CSV更新

1. D0-D3の決定に従い、対象variantのbindingをCSVで更新する。
2. A案が選ばれたkeyはP3-c送りとし、P3-bでは据え置く（変更しない）。
3. B案が選ばれたkeyのうち未生産のものを、candidate／contradictionから除去する。
4. before/afterの行内容を全件記録する。

---

## 6. 検証手順

### 6.1 tick_size除去の確認

```
cd Delta_Engine_Pro4web
grep -rn "_BTCUSDT_TICK_SIZE" . --include="*.py"
```

期待: 0件（exit code 1）。

### 6.2 config供給の確認

```
grep -rn "tick_size" src/pipeline.py src/config.py config/config.yaml
```

期待: Replay側・Live側の`from_config`双方でDecimal取得が確認できること。
`float(`が同一行に現れないこと。

### 6.3 回帰テスト

```
cd Delta_Engine_Pro4web
python -m pytest -q -p no:cacheprovider
```

期待値: P3-aで§4.1-7のテストを1件追加するため **581 passed, 1 skipped**。
「580以上」という曖昧な基準は用いない。追加テスト数が1件でない場合は
その数を明記した上で期待値を再計算すること。

### 6.4 実測確認

P3-b実施時は、pipelineを起動して実際に生成されたcondition keyのセットを取得し、
突合表の「生産経路」列と一致することを確認する。
不一致があれば実装を停止し報告する。

---

## 7. 完了基準

### P3-a
- `_BTCUSDT_TICK_SIZE`の定義・参照が0件（§6.1で確認）。
- `market.tick_size`がReplay／Live双方へDecimalで供給される（§6.2で確認）。
- `float()`不使用。
- 回帰: 581 passed, 1 skipped（§6.3）。

### P3-b
- 突合表が全key埋まっている。
- 正本CSVの変更がD0-D3承認内容と厳密に一致する。
- 承認範囲外のkeyに変更が入っていない。
- 実測keyセットと突合表が一致する（§6.4）。

### 共通
- runtime有効化0、発注権限0を維持する。
- 既存検出器、raw data、収録基盤は無変更。
- commit/pushはお館様の指示まで行わない。

---

## 8. 停止条件

- D0-D4の承認が揃っていない。
- 突合表に空欄がある状態でCSV編集が必要になった。
- key名、単位、window、差分、OI供給が正本から一意に決まらない。
- config schemaとcanonical YAMLReferenceに齟齬がある。
- 未生産keyを実装済みとしてbindingへ残す必要が生じる。
- 既存検出器、runtime、発注系、収録基盤の変更が必要になる。
- §2の継承事実と実ファイルに相違がある。
- P3-c相当の作業が必要になった。

上記の場合は実装を停止し、ファイル:行番号付きで報告する。
