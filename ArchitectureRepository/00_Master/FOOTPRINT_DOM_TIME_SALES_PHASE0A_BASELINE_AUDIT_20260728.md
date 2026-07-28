# Footprint × LIVE DOM × Time & Sales Phase 0A Baseline監査

作成日時: 2026-07-28 15:58:19 JST
最終更新: 2026-07-28 16:49:08 JST
状態: **Phase 0A完了／監査時NO-GO／限定remediation完了／Phase 0B承認待ち**
承認範囲: V2.1採用、OI A確定、Phase 0A read-only監査
未承認: source修正、git commit、branch作成、artifact削除、Phase 0C、Phase 1

本書は次のV2.1補遺に定義されたPre-Phase Baseline Gateの監査記録である。

- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`

## 1. 結論

テスト上の退行はない。

```text
対象回帰: 67 passed
全体回帰: 601 passed, 1 skipped
```

監査時点では、Session VWAPの完成記録、checkpoint、実装の間に複数の不一致があり、
debug traceも残っていたため、現ワークツリーをそのままbaseline commitできなかった。

特に、WebAppの表示fallbackが参照する`current_value`は実装されておらず、
mid-session開始時の表示用VWAPは常に`None`になる。
現在のtestはbrokerへVWAP値を直接渡すため、この実運用経路の欠落を検出しない。

2026-07-28 16:49:08 JSTまでにSession VWAP／UI差分だけを対象とした限定remediationと
再検証を完了した。commit／branchはPhase 0Bの明示承認まで実行しない。

## 2. Repository snapshot

```text
branch: ui-refresh-v2
HEAD: a8182a9
upstream: origin/ui-refresh-v2
local commits: ahead 3
tracked modified: 12 files
tracked diff: 218 insertions, 18 deletions
untracked regular files: 19 files
```

pytest／監査用一時directoryにはWindows sandbox由来のaccess deniedがあり、
`git status`が内容を列挙できないdirectoryが複数ある。
これらはbaseline対象外であり、本監査では削除していない。

## 3. Dirty inventory

### 3.1 Session VWAP core候補

| file | classification | audit |
|---|---|---|
| `Delta_Engine_Pro4web/src/database/session_vwap_warm_start.py` | intended source | core候補 |
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/session_vwap.py` | intended source | core候補。ただし表示用property欠落 |
| `Delta_Engine_Pro4web/src/pipeline.py` | intended source | core候補。`_last_market_state = None`重複あり |
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py` | intended source | core候補 |
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py` | intended source | core候補 |
| `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py` | mixed intended source | VWAP差分と既存600秒retention差分が同居 |
| `Delta_Engine_Pro4web/tests/database/test_session_vwap_warm_start.py` | intended test | core候補 |
| `Delta_Engine_Pro4web/tests/strategy_engine/test_session_vwap.py` | intended test | core候補 |
| `Delta_Engine_Pro4web/tests/test_session_vwap_live.py` | intended test | core候補 |

### 3.2 Session VWAP WebApp候補

| file | classification | audit |
|---|---|---|
| `Delta_Engine_Pro4web/webapp/history.py` | intended source | API fieldは追加、履歴値は常に`NULL` |
| `Delta_Engine_Pro4web/webapp/main.py` | intended source | 存在しない`current_value`へfallback |
| `Delta_Engine_Pro4web/webapp/push_broker.py` | intended source＋debug | 常時`warning`のtraceが残存 |
| `Delta_Engine_Pro4web/webapp/static/index.html` | intended source＋debug | 白実線、console trace、履歴補完なし |
| `Delta_Engine_Pro4web/tests/webapp/test_bar_update.py` | intended test | broker直渡しのみ。runtime fallback未検証 |

### 3.3 運用設定

| file | classification | disposition |
|---|---|---|
| `DeltaEngine05M.bat` | operational change／baseline外 | compose project名変更と旧container強制削除を含む。別承認まで除外 |
| `Delta_Engine_Pro4web/docker-compose.yml` | operational change／baseline外 | source static bind mount追加。別承認まで除外 |

### 3.4 文書

| group | files | disposition |
|---|---:|---|
| `PROJECT_MEMORY.md` | 1 | intended documentだが現物と不一致。修正前はcommit不可 |
| VWAP checkpoint | 1 | intended documentだが現物と不一致。修正前はcommit不可 |
| Footprint V1／V2／V2.1 | 3 | intended design。baselineへの同梱は別途明示承認が必要 |
| Footprint HTML mocks | 3 | intended design artifact。同上 |
| 経緯／Hook棚卸し／内容説明 | 3 | unrelated intended documents。別commit候補 |
| Phase 0A本監査書 | 1 | intended checkpoint |

Footprint V1／V2は
`ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_dom_fusion_mock.png`
を参照しているが、当該PNGは現ワークツリーに存在しない。

V2／V2.1の文書状態もまだ`DRAFT — USER REVIEW REQUIRED`、
OI AとPhase 0Aも未確定と記録されており、2026-07-28のユーザー承認を反映していない。

### 3.5 Runtime／debug／temporary artifact

| artifact | size | disposition |
|---|---:|---|
| `vwap-audit.duckdb` | 219,688,960 bytes | runtime audit DB、必ず除外 |
| `vwap_first100.jsonl` | 26,788 bytes | debug capture、必ず除外 |
| `vwap_restore_ws_capture.jsonl` | 0 bytes | debug capture、必ず除外 |
| `vwap_ws_capture.jsonl` | 1,886 bytes | debug capture、必ず除外 |
| `.pytest_cache/`等access denied directory | unknown | temporary artifact、必ず除外 |
| `pytest-vwap-*`／`phase0a_pytest_*` | unknown | temporary artifact、必ず除外 |
| `session_audit_manual_*` | unknown | temporary artifact、必ず除外 |

本監査では削除、移動、ignore追加を行っていない。

## 4. Baseline blocker

### B1. 表示fallback実装が存在しない

`webapp/main.py`は戦略用Session VWAPが`None`の場合、
`SessionVwapAccumulator.current_value`を参照する。

しかし`session_vwap.py`に次のpropertyは存在しない。

- `current_value`
- `notional`
- `volume`

`getattr(..., None)`のためexceptionにはならず、UIへ`None`が静かに送られる。
checkpointの「表示用累積値を配信」は現物と一致しない。

### B2. 表示仕様と現物が不一致

`PROJECT_MEMORY.md`とVWAP checkpointは「橙色破線」と記録しているが、
`index.html`は白色の実線で描画し、legendも白色である。

### B3. Debug traceが常時有効

次が残っている。

- server `logger.warning("VWAP_TRACE_WS ...")`
- browser `console.info("[VWAP_TRACE] ...")`
- browser `console.info("[LAST_PRICE_RX] ...")`

`BAR_UPDATE`間隔でwarningを出すため、productionでlog floodとなり得る。
`vwap_notional`、`vwap_volume`、`current_price`引数もpayload契約ではなく
trace専用であり、現状ではaccumulator property欠落により値も取得できない。

### B4. 履歴方針が文書間で矛盾

- `PROJECT_MEMORY.md`: 既存履歴はVWAP未提供、liveのみ表示
- VWAP checkpoint末尾: OHLCV session累積推定で履歴補完
- 現物: history APIは`vwap = NULL`、browser側推定なし

OHLCV推定値は実約定VWAPと同一ではないため、
無断で「Session VWAP」として補完してはならない。
推奨baselineは、履歴は`null`、live exact／表示用partialは状態を明示して分離する案である。

### B5. 同一file内に別変更が混在

`snapshot_producer.py`にはVWAP追加と、
既存の`_PRICE_HISTORY_NS = 300秒 → 600秒`変更が同居している。
Session VWAP baselineへ無言で混ぜず、hunk単位で承認を分ける必要がある。

### B6. 運用設定が機能差分と混在

`DeltaEngine05M.bat`はcompose project変更に加え、
`docker rm -f deltaengine_05m-deltaengine_clone-1`を実行する。
`docker-compose.yml`はWebApp static source bindを追加する。

どちらもSession VWAPの論理実装には不要であり、baselineから除外する。

### B7. 軽微なcleanliness

`pipeline.py`で`self._last_market_state = None`が連続して2回代入されている。

## 5. Verification

### 5.1 Diff

```text
git diff --check:
  whitespace errorなし
  LF→CRLF warningのみ
```

### 5.2 対象回帰

実行対象:

- Session VWAP unit
- DuckDB warm start
- Live restart
- BAR_UPDATE
- history
- push broker
- WebApp API

```text
67 passed in 6.81s
```

### 5.3 全体回帰

```text
601 passed, 1 skipped in 103.59s
```

最初のsandbox内実行はpytest `basetemp`のWindows access deniedで終了した。
同じ対象をsandbox外の新規`basetemp`で再実行し、上記結果を得た。
code failureではない。

### 5.4 Test gap

全体回帰合格はB1〜B4を否定しない。

現行testは次を検証していない。

- `chart_session_vwap()`のmid-session fallback
- accumulatorの表示用property
- orange dashed style
- debug trace不在
- browserでのlive line実表示
- 履歴`null`とlive exactの切替

## 6. Proposed baseline structure

限定remediationと再検証は完了した。
Phase 0Bの明示承認後、次の論理単位だけをstageする。

### Commit 1 — Session VWAP core

候補message:

```text
feat(strategy): add exact UTC session VWAP with warm start
```

候補file:

- `Delta_Engine_Pro4web/src/database/session_vwap_warm_start.py`
- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/condition_adapter.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/market_state.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/session_vwap.py`
- `Delta_Engine_Pro4web/src/strategy_engine/ingestion/snapshot_producer.py`
- `Delta_Engine_Pro4web/tests/database/test_session_vwap_warm_start.py`
- `Delta_Engine_Pro4web/tests/strategy_engine/test_session_vwap.py`
- `Delta_Engine_Pro4web/tests/test_session_vwap_live.py`

`snapshot_producer.py`の600秒retention hunkは、
今回のbaselineからhunk単位で除外し、既存差分として保持する。

### Commit 2 — WebApp Session VWAP overlay

候補message:

```text
feat(webapp): overlay live session VWAP on the price pane
```

候補file:

- `Delta_Engine_Pro4web/webapp/history.py`
- `Delta_Engine_Pro4web/webapp/main.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/webapp/test_bar_update.py`
- `Delta_Engine_Pro4web/tests/webapp/test_history.py`
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`

B1〜B4は解消済み。

### Commit 3 — Completion record

候補message:

```text
docs: record session VWAP baseline and Phase 0A audit
```

候補file:

- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`
- `ArchitectureRepository/00_Master/トリガー作成指示書群/VWAP_IMPLEMENTATION_CHECKPOINT_20260727.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE0A_BASELINE_AUDIT_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_PHASE0A_REMEDIATION_CHECKPOINT_20260728.md`

文書は現物と最終test件数`606 passed, 1 skipped`へ同期済み。

### Commit 4 — Approved Footprint design docs

候補message:

```text
docs: approve footprint DOM and time sales design v2.1
```

Phase 0B GOにより同梱が明示承認された場合、docs-only commitとする。

- `ArchitectureRepository/00_Master/FOOTPRINT_CHART_DOM_FUSION_IMPLEMENTATION_INSTRUCTION_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_IMPLEMENTATION_INSTRUCTION_V2_20260728.md`
- `ArchitectureRepository/00_Master/FOOTPRINT_DOM_TIME_SALES_FUSION_PREIMPLEMENTATION_AMENDMENT_V2_1_20260728.md`
- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_3bar_mock.html`
- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_reference_mock.html`
- `ArchitectureRepository/30_Modules/WebApp/Design/footprint_chart_dom_fusion_mock.html`

V2.1 APPROVED、OI A、Phase 0A承認済み状態へ同期し、存在しないPNG参照は除去済み。

## 7. Explicit exclusions

次はbaseline commitへ含めない。

- `DeltaEngine05M.bat`
- `Delta_Engine_Pro4web/docker-compose.yml`
- `vwap-audit.duckdb`
- `vwap_first100.jsonl`
- `vwap_restore_ws_capture.jsonl`
- `vwap_ws_capture.jsonl`
- pytest／sandbox／browser／manual audit一時directory
- raw market data
- source由来不明artifact
- 経緯報告、Hook棚卸し、Hook内容説明書
- 存在しない／未確認のPNG

## 8. Completed remediation before Phase 0B

次の限定範囲を完了した:

1. `current_value`等の表示契約を実装するか、fallback記述を撤回する
2. live exactとpartial表示を混同しないpayload／label／testを追加する
3. VWAPを承認記録どおり橙色破線へ揃える
4. server／browser debug traceとtrace専用引数を除去する
5. 履歴は実約定値がない限り`null`とするか、別名の推定値として明示承認を取る
6. duplicate代入を除去する
7. `snapshot_producer.py`の600秒hunkを別判断にする
8. `PROJECT_MEMORY.md`、VWAP checkpoint、V2／V2.1の状態を現物へ同期する
9. 不足test、対象回帰、全体回帰、browser表示確認を再実行する
10. 最終diffとcommit対象を再提示し、Phase 0Bの明示承認を得る

## 9. Checkpoint

現在時刻: 2026-07-28 15:58:19 JST
承認範囲: Phase 0A read-only auditのみ
完了:

- `PROJECT_MEMORY.md`全文確認
- dirty inventory
- file分類
- diff review
- 対象回帰
- 全体回帰
- commit／exclusion proposal

未完了:

- B1〜B7 remediation
- baseline commit
- commit SHA記録
- feature branch作成
- Phase 0C storage sizing
- Phase 1 source implementation

今回変更したfile:

- 本監査書のみ

検証結果:

```text
67 passed
601 passed, 1 skipped
```

blockerの限定範囲:

- Session VWAP／WebApp baseline commitだけを停止する
- Footprint source実装はPhase 0B／0C承認前のため未着手
- read-only調査、設計確認、artifact分類は完了

次の再開位置:

1. ユーザーが限定remediationを承認
2. B1〜B7だけを修正
3. test再実行
4. exact commit proposal再提示
5. ユーザーのPhase 0B承認後にcommit／branch作成

## 10. Remediation result

完了時刻: 2026-07-28 16:49:08 JST

| blocker | result |
|---|---|
| B1 | 表示専用`current_value`と`EXACT/PARTIAL`投影を実装 |
| B2 | 橙色破線、PARTIAL `~` labelへ統一 |
| B3 | server／browser debug traceとtrace専用引数を除去 |
| B4 | 履歴は`vwap=null`／`vwap_status=null`、OHLCV推定なしで確定 |
| B5 | 600秒retention hunkは変更せず別判断を維持 |
| B6 | BAT／Docker差分は変更せずbaseline除外を維持 |
| B7 | Replay／Liveの重複代入を除去 |

追加同期:

- WebSocketPayload v1.1 additive extension
- V2.1 APPROVED
- OI A確定
- 欠落PNG参照を除去

検証:

```text
対象回帰: 72 passed
全体回帰: 606 passed, 1 skipped in 116.81s
inline JavaScript syntax OK (1 script)
debug trace residue: 0
git diff --check: whitespace errorなし
```

現在のblockerはPhase 0Bのユーザー明示承認だけである。
