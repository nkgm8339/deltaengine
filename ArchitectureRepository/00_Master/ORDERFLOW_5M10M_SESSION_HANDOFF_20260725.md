# Session handoff: 2026-07-25

## このセッションで実施したこと

1. `PROJECT_MEMORY.md`、既存の5M/10M研究計画、Episode／Outcome／HFM時刻checkpoint、元のhandoffを全文確認。

2. 5M/10M Episodeの入口仮説を、次の3種類として文章固定。

   - `ATTACK_V1`
   - `PERSIST_PRESSURE_V1`
   - `RESOLUTION_CONFIRMED_V1`

3. `orderflow_episode.py`へ、研究時だけ使える`max_episode_sec`を追加。

4. `src/orderflow/episode_entry.py`を新規追加。

   - Episodeから3種類のcandidateを抽出
   - `DEFENDER_REVERSAL`時のtrade side反転
   - 600秒重複purge
   - 300秒／600秒のforward path
   - signed return、MFE、MAE
   - 20 USD／30 USD proxy cost
   - favorable／adverse hurdleの先着
   - price invalidationと、invalidation時の研究上の撤退結果

5. `tools/evaluate_episode_entries.py`を新規追加。

   - 安定済みParquetだけをsnapshotとして読む
   - RAW tradeはPyArrowでfile単位に監査
   - UTC session別集計
   - JSON／Markdown結果出力

6. 対応テストを追加・修正。

   - `tests/orderflow/test_episode_entry.py`
   - `tests/orderflow/test_orderflow_episode.py`
   - `tests/tools/test_evaluate_episode_entries.py`

7. 固定cutoffで同じ集計を2回実行。

   - entry cutoff: `2026-07-25T06:40:00Z`
   - outcome cutoff: `2026-07-25T06:50:30Z`
   - 865 Episodes
   - raw candidates 572
   - purge後 candidates 277
   - RAW trade 777,683件
   - trade ID重複0、非正値価格0、読取り不能file0

8. 結果文書、checkpoint、handoff、PROJECT_MEMORYを更新。

## 検証結果

- Entry Spec対象: **27 passed**
- 全体回帰: **451 passed**
- HFM同一時計quote: **0 bytes**
- MT5／LIVE注文: **0件**
- 完成済み1M Flow Price Response、3段チャート、UI: **変更なし**

60秒観測の`RESOLUTION_CONFIRMED_V1`、30 USD stress後:

- 300秒: median net `-5.668bps`、positive `1/18`
- 600秒: median net `-5.397bps`、positive `0/18`

この結果から、`Entry Spec v1`についてだけ`NO_GO_FOR_HFM_ENTRY_V1`と記録した。
これは1.5日分のBinance proxy結果であり、HFM全体の可否や注文フロー原理全体の結論ではない。

## このセッションの重大な問題

私は、ユーザーが作ろうとしているシステム全体の目的を確認せず、
自分で狭いEntry Spec v1を作り、その仮説の成績をプロジェクト結論のように扱った。
451件のテストは、その検証器が動くことを示しただけで、ユーザーの問題を解いたことを示さない。

次セッションでは、上記の`NO_GO`を最終結論として扱わないこと。

## 次セッションで最初に読むファイル

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_HANDOFF_20260725.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_SPEC_CHECKPOINT_20260725.md`
- `ArchitectureRepository/00_Master/ORDERFLOW_5M10M_ENTRY_EVALUATION_20260725.md`

## 再開時の注意

- 既存の1M完成機能、3段チャート、UIを変更しない
- MT5／LIVE発注へ進まない
- Entry Spec v1を勝手に改良して再評価しない
- まずユーザーが高い費用を払って作っているシステムの目的を確認し、そこから設計を組み直す
