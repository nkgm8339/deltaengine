# DeltaEngine 05M — 右カラム・固定詳細欄 UI 引継ぎ

- 記録時刻: `2026-07-26T13:01:12+09:00`
- ブランチ: `ui-refresh-v2`
- 承認範囲: LIVE OBSERVATIONの横幅・文字サイズと、3段チャート右側の固定詳細欄の表示改善
- 保護範囲: Flow Price Response、3段チャートの計算・比率、バックエンド、API、WebSocket、保存データ

## 完了した変更

### LIVE OBSERVATION

- ページ右カラムを`322px`から`238px`へ変更した。
- 確保した幅を左側のメイン領域へ戻した。
- 時刻を`13px`、Flow Measuresの主要数値を`14px`へ拡大した。
- 市場数値を`14px`、変化値を`11px`、方向矢印を`16px`へ拡大した。
- Contextの値を`11px`、状態ドットを`8px`へ拡大した。
- Observed Factsの見出しは`9px`を維持し、箇条書き本文を`14px`へ拡大した。

### 3段チャート右側の固定詳細欄

- 固定詳細欄を`250px`から`334px`へ拡大した。
- 詳細欄をマウスホイールで縦スクロールできるようにした。
- 選択中の足がライブ更新で再描画されてもスクロール位置を保持する。
- 別の足へ移動したときは詳細欄を先頭へ戻す。
- 時刻、OHLC、CVD、Delta、Volume、OI、Flow Response、Flow Eventの数値を`14px`へ統一した。
- 8パターンカード本文を`12px`、PRICE／CVD／Delta／OI方向行を`14px`へ拡大した。

### 選択足の観測情報

- 8パターンカードの方向行へOIを追加した。
- 既存8パターンの説明を日本語へ変更した。
- OI評価は「可能性」を先に置き、その下へ観測事実を表示する順序へ統一した。
- OIの重複カードを作らず、8パターンカード内へ統合した。
- OI OPEN、CLOSE、CHANGE、CHANGE %、SAMPLESの生値表示は維持した。
- Footprintの`Σ BID`、`Σ ASK`、`Delta`を囲みのない1行表示で追加した。
- ライブ足はFootprint levelsを合算し、履歴足はVolumeとDeltaから同値を復元して表示する。

## 意味を変えていないもの

- Flow Price Responseの状態、PR、P、Vの計算
- 3段チャートのローソク足、CVD、Volumeの計算と描画比率
- 8パターンの分類条件
- OIの取得、保存、足への時刻整列
- 05M CONTEXT固定帯

今回追加したOI文は断定ではなく、観測事実から読める可能性の説明である。
売買シグナル、確率、score、自動発注条件としては扱わない。

## 変更ファイル

- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
- `ArchitectureRepository/00_Master/CHANGELOG.md`
- `ArchitectureRepository/00_Master/UI_RIGHT_RAIL_DETAIL_HANDOFF_20260726.md`

## Checkpoint

- 完了済み: UI実装、表示値の確定、対象テスト更新、文書化、稼働中05Mへの反映
- 未完了: なし
- 検証結果: JavaScript構文通過、HTML ID 163件・重複0件、
  UI対象30 passed、WebApp全体76 passed、配信HTMLのSHA-256一致
- Blocker: なし
- 次の再開位置: ユーザーからの次の明示指示を待つ
