# Footprint × Time & Sales lower indicator layout checkpoint

最終更新: 2026-07-29 03:06 JST  
状態: **実装・検証完了／bind mount経由で現runtimeへ反映済み**

## 承認範囲

- ユーザーは、左へ追いやられたALERTSと他の指標を下へ移し、下方向へ広げるよう明示した。
- Footprint＋LIVE DOMとTime & Salesの主横列から、FLOW EVENTS、ABSORPTION、IMBALANCE、
  ALERTSを外し、その下へ常設の横長領域として配置する。
- 下段はFLOW EVENTSを全幅、ABSORPTION／IMBALANCE／ALERTSを3列で広く表示する。
- 完成済み3段チャートの高さ、PRICE／CVD+Delta／VOLUME比率、Flow Response固定行、
  計算、選択、zoom、panは変更しない。
- Footprint、LIVE DOM、Tape、各indicatorのデータ契約、計算、filter、alert判定は変更しない。
- container restart、image build、runtime process操作は行わない。

## 完了済み

- 本sessionで`PROJECT_MEMORY.md`全文と2026-07-29可読性追記を確認済み。
- 現layout sourceとreparent処理を確認した。
- 現在は`flowtop`が`main`第1列にあり、FLOW EVENTSが上、
  ABSORPTION／IMBALANCE／ALERTSが高さ142pxの下段3列へ圧縮されていることを確認した。
- branch `feature/footprint-dom-tape`、HEAD `92ee4ef`、既存dirty worktreeを確認した。
- 変更前実測で3 indicator panelが各74pxまで圧縮され、Footprintと横方向で重なっていた。
- `flowtop`を`main`からappgrid第4行へ移した。
- `main`をFootprint＋Time & Salesの2列へ変更した。
- FLOW EVENTSを下段全幅、ABSORPTION／IMBALANCE／ALERTSをその下の3列へ展開した。
- 下段indicatorの行高、余白、文字サイズを広い領域に合わせて拡大した。
- 実Edge相当1280pxで次を確認した。
  - FLOW EVENTS: 幅1260px／高さ198px
  - ABSORPTION／IMBALANCE／ALERTS: 各幅412px／高さ178px
  - Footprint: 幅770px、Time & Sales: 幅232px
  - main終了y=1200、下段開始y=1212
  - panel重なり0、page横overflow 0、browser page error 0
- WebApp全体回帰121件が合格した。
- 稼働中`http://127.0.0.1:18080/static/index.html`がHTTP 200で新layout markerを返した。

## 未完了

- ユーザー側ブラウザでの最終見え方確認。古いCSS／JSが残る場合は強制再読込する。
- image build／container restartは不要かつ未実施。

## 変更file

- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- 本checkpoint

## 検証結果

- frontend contract: **12 passed**
- WebApp full regression: **121 passed**
- 1280px実Edge相当: geometry全条件PASS、page error 0
- runtime static HTTP: 200、新layout marker全件一致

## blockerの限定範囲

- なし。

## 次の再開位置

1. ユーザーが画面を強制再読込して下段展開を確認する。
2. 問題がなければ本layout remediationを完了扱いとする。
