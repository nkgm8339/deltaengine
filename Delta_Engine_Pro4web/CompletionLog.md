# CompletionLog

## v3.6.4 — SelfMonitor v1 + ライブ進行中バー配信 + stack_ref/min_volume較正ツール

**実施日**: 2026-07-18(web直接実装。Code不使用)

### 実装内容

1. **SelfMonitor v1**(優先度1: バグ撲滅)
   - `src/monitor/health.py`: 異常検知6種(SEQUENCE_GAP / BAR_MISSING / WS_RECONNECT / PROCESSING_LATENCY / MEMORY_RSS / PIPELINE_EXCEPTION)、GREEN/YELLOW/RED判定、JSONL日次ローテーション(`data/monitor/anomalies_YYYYMMDD.jsonl`)
   - HEALTH WebSocketメッセージ(5秒周期)+ UIヘルスドット(●クリックでポップアップ詳細)
   - `GET /api/health` エンドポイント
   - `tools/diagnose.py`: ワンコマンド診断レポート(バージョン/設定/DB統計/異常ログ/稼働サーバ)
   - config `monitor:` 節(15キー)追加
2. **ライブ進行中バー配信**(優先度2)
   - `CvdCalculator.current_bar_snapshot()`: 進行中バーの非破壊スナップショット
   - `BAR_UPDATE` メッセージ(既定1秒間引き、`webapp.bar_update_interval_sec`): 形成中バーのOHLCV/delta/cvd + footprint(価格降順、POC/VAH/VAL付き)。orderbookは含めない(CANDLE同梱で十分・軽量化)
   - UI: 追従モード時にFOOTPRINTへ [FORMING] バーを表示。チャート系列は確定バーのみ(系列汚染防止)
   - Replayモードは既存どおりon_tradeフック未配線のためBAR_UPDATE対象外(guardで安全)
3. **stack_ref / min_volume 較正ツール**(優先度3)
   - `tools/calibrate_refs.py`: tradesテーブルからFootprintを決定的に再構成し、min_volume=レベル総出来高P25、stack_ref=実運用と同一のImbalanceDetectorで測ったstacked run長P80を推奨。--writeでconfig反映(コメント・CRLF保持)
4. **replayモード起動バグ修正**(v3.6.3以前から存在)
   - `asyncio.create_task(run_in_executor(...))` はFutureを渡すためTypeErrorでlifespan起動失敗 → `asyncio.ensure_future` に修正+回帰ガードテスト

### 変更/新規ファイル

| 区分 | ファイル |
|------|---------|
| 新規 | src/monitor/__init__.py, src/monitor/health.py |
| 新規 | tools/diagnose.py, tools/calibrate_refs.py |
| 新規 | tests/monitor/(2), tests/tools/(2), tests/orderflow/test_cvd_snapshot.py, tests/webapp/test_bar_update.py |
| 変更 | src/config.py, config/config.yaml(monitor節・bar_update_interval_sec) |
| 変更 | src/orderflow/cvd.py(snapshot API), src/pipeline.py(公開3点) |
| 変更 | webapp/main.py, webapp/push_broker.py, webapp/static/index.html |
| 変更 | tests/webapp/test_api.py, tests/webapp/test_push_broker.py(mock config拡張+回帰ガード) |

### pytest 結果

```
320 passed
```

| 区分 | 本数 |
|------|------|
| 既存テスト(無影響) | 291 |
| monitor | 13 |
| BAR_UPDATE / IntervalGate | 6 |
| CVDスナップショット | 3 |
| calibrate_refs | 4 |
| /api/health + 回帰ガード | 3 |
| **合計** | **320** |

### 検証実績(webサンドボックス)

- ライブ起動スモーク: /health・/api/version・/api/health応答、WSでHELLO+HEALTH受信を確認
- SelfMonitor実挙動: Binance接続不可環境で再接続増加をGREEN→YELLOW→REDで検知、JSONLに3件記録されることを実測
- replayモード起動スモーク: TypeError再発なしを実測
- 全ファイルdiff: 宣言ファイル以外は元ZIPとバイト一致
- `grep -rn "float("`: 新規・変更コードに違反なし(既存の承認済み2箇所のみ)
- JS構文: `node --check` green

---

## Phase1_v2.2 + TaskF — ライブバグ修正 4 件 + フットプリント順序契約修正

**実施日**: 2026-07-18

### 実装内容

| Task | 症状 | 修正 |
|------|------|------|
| A | IMBALANCE 毎バー strength=1.00 飽和 | min_volume null→E3002+0.5 フォールバック / 分母ゼロは numerator≥min_volume 時のみ cap / strength 連続値化 `min(net/(stack_ref×2),1)` + 同方向 3 バークールダウン |
| B | CVD が「—」 | `tools/calibrate_cvd.py` 新規。7 日 \|delta\| P80(397 サンプル)→ `cvd_slope_ref = 65.203` 書込。cvd_unref を仕様化 |
| C | CONFLUENCE 星ゼロ | confluence() の WAIT 全 False 短絡撤廃。WAIT 中は composite 符号で方向判定 |
| D | ALERTS 侵食 / フットプリント見切れ | D-1: #alerthist 通常フロー化 / D-2: 行ウィンドウ化 / D-3: [CLOSED]+経過秒。main.py に Cache-Control: no-cache |
| E | signal.enabled 不整合 | 実態に合わせ `enabled: true` に統一 |
| F | フットプリント価格軸反転・VAH/VAL 入替わり | to_levels() 昇順契約 vs Payload 仕様降順の変換漏れ。`webapp/main.py` アダプタ境界で `reversed()` 適用。delta 負ゼロ表示修正 |

### 変更/新規ファイル

- `src/orderflow/imbalance.py` — `_qualify()` ゲート順序化
- `src/pipeline.py` — `_resolve_imbalance_min_volume()` / `_imbalance_should_fire()` / strength 式
- `tools/calibrate_cvd.py` — 新規
- `webapp/push_broker.py` — confluence WAIT 短絡撤廃
- `webapp/main.py` — Cache-Control / footprint 降順化(TaskF)
- `webapp/static/index.html` — D-1/D-2/D-3 / 負ゼロ表示
- `config/config.yaml` — min_volume 0.5 / cvd_slope_ref 65.203 / signal.enabled true
- `tests/webapp/test_push_broker.py` — TaskF 回帰 2 本(test 15: payload 降順 + VAL<POC<VAH 厳密 / test 16: reversed 配線ガード)

### pytest 結果

```
285 passed
```

| 区分 | 本数 |
|------|------|
| WebApp v3 完了時点 | 281 |
| Phase1_v2.2 追加分 | 2 |
| TaskF 回帰 | 2 |
| **合計** | **285** |

### 完了条件確認

- [x] 285 本 green、既存無影響
- [x] `float(` は webapp/ 実コード 0 件
- [x] ブラウザ目視合格: ①ALERTS 右カラム内 ②[CLOSED]+Ns ③フットプリント高値上・VAH/VAL 正順・板 MID との見かけ乖離解消
- [x] git コミット: `6036061`(v2.2)→ `e0c9c0a`(Cache-Control)→ `c40b7a7`(TaskF)→ `ebdbcdb`(テスト配置修正)
- [x] 仕様書整合: Imbalance v3.2 / SignalEngine v3.1 rev. / CHANGELOG v3.6.2

---


## WebApp v3 — Command Center 実装（指示書_WebApp_v3）

**実施日**: 2026-07-17

### 実装内容

| 責務 | 実装 |
|------|------|
| config webapp 拡張 | `depth_levels` / `flow_window_sec` / `alert_threshold` / `confluence{score_threshold, strength_threshold}` / `enabled` 追加、`v_confluence` バリデータ |
| PushFlowEvent | `src/pipeline.py` — webapp配信用 FlowEvent（IMBALANCE/ABSORPTION のみ、v1） |
| IMBALANCE 発火 | `_evaluate_and_store` に `on_webapp_flow_event` 追加。stacked_imbalances を BUY/SELL 方向ごとに集計し `strength=min(net/stack_ref,1)` で発火 |
| ABSORPTION 発火 | `run_async` の `handle()` で `events_detected` 増分検知（二重発火なし） |
| module_scores | `_BarCloseResult` に `{cvd, footprint, imbalance}` を追加 |
| PushBroker | `webapp/push_broker.py` 新規 — Payload組立の唯一の場所。`d2s`/`envelope`/`compute_value_area`（VA 70%規則）/`flow_score`（指数減衰加重平均）/`confluence` |
| OI poller | `webapp/oi_poller.py` 新規 — `interval_sec` ごとに OI 取得、失敗はログ＋継続 |
| WebApp main | `webapp/main.py` 全面書換 — PushBroker + oi_poller 配線、HELLO握手、STATS 5秒ループ |
| Command Center UI | `webapp/static/index.html` — UI仕様書_CommandCenter_v1 準拠（判定ロジック無し・表示整形のみ） |

### 変更/新規ファイル（WebApp v3）

- `src/config.py` — `v_confluence` + webapp スキーマ拡張
- `config/config.yaml` — webapp セクション拡張
- `src/pipeline.py` — `PushFlowEvent` / `on_webapp_flow_event` / IMBALANCE・ABSORPTION 発火 / `_BarCloseResult.module_scores`
- `webapp/push_broker.py` — 新規
- `webapp/oi_poller.py` — 新規
- `webapp/main.py` — 全面書換
- `webapp/static/index.html` — Command Center UI に置換
- `tests/webapp/test_push_broker.py` — 新規 14 本
- `tests/webapp/test_api.py` — v3 main.py 対応に更新

### pytest 結果

```
281 passed in 8.54s
```

| 区分 | 本数 |
|------|------|
| Phase E 完了時点 | 266 |
| test_push_broker.py 新規 | 14 |
| 既存 test（module_scores 修正で回復） | +1 |
| **合計** | **281** |

### 完了条件確認

- [x] 235本以上 green（281）、既存無影響
- [x] `float(` は webapp/ 実コード 0 件（コメント/docstring の記述のみ）
- [x] Payload は WebSocketPayload仕様_v1 準拠（envelope v=1 / str(Decimal) / expected_rr=null）
- [x] 正本ドキュメント無変更

---

## FlowDetector_v1 Phase E — SignalEngine 統合

**実施日**: 2026-07-16

### 実装内容

| 責務 | 実装 |
|------|------|
| FlowScorer Protocol | `src/orderflow/signal.py` — 差し替え可能なスコアリング戦略 |
| SimpleAverageFlowScorer | 単純平均スコアラー（デフォルト実装） |
| score_flow_events() | モジュールレベルのスタンドアロン関数（score_cvd と同一構造） |
| SignalEngine 拡張 | `w_flow` 重み + `flow_events` 引数 + `FLOW_BUY/SELL` reason codes |
| SignalResult 拡張 | `flow_score: Optional[Decimal] = None` フィールド追加（後方互換） |
| Pipeline 統合 | bar close 時に `flow_event_buffer` スナップショットを SignalEngine へ渡す |

### 変更ファイル（Phase E）

- `src/orderflow/signal.py` — FlowScorer Protocol / SimpleAverageFlowScorer / score_flow_events() / SignalResult.flow_score / SignalEngine.w_flow + flow_scorer
- `config/config.yaml` — `signal.weight.flow: 1.0` 追加
- `src/config.py` — `v_weight` に `flow` オプションキー追加
- `src/pipeline.py` — `_evaluate_and_store()` に `flow_events` 追加、`LivePipeline` に `signal_w_flow`、bar close 順序を Exhaustion/UA 先行→スナップショット→Signal に変更
- `tests/orderflow/test_signal_flow.py` — 新規 16 本
- `tests/test_live_pipeline.py` — 1 本追記

### pytest 結果

```
266 passed in 13.35s
```

| 区分 | 本数 |
|------|------|
| Phase A 完了時点 | 249 |
| test_signal_flow.py 新規 | 16 |
| test_live_pipeline.py 追記 | 1 |
| **合計** | **266** |

### 設計決定遵守確認（Phase E）

| 項目 | 状態 |
|------|------|
| score_flow_events() は SignalEngine から独立 | ✅ モジュールレベル関数、FlowScorer Protocol 経由 |
| 将来アルゴリズム差し替え可能 | ✅ FlowScorer Protocol + DI（flow_scorer 引数） |
| 既存 API 破壊なし | ✅ デフォルト引数のみ追加 |
| float() 0 件 | ✅ |
| WebUI/AI/バックテスト実装なし | ✅ スコープ外 |

---

## FlowDetector_v1 Phase A — 完了

**実施日**: 2026-07-16

### 実装内容

| # | 検出器 | 配置 |
|---|--------|------|
| 1 | LargeTradeDetector | src/orderflow/flow_detector.py |
| 2 | SweepDetector | src/orderflow/flow_detector.py |
| 3 | ExhaustionDetector | src/orderflow/flow_detector.py |
| 4 | UnfinishedAuctionDetector | src/orderflow/flow_detector.py |
| 5 | TapeAnalyzer | src/orderflow/flow_detector.py |

### 変更ファイル

- `src/orderflow/flow_detector.py` — 新規作成（FlowEvent + 5 検出器）
- `config/config.yaml` — `flow_detector` セクション追加
- `src/config.py` — `flow_detector` SCHEMA 追加
- `src/pipeline.py` — LiveStats に `flow_events_emitted`、LivePipeline に FlowDetector 統合（trade 経路 + bar-close 経路）、`flow_event_buffer`・`on_flow_event` フック追加
- `tests/orderflow/test_flow_detector.py` — 新規作成（15 本）
- `tests/test_live_pipeline.py` — FlowDetector 統合テスト 2 本追記

### pytest 結果

```
249 passed in 9.58s
```

| 区分 | 本数 |
|------|------|
| 既存テスト（無影響） | 221 |
| 新規 flow_detector テスト | 15 |
| 新規 live_pipeline 統合テスト | 2 |
| その他増加分 | 11 |
| **合計** | **249** |

### 設計決定遵守確認

| # | 決定 | 状態 |
|---|------|------|
| 1 | FlowEvent frozen dataclass | ✅ |
| 2 | flow_detector.py に集約 | ✅ |
| 3 | flow_event_buffer(maxlen=500) + on_flow_event フック | ✅ SignalEngine 未接続 |
| 4 | 閾値は config.yaml から Decimal で読む | ✅ |
| 5 | float() 0 件 | ✅ |
| 6 | 永続化なし（in-memory のみ） | ✅ |
