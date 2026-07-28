# Footprint × Time & Sales readability remediation checkpoint

最終更新: 2026-07-29 01:59 JST  
状態: **実装・検証完了／bind mount経由で現runtimeへ反映済み**

## 承認範囲

- ユーザーが2026-07-29 01:37 JSTの実画面画像を提示し、
  Footprint ChartとTime & Salesの文字が小さすぎて読めないと明示した。
- Footprint Canvas内の表示文字と、Time & Salesの見出し、filter、列名、約定行、
  detail、statusの文字および文字に直接依存する固定行高を拡大する。
- Footprint、LIVE DOM、Tapeのデータ契約、計算、保持件数、filter、selection sync、
  gap／restart判定、fail-closed動作は変更しない。
- 完成済みFlow Price Response、3段チャート、8パターン、OIの計算・構造・操作は変更しない。
- production image build、container restart、deploymentは本checkpointの承認範囲に含めない。
  `./webapp/static:/app/webapp/static`の既存bind mountによる静的表示反映だけを確認する。

## 完了済み

- `PROJECT_MEMORY.md`全1074行を分割して全文確認した。
- root `AGENTS.md`とV2／V2.1の可読性・Canvas・checkpoint契約を確認した。
- branch `feature/footprint-dom-tape`、HEAD `92ee4ef`、既存dirty worktreeを確認した。
- ユーザー提示画像とsourceを照合した。
- 原因を次のとおり特定した。
  - Time & Sales約定行: 7px font／15px row
  - Time & Sales補助表示: 6.5〜8px
  - Footprint価格、数量、時刻、DOM数量: 7〜9px中心
- Time & Sales約定行を14px font／28px rowへ拡大した。
- Time & Salesの見出し、filter、列名、detail、statusを9〜12pxへ拡大し、最小幅232pxを確保した。
- Footprintの通常AUTO表示を20価格行、主要BID／ASK値14px太字へ変更した。
- Footprintの長い数量はCanvas `fillText(..., maxWidth)`で各BID／ASK半セル内へ収める。
- 手動STEPで価格行が密になる場合だけ12px／11pxへ段階縮小する。
- Footprint価格軸を12px、時刻／補助値を11〜14pxへ拡大した。
- Footprint／Time & Salesのcontrol、tooltip、selection、statusも拡大した。
- 1280px実Edge相当でTime & Sales 230px、約定10行、横overflow 0を確認した。
- 同条件のFootprintは10本bar幅52.1px、価格行18.95px、20行で、
  実draw callが14px／maxWidth 21.05pxになることを確認した。
- page横overflow 0、browser page error 0を確認した。
- 稼働中`http://127.0.0.1:18080/static/`がindex／Footprint JS／Tape JSをHTTP 200で返し、
  14px／28px／cell fitの全markerを含むことを確認した。

## 未完了

- ユーザー側ブラウザでの最終見え方確認。古いCSS／JSが残る場合は強制再読込する。
- image build／container restartは不要かつ未実施。

## 変更file

- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/webapp/static/footprint_canvas.js`
- `Delta_Engine_Pro4web/webapp/static/time_sales.js`
- `Delta_Engine_Pro4web/tests/webapp/test_footprint_chart_ui.py`
- `Delta_Engine_Pro4web/tests/webapp/test_dom_tape_fusion_ui.py`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- 本checkpoint

## 検証結果

- source contract: **12 passed**
- Footprint／Tape／Phase 6／history関連: **26 passed**
- WebApp full regression: **121 passed**
- 初回拡張回帰の5 setup errorは、pytest既定tmpのWindows permission errorだけであり、
  workspace内専用basetemp＋昇格実行で同じ対象を全件PASSした。
- 1280px実Edge相当: page error 0、page overflow 0、Tape overflow 0。
- completed three-stage chartのsource geometryと試験契約は変更なし。

## blockerの限定範囲

- なし。
- Docker APIはsandbox内からpermission deniedだったが、静的fileは既存bind mountで反映され、
  runtime HTTP応答を直接照合できたため本修正のblockerではない。

## 次の再開位置

1. ユーザーが画面を再読込して14px表示を確認する。
2. まだ小さい、またはOS scalingで崩れる場合は実画面画像とviewport／DPRを再取得する。
3. それ以外は本remediationを完了扱いとする。
