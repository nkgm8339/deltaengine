# Order-flow Episode Builder checkpoint

時刻: 2026-07-25 13:20 JST  
承認範囲: Episode Builderの純粋ロジックとdry run  
未承認: 評価器、HFM結合、Live接続、UI、売買発注

## 完了

- `src/orderflow/orderflow_episode.py`を新規追加
- 選択したFlow observation windowだけを処理する境界を追加
- `AGGRESSION`
- `NON_RESPONSE`
- `SUSTAINED_CONFLICT`
- `AGGRESSOR_BREAKTHROUGH`
- `DEFENDER_REVERSAL`
- `INVALIDATED`
- `UNRESOLVED`
  の状態を定義
- 同一rolling eventの連続更新を一つのEpisodeへまとめる処理を追加
- `episode_id`、時刻、pressure side、observation count、checkpointsを保持
- gapをまたぐEpisodeをINVALIDATEDとして終了
- out-of-order observationを拒否
- finalize時の未決着をUNRESOLVEDとして保持
- `tests/orderflow/test_orderflow_episode.py`を追加

## 検証

- 人工時系列テスト: **4 passed**
- 60秒window dry run: observations 1,595 / episodes 583
  - resolved 279
  - invalidated 303
  - unresolved 1
- 300秒window dry run: observations 497 / episodes 212
  - resolved 82
  - invalidated 129
  - unresolved 1

dry runはイベントをEpisodeへ構造化できることだけを確認した。件数、resolved率、
状態名を優位性や売買シグナルとして解釈しない。

## 変更しない範囲

- 既存1M Flow Price Response
- 3段チャート
- 8パターン、OI Context、Flow Event
- Native 5m/10m処理
- Live pipeline、API、UI、HFM quote保存
- 注文発注経路

## 限定blocker

- 現在のRAW連続区間は短く、複数gapがある
- Flow eventの開始範囲とRAW tradeの保存範囲が完全一致しない
- Episodeの閾値・判定性能は未評価

## 次の再開位置

ユーザーの次の承認後、Episode dataset schemaと、先読みを含まない
5分・10分事後ラベルの純粋評価器を設計する。HFM価格への結合はその後に行う。

