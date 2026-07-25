# DeltaEngine 5M/10M 引き継ぎ書

作成日: 2026-07-25  
状態: Entry Spec v1オフライン評価完了。HFM発注はNO-GO。再開時は本書を最初に読むこと。

## 0. 最重要結論

このプロジェクトの目的は、1Mで完成しているオーダーフロー観測の特性が、HFMという別の戦場で5M/10Mの観測時間でも成立するかを検証することである。

単なるBUY/SELL状態を売買指示に変えることではない。

### 次担当への最重要指示

次にこの案件を引き継ぐ担当は、最初にエントリー判断を考えること。これが最重要議題であり、システム全体の中心である。

- 何を観測したら入るのか
- 買い攻撃のどの局面で入るのか
- 価格停滞・継続・失速・反転/突破をどう区別するのか
- 入った直後に何が起きたら仮説を否定するのか
- HFMスプレッドを払ってもなお入る価値があるのか

パイプライン、JSONL、UI、MT5接続、ログ基盤は、エントリー仮説を正しく再現・検証するために必要な実装である。ただし、何を再現・検証するのかを先に定義し、実装を目的化してはならない。

「買いは科学、売りは芸術」という原則を踏まえ、まず買いエントリーの再現可能な条件と、売り・撤退の判断を定義する。コード作業はその後に行う。

今回、`BUY_EFFECTIVE` / `SELL_EFFECTIVE` をそのまま発注トリガーにしようとした案は誤りとして撤回する。これはオーダーフローの連続構造を無視した設計逸脱であり、再利用・実装してはならない。

### 0.1 Entry Spec v1の結論（2026-07-25 16:11 JST）

コードより先に、次の三入口を事前固定してオフライン評価した。

- `ATTACK_V1`: 攻撃開始。pressure sideへ入る早期対照
- `PERSIST_PRESSURE_V1`: `AGGRESSION → NON_RESPONSE → SUSTAINED_CONFLICT`を
  観測した時点でpressure sideへ入る早期研究候補
- `RESOLUTION_CONFIRMED_V1`: 上記三段階後の突破ならpressure side、
  Defender reversalなら反対sideへ入る主候補

主候補のBUYは、次のどちらかだけである。

1. BUY攻撃の継続停滞後に`BUY_EFFECTIVE`を初めて確認
2. SELL攻撃の継続停滞後に`SELL_TRAPPED`を初めて確認

単発`BUY_EFFECTIVE`は主entryではない。BUY攻撃が`BUY_TRAPPED`ならBUYせず、
SELL候補とする。SELLは完全に対称である。

entry後は、trade sideの`TRAPPED`、反対sideの`EFFECTIVE`、data gap、
および継続停滞中の価格境界を逆へ抜けた時点を仮説否定と定義した。

固定cutoff `2026-07-25T06:40:00Z`、600秒重複purge、HFM proxy cost 20 USD／
1.5倍stress 30 USDで評価した。60秒観測の主候補はraw 35件、purge後27件、
有効Outcome 18件だった。

30 USD stress後中央値:

- 5分: `-5.668bps`、positive net 1/18
- 10分: `-5.397bps`、positive net 0/18
- 価格無効化で撤退: 5分`-6.623bps`、10分`-6.834bps`、positive net 0/18

解放確認entryはpaired EpisodeでAttackより5分`-3.170bps`、10分`-2.775bps`、
Persistより5分`-2.149bps`、10分`-1.682bps`遅かった。しかしAttackとPersistも
30 USD stress後中央値はすべて負だった。

したがって現在の運用判定は **`NO_GO_FOR_HFM_ENTRY_V1`** である。

これは1.5186日の探索標本に対する発注NO-GOであり、注文フロー原理全体の統計的棄却ではない。
30日、purge後200 Episode、untouched test、HFM同一時計Bid／Askを満たしていない。
MT5 bridge、LIVE発注、自動売買シグナルへ進んではならない。

## 1. ユーザーの問題意識

- 1Mコアはスプレッドほぼゼロなら実践可能性がある。
- BinanceとHFMは戦場が異なる。BinanceのデータをそのままHFMに移せない。
- HFMでは1Mがスプレッド負けする。
- 30Mならレンジはあるが、注文フロー取引の性質を失う。
- 5M/10Mは単純に足を伸ばすのではなく、次のEpisodeの観測時間を伸ばす仮説である。

```text
買い攻撃 → 価格停滞 → 買い継続 → 失速 → 反転
```

- 1Mロジックで動きつつ、エントリーの滞留時間だけを5M/10Mへ延ばすと負け戦の確率が上がる可能性がある。
- 最重要課題は、5M/10Mでも注文フローの特性を保ったままHFMコストに耐えるかであり、システムを作ること自体ではない。

## 2. 完成・確認済みの研究基盤

### 2.1 変更してはいけない完成機能

- 1M Flow Price Response
- 完成済みの3段チャート
- 既存の1Mコアロジック

ユーザーの明示依頼なしに改善・変更しない。

### 2.2 5M/10M研究基盤

- `src/orderflow/orderflow_episode.py`
  - AGGRESSION、NON_RESPONSE、SUSTAINED_CONFLICT、AGGRESSOR_BREAKTHROUGH、DEFENDER_REVERSAL等を扱う純粋なEpisode状態機械。
  - ギャップ、時刻逆行、未解決Episodeを扱う。
- `src/orderflow/episode_dataset.py`
  - 因果的な300秒/600秒フォワードラベル。
  - `OK`、`MISSING_OUTCOME`、`DATA_GAP`等を分離。
- `src/orderflow/hfm_episode_outcome.py`
  - HFM Bid/Askを使い、BUYはAsk→将来Bid、SELLはBid→将来Askで評価。
  - HFMローカル時刻とBinanceイベント時刻を危険に結合しない。
- `src/orderflow/manual_execution_log.py`
  - 約定・見送り・拒否・QUOTE_STALEを検証する記録型。
- `src/orderflow/manual_execution_ledger.py`
  - 重複IDを拒否するappend-only JSONL ledger。
- `tools/build_orderflow_manifest.py`
  - RAWデータの行数、ID、欠損、ギャップ監査。
- `tools/audit_manual_sessions.py`
  - 手動ledgerをUTCセッション別に集計する読み取り専用ツール。
- `src/orderflow/episode_entry.py`
  - Entry Spec v1の因果的candidate抽出、方向反転、600秒重複purge、
    MFE／MAE、cost hurdle先着、price invalidation、撤退Outcomeを扱う純粋研究器。
- `tools/evaluate_episode_entries.py`
  - 安定Parquetだけを時刻固定して読み、1M観測と5M／10M outcome、
    20／30 USD proxy、固定UTC sessionを分離したJSON／Markdownを生成。

### 2.3 自動SHADOW記録

- `src/orderflow/shadow_signal_recorder.py`
- `webapp/main.py` のFlow Response callbackへ接続済み。
- 保存先:

```text
Delta_Engine_Pro4web/data_05M/manual/flow_response_shadow.jsonl
```

- 実際に再起動後のログ生成を確認済み。
- 直近ログには180秒、300秒、1800秒窓が存在。
- 各行は `status=SHADOW`、`order_created=false`。
- 手動で記録を取る必要はない。

## 3. 構造検証の既知結果

対象: `data_05M/parquet/flow_response_events/**/*.parquet`

- 60秒窓:
  - BUY_EFFECTIVE平均価格変化 +3.70bps
  - BUY_STALLED +0.35bps
  - BUY_TRAPPED -1.96bps
- 300秒窓:
  - BUY_EFFECTIVE +7.72bps
  - BUY_STALLED +0.24bps
  - BUY_TRAPPED -1.95bps
- SELL側は概ね符号が逆。

これは攻撃・停滞・罠/反転が記述統計上分離されることを示すだけであり、HFMスプレッド控除後の利益、独立約定成績、将来再現性を証明しない。

600秒イベントは既存イベントファイルに不足していたため、10M相当は未評価。

## 4. HFM時刻・データに関する重要事項

- 既存HFM quote期間と現在のBinance RAW期間は重なっていない。
- HFM source/local clockには約3時間の差が見られた。
- オフセットを推測してHFM評価へ結合しない。
- HFMの同一ローカル時刻を正規化できるデータが必要。
- HFMの約定・拒否・スプレッド・遅延を含む実測が必要。

## 5. MT5関連の現状（要注意）

### 5.1 追加されたファイル

- `mt5/HFMSafeTestExecutor.mq5`
- `mt5/HFMSafeTestExecutor_README.md`
- `tools/write_hfm_order_command.py`

### 5.2 現在の扱い

- EAは初期値SHADOW。
- 0.01 lot制限、単一ポジション、MagicNumber、SL必須、緊急停止flag、監査ログの枠を持つ。
- MetaEditor/MT5実環境でのコンパイル確認は未実施。
- HFMデモ口座は存在しない。
- 実口座への注文は一件も送っていない。
- DeltaEngineのFlow Responseを自動売買シグナルへ接続していない。
- `BUY_EFFECTIVE` / `SELL_EFFECTIVE` を発注トリガーにする案は撤回済み。

### 5.3 絶対にしないこと

- 単一の観測状態をそのまま売買指示に変える。
- 未定義のEpisode条件でコマンドを生成する。
- HFMスプレッド上限なしでLIVEを有効化する。
- SLなしでLIVE発注する。
- ユーザーが目視で止める前提だけで安全設計を済ませる。

## 6. 文書一覧

- [ORDERFLOW_5M10M_BATTLEFIELD_FIT_RESEARCH_PLAN_20260725.md](ORDERFLOW_5M10M_BATTLEFIELD_FIT_RESEARCH_PLAN_20260725.md)
- [ORDERFLOW_5M10M_VALIDATION_PROTOCOL_20260725.md](ORDERFLOW_5M10M_VALIDATION_PROTOCOL_20260725.md)
- [ORDERFLOW_5M10M_STRUCTURE_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_STRUCTURE_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_EPISODE_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_EPISODE_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_OUTCOME_LABEL_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_OUTCOME_LABEL_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_HFM_TIME_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_HFM_TIME_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_MANUAL_EXECUTION_LOG_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_MANUAL_EXECUTION_LOG_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_MANUAL_LEDGER_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_MANUAL_LEDGER_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_MANUAL_COLLECTION_RUNBOOK_20260725.md](ORDERFLOW_5M10M_MANUAL_COLLECTION_RUNBOOK_20260725.md)
- [ORDERFLOW_5M10M_MT5_SAFE_EXECUTOR_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_MT5_SAFE_EXECUTOR_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_MT5_SIGNAL_BRIDGE_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_MT5_SIGNAL_BRIDGE_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_MT5_DEMO_TEST_RUNBOOK_20260725.md](ORDERFLOW_5M10M_MT5_DEMO_TEST_RUNBOOK_20260725.md)
- [ORDERFLOW_5M10M_SHADOW_LIVE_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_SHADOW_LIVE_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md](ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md)
- [ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md](ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md)

## 7. テスト状況

- Entry Spec対象試験は **27 passed**。
- 全体回帰はWindows sandbox外の専用basetempで **451 passed**。
- sandbox内のfull pytestは既知のWindows temp ACLでsetup errorになったが、
  同一suiteをsandbox外で再実行し全件合格した。
- `webapp/main.py` とSHADOW recorderは従来どおり `py_compile` 通過済み。
- MQL5はMetaEditorが環境にないため未コンパイル。

## 8. 再開時の正しい順序

1. 本引き継ぎ書と `PROJECT_MEMORY.md` を読む。
2. MT5発注作業を再開しない。
3. Entry Spec v1とNO-GO結果を変更せず確認する。
4. 同じEntry Spec v1のまま30日／purge後200 Episodeまでデータを継続蓄積する。
5. HFM同一時計Bid／Askの連続保存を成立させ、0バイトblockerを解消する。
6. 固定仕様のuntouched test後、通過した場合だけHFM実Bid／Askへ結合する。
7. 別entry仮説が必要ならv2として先に文章固定し、今回期間を探索／学習へ隔離する。
8. ユーザーがシグナル仕様を明示承認し、Gate 4まで通過した後だけMT5ブリッジを検討する。

## 9. 再開禁止条件

Episodeの「攻撃 → 停滞 → 継続 → 失速 → 反転/突破」のどこをエントリーにするかが未定義のまま、LIVE注文へ進んではならない。

この文書作成時点で、LIVE発注は未実施である。
