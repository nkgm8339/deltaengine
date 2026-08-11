# Footprint POC 表示復旧 checkpoint

最終更新: 2026-08-01 21:37:25 JST

## 承認範囲

- ユーザー明示指示「ふっかつさせなさい」に基づく Footprint Chart の POC 常時表示復旧
- POC の計算、表示位置、ズーム、履歴／ライブ更新、VA／Imbalanceとの重なりに関する不具合監査
- 必要な source、回帰試験、本 checkpoint の変更
- git commit、runtime再起動、production deploymentは未承認

## 完了済み

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md` 全文確認
- Footprint V2正本のPOC表示、色、display bucket再計算、試験、checkpoint要件を確認
- 現行Canvasはdisplay bucket後のPOC計算を維持していることを確認
- 現行表示はPOC価格帯の黄色1.2px枠と選択時detailだけで、旧常時ラベル相当の視認性を失っていることを確認
- `footprint_canvas.js` と `test_footprint_chart_ui.py` は作業開始時cleanであることを確認
- `index.html` には別件のDOM→Time & Sales診断用未コミット変更があるため、本件では原則変更しない
- POC価格帯を金色18% overlay＋2.5px輪郭（dense時1.75px）へ強化
- 共通価格軸上部へ金色`POC`凡例とline sampleを常設
- 3本／10本表示の足別固定factsへ正確なPOC価格を常設し、欠測は`POC —`とする
- manual STEPで40行window外となるPOCは`POC ↑`／`POC ↓`として方向を明示
- 20本overviewでも各足のPOC価格行markerを維持
- 10本deterministic Edge fixtureでPOC凡例、価格行強調、足別POC価格を画像確認
- 検証用`poc_visual_fixture.html`は確認直後に削除し、runtime staticへ残していない
- 稼働containerはhost `webapp/static`を`/app/webapp/static`へbindしており、container内sourceに`POC GOLD`反映を確認

## 未完了

- 稼働HTTPのstatic応答復旧後、production URLの実画面でPOCを最終確認
- runtime再起動は未承認のため未実施

## 変更file

- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py`
- `ArchitectureRepository/00_Master/FOOTPRINT_POC_RESTORATION_CHECKPOINT_20260801.md`

## 検証結果

- POC対象: **6 passed**
- POC／Footprint／DOM／PushBroker関連: **49 passed, 1既存failure**
- WebApp全体: **171 passed, 1既存failure**
- 既存failureは`test_dom_tape_fusion_ui.py`が旧selector
  `body.phase5-fusion #right>#left{display:none!important}`を要求する不一致で、
  PROJECT_MEMORYに記録済みのHeatmap layout baseline failureと同一。POC新規failureは0。
- `node --check footprint_canvas.js`: PASS
- 対象`git diff --check`: PASS（Windows LF→CRLF warningのみ）
- deterministic Edge画像: `C:\tmp\deltaengine_poc_restore_20260801_2118.png`
- POC計算はdisplay bucket後の既存`valueArea()`を維持し、backend計算／raw Footprint／VA／Imbalanceを変更していない

## blockerの限定範囲

- repositoryには多数の別件未コミット／未追跡fileがある。対象外fileは編集、stage、削除しない。
- runtime `/api/health`は一度HTTP 200で応答したがoverall RED、latency 12,086msだった。
- host／container内部ともstatic file responseが10〜15秒timeoutし、0 byteとなる既存runtime不具合を再現した。
- sourceはbind mountでcontainerへ反映済みだが、static HTTPが停止しているためproduction URLの再読込確認だけがblockされる。
- blockerはruntime配信とproduction実画面確認に限定され、source実装・試験・deterministic Edge確認は完了。

## 次の再開位置

ユーザーがruntime再起動を明示承認した場合、現container identityとhealthを再確認してからrestartし、
static `footprint_canvas.js`の全body受信、`/api/health`、production実EdgeのPOC、Tape／Book継続を確認する。
