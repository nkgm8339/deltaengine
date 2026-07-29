# Order Book Heatmap Phase H1 completion report

完了時刻: 2026-07-29 06:01 JST
branch: `feature/footprint-dom-tape`
baseline HEAD: `1134886430b7c48487cd4a9389a202acfa6ff53e`
承認: user `GO-H1`
判定: **SOURCE PASS／runtime未配備**

## 1. 結論

GO-H1「Book continuity contract」を完了した。

`BOOK_UPDATE`へadditiveな`book_stream_id`と`book_sequence`を追加し、同一broker lifecycle、
SYNCED／fail-closed、validation拒否、reconnect cache、new lifecycleの境界をtestで固定した。

既存payload field、Book projection、analysis depth path、Footprint LIVE DOM、Tape、3段チャートは
変更していない。runtime再起動／image build／deploymentは未実施である。

## 2. 実装契約

### 2.1 Stream ID

- `PushBroker` lifecycleごとにcanonical UUIDを1個生成
- 同一broker／WebSocket reconnectでは不変
- new broker／server lifecycleで変更
- Tape `stream_id`とは独立

### 2.2 Sequence

- `book_sequence = book_updates_broadcast + 1`
- 1開始、同一stream内で連続
- SYNCEDとfail-closed messageを同じsequenceへ含める
- validation拒否はsequenceを消費しない
- reconnect cacheは元messageを同じsequenceのまま再送
- exchange `last_update_id`とは独立

### 2.3 Compatibility

- WebSocket envelope `v: 1`維持
- existing fieldの型／意味は不変
- payload specificationは`BOOK_UPDATE v1.4 additive`
- existing frontendは未知fieldを無視できる
- Heatmap UIはまだ未実装／未有効化

## 3. Verification

| scope | result |
|---|---|
| Book／reconnect／broker targeted | `45 passed in 3.54s` |
| WebApp全体 | `125 passed in 7.90s` |
| repository全体 | `667 passed, 1 skipped in 34.53s` |
| source diff check | PASS |
| failure／error | 0 |

追加test:

- payload UUIDがcanonicalでsequence 1
- SYNCED→STALE→recoveryがsequence 1／2／3
- fail-closed messageのlevels clearとsequence連続
- new broker lifecycleが別UUID／sequence 1
- invalid projection拒否後の最初のvalid messageがsequence 1
- reconnect cacheが元messageと完全一致

検証用pytest temporary directory 3件はexact pathを検証して削除した。

## 4. 変更file

Source／spec／test:

- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/tests/webapp/test_book_update.py`
- `ArchitectureRepository/30_Modules/WebApp/Specifications/WebSocketPayload_Spec_v1.md`

Record:

- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H1_CHECKPOINT_20260729.md`
- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_PHASE_H1_COMPLETION_REPORT_20260729.md`
- `ArchitectureRepository/00_Master/ORDER_BOOK_HEATMAP_IMPLEMENTATION_INSTRUCTION_V1_20260729.md`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`

## 5. Runtime／rollback

- current runtimeは再起動していないため、新fieldはまだ配備されていない。
- current browser表示への変更はない。
- H1 rollbackは`push_broker.py`のUUID／2 payload fieldと対応test／specだけを対象にできる。
- completed Footprint／Tape／3段チャートをrollbackしてはならない。

## 6. 次の境界

GO-H1承認範囲は完了した。

次のGO-H2は未承認である。GO-H2ではpure Heatmap coreのみを実装する。

- validator
- bounded book／trade store
- bucket／duration-weighted raster
- intensity／bubble pure function
- Node／Python contract test

Canvas UI、runtime deployment、persistent depth historyはGO-H2へ含めない。
