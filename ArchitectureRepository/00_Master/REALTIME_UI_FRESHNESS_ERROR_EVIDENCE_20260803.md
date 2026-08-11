# Realtime UI Freshness TIMEOUT エラー証拠

- 作成日: 2026-08-03 JST
- 用途: Claude独立レビューへのエラー全文・発生場所・traceback有無の回答
- status: 恒久対処実装NO-GO／レビュー中

## 1. エラー全文

ユーザー実画面に表示されたbanner全文:

```text
MARKET DATA STALE — LIVE DECISION DATA DISABLED · TICK_TIMEOUT
```

同時に上部LIVE表示が`STALE`へ変化し、USD-M主価格が無効化された。

第一是正を反映しpage reloadした後も、ユーザーから次の再発報告を受けた。

```text
なおってねーよ！！タイムアウト連発だぞ
```

再発時のreasonは現行sourceに残る`TICK_TIMEOUT`であり、`MarketFreshnessGuard.check()`が最後の受理TICKから2000ms超で生成する。

## 2. 出ている場所

- 主発生場所: **ブラウザ画面上部の赤色banner**
- browser JavaScript state: `STALE`
- browser WebSocket自体: 第一是正後の再発時はopenのまま
- pytest: 本不具合を示すfailureは出ていない
- docker起動時: 本不具合に対応するERROR／tracebackは出ていない
- Python traceback: なし
- browser console traceback: 採取なし。画面bannerとして再現
- Codex実装tool error: 本不具合とは無関係

## 3. スクリーンショット

package内:

```text
Evidence/OFF_bug_20260803_071240.png
```

撮影時刻表示は2026-08-03 07:12:40 JST付近。bannerは次を表示している。

```text
MARKET DATA STALE — LIVE DECISION DATA DISABLED · TICK_TIMEOUT
```

注意: この画像は第一是正前の実画面である。第一是正後の再発はユーザーの画面報告で確認したが、第二のスクリーンショットは未受領。

## 4. 第一是正前のruntime証拠

- 直近30分docker log:
  - `connection open`: 58件
  - `connection closed`: 0件
- `/api/health`: 5秒timeoutを観測
- client sourceの経路:

```text
MarketFreshnessGuard.check()
  -> _fail("TICK_TIMEOUT")
  -> onReconnect()
  -> ws.close()
  -> onclose
  -> exponential backoff reconnect
```

第一是正では`onReconnect -> ws.close()`を撤去した。

## 5. 第一是正後の再発時runtime証拠

2026-08-03 08:14 JST付近:

```text
/api/health              GREEN
upstream reconnect       0
pipeline exception       0
browser WS open/close    0 / 0（直近1分）
docker ERROR             0
```

server／upstream／browser transportが正常でもbrowser bannerだけが`TICK_TIMEOUT`へ遷移した。したがって第一是正後の再発はtransport断ではなく、TICKが2000ms来ないことを通信断として扱うclient誤判定である。

## 6. 実WebSocket採取

第一是正反映後、読み取り専用clientで15.02秒採取:

```text
messages                 243
TICK                     34
first trade id           7947840145
last trade id            7947840258
maximum TICK gap         1572.7ms
maximum transport age    725.3ms
socket completion        normal
```

短時間採取では2秒を超えなかったが、TICKは約定eventであり、2秒以内に必ず届くheartbeat契約は存在しない。長時間画面では正常な無約定区間またはbrowser event-loop遅延により閾値を超え、誤TIMEOUTが反復する。

## 7. 関係する現行source anchor

### `webapp/static/market_freshness.js`

```text
17   class MarketFreshnessGuard
78   acceptTick(candidate)
105  check()
108  _fail("TICK_TIMEOUT")
```

`lastAcceptedAt`はfresh TICK受理時だけ更新される。`check()`はLIVE中に`now - lastAcceptedAt > staleAfterMs`で`TICK_TIMEOUT`へ遷移する。

### `webapp/static/index.html`

```text
1024  MARKET_FRESHNESS生成
1025  staleAfterMs:2000
1041  renderMarketFreshness(snapshot)
1054  TAPE_UI.setConnected(fresh)
1055  HEATMAP_UI.setConnected(fresh,...)
1108  TICK dispatch
1138  onTick
1159  onBookUpdate
1165  onTapeUpdate
```

価格TICKの誤STALEがHeatmap／Tape connectedとBOOK routingへ波及する。

### Server／upstream

- `src/acquisition/connector.py`
- `webapp/push_broker.py`
- `webapp/main.py`
- `src/config.py`
- `config/config.yaml`

現物はpackageの`Source/`へ収録している。

## 8. pytest結果とtraceback

第一是正後のtest:

```text
専用test          7 passed
関連test          76 passed
WebApp全体        190 passed / 1 failed
repository全体    818 passed / 1 skipped / 1 deselected
```

唯一のWebApp failure:

```text
tests/webapp/test_dom_tape_fusion_ui.py::
test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

assertion全文:

```text
assert 'body.phase5-fusion #right>#left{display:none!important}' in html
```

現行／HEADは`body.phase5-fusion #main>#left`であり、本件開始前から存在する既知baseline selector不一致。本TIMEOUTとは無関係である。

本TIMEOUTを検出するpytest failureまたはPython tracebackは存在しない。専用testが「TICKが2秒ない場合はSTALE」を正しい期待値として固定していたため、誤設計をPASSさせていた。

## 9. 第一是正で変更済みの現物

- `market_freshness.js`: TIMEOUT時のtransport reconnect callbackを撤去
- `index.html`: guardから`onReconnect -> ws.close()`を撤去
- `push_broker.py`: global client lock中の無期限network awaitを撤去し、0.5秒bounded sendへ変更
- `test_market_freshness_ui.py`: 第一是正test追加

第一是正は自己切断stormを抑止したが、TICK単独timeout判定を残したためLIVE OFFは未解消。

## 10. 独立レビュー対象

恒久対処の設計と変更境界はpackage内の次を正本とする。

```text
Documents/REALTIME_UI_FRESHNESS_HEARTBEAT_PERMANENT_FIX_IMPLEMENTATION_INSTRUCTION_V1_20260803.md
```

実装は独立レビューGOとユーザーの別途実装GOまで開始しない。
