# Order-flow Episode outcome-label checkpoint

時刻: 2026-07-25 13:35 JST  
承認範囲: Episode checkpointのBinance価格事後ラベル生成  
未承認: HFM quote結合、戦略評価、Live接続、UI、売買発注

## 完了

- `src/orderflow/episode_dataset.py`を新規追加
- Episode checkpointごとに5分・10分のforward labelを生成
- forward return、pressure signed return、max up、max downを保存
- episode terminal stageとcheckpoint stageを分離
- outcome時刻の許容遅延を超える場合はMISSING_OUTCOME
- 価格列の連続gapを超える場合はDATA_GAP
- 非正値価格と時刻逆行を拒否
- `to_row()`で後続Parquet／DB境界へ渡せる列を固定
- `tests/orderflow/test_episode_dataset.py`を追加

## 検証

- Episode Builder + outcome label tests: **7 passed**
- 60秒windowの現有データdry run:
  - episodes 586
  - labels 2,380
  - OK 1,509
  - MISSING_OUTCOME 846
  - DATA_GAP 25
- 300秒windowの現有データdry run:
  - episodes 213
  - labels 708
  - OK 495
  - MISSING_OUTCOME 210
  - DATA_GAP 3

OK件数はcheckpointとhorizonの組合せ数であり、独立標本数、勝ち数、期待値ではない。
同じEpisode、同じ価格列、複数checkpoint・複数horizonを独立取引として集計していない。

## 変更しない範囲

- 既存1M Flow Price Response
- 3段チャート、8パターン、OI Context、Flow Event
- Native 5m/10m pipeline
- HFM quote、DB、API、UI、発注経路

## 次の再開位置

次の承認後、Episode labelを保存可能な研究datasetへ変換する純粋な集計器を追加し、
episode単位の重複除去、chronological split、block単位の検証規則を設計する。
HFM Bid／Askへの結合は、その後の別checkpointで行う。

