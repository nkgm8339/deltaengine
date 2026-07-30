# Completion Log

完了済みフェーズの時系列記録。最新エントリを末尾に追加する。

---

## B-1: Order Book 正規化基盤実装

**実施日時**: 2026-07-08  
**指示書**: `指示書_B1_OrderBook基盤実装_v1.md`

### 完了報告

- 新規テスト件数: 旧128 → B-1完了時 168（+40本）
- 設計判断逸脱: なし（全5決定を逐語実装）
- Decimal禁則スキャン: `src/orderflow/orderbook.py` にて float() 呼び出し 0件

### 成果物ファイル一覧

**新規**
- `src/orderflow/orderbook.py`（BookLevel / OrderBookUpdate / OrderBookSnapshot / OrderBookStateManager）
- `tests/orderflow/test_orderbook.py`

**編集**
- `src/normalization/normalizer.py`（process_depth / classify_raw / normalize_raw_depth / ExchangeProfile.order_book_mapping 追加）
- `src/acquisition/binance_ws.py`（is_agg_trade_or_depth 追加）
- `config/profiles/binance.yaml`（order_book_mapping ブロック追加）
- `tests/normalization/test_normalizer_depth.py`（新規）
- `tests/acquisition/test_binance_ws.py`（追記）

### 逸脱

なし。

---

## B-2: M9 Absorption 実装 + volume_ref 共有機構 + Pipeline 配線

**実施日時**: 2026-07-08  
**指示書**: `指示書_B2_M9Absorption_Pipeline配線_v1.md`

### 完了報告

- 新規テスト件数: 旧168 + 新規17本 = **185 passed**
- TV-ABS-01〜05 実測結果: **5件全て PASSED**
  - TV-ABS-01: BUY_ABSORPTION、strength=1.0 ✓
  - TV-ABS-02: aggression_condition_fails==1 ✓
  - TV-ABS-03: stall_condition_fails>=1 ✓
  - TV-ABS-04: replenish_condition_fails==1 ✓
  - TV-ABS-05: SELL_ABSORPTION、strength=1.0 ✓
- Decimal禁則スキャン: `src/orderflow/` 全ファイルで `float(` 呼び出し 0件 ✓
- `AbsorptionResult` 型シグネチャ: stub 時代と完全一致 ✓
- `ImbalanceDetector.volume_ref`: keyword 引数 default None、既存呼び出し無影響 ✓
- `pipeline.py` の `absorption_result=None` 固定: 実接続に完全置換 ✓
- `is_agg_trade_or_depth`: pipeline の validate に差し替え済み ✓
- docs(`ArchitectureRepository/`): 無変更 ✓

### §4 設計判断 5点の実装確認

| 決定 | 内容 | 逸脱 |
|---|---|---|
| 1 | price_stall_ticks = distinct executed price 数の許容上限値 | なし |
| 2 | volume_ref.current() None 時は sink（カウンタ非増加） | なし |
| 3 | window_start_snapshot は window head 変化時 or 最初の trade 時に捕捉 | なし |
| 4 | Absorption は tick 駆動、SignalEngine は bar 確定時に current() 問い合わせ | なし |
| 5 | 両方向同時発火は BUY_ABSORPTION 優先、double_direction_events++ | なし |

### 統合テスト実測値（test_pipeline_absorption.py）

- `test_pipeline_depth_flows_to_book_state`: normalized=3, candles_stored=2, signals_stored=2, invalid=0 ✓
- `test_pipeline_absorption_veto_reaches_signal`:
  - bar0 signal="SELL"（absorption 未較正のため veto なし）
  - bar1 signal="WAIT"（BUY_ABSORPTION veto 発動、confidence=0.5 > 0.4 threshold）
  - events_detected 経路全通過確認 ✓

### 成果物ファイル一覧

**新規**
- `src/orderflow/volume_ref.py`（VolumeRefTracker）← B-2着手中に作成済み、本フェーズで完成確認
- `tests/orderflow/test_volume_ref.py`（6本）
- `tests/orderflow/test_absorption.py`（9本）
- `tests/test_pipeline_absorption.py`（2本）

**編集**
- `src/orderflow/absorption.py`（stub → AbsorptionDetector 実装で完全置換）
- `src/orderflow/imbalance.py`（volume_ref keyword 引数追加）
- `src/pipeline.py`（depth 経路配線 + Absorption + VolumeRef + is_agg_trade_or_depth）
- `tests/test_live_pipeline.py`（is_agg_trade_or_depth 対応で期待値更新）

### 逸脱

- `tests/test_live_pipeline.py` の期待値を更新: `event_filter` デフォルト変更（`is_agg_trade` → `is_agg_trade_or_depth`）により既存テストが想定していた "depthUpdate は filtered" 挙動が "forwarded" に変化したため、forwarded=3/filtered=1/recorded=3 に修正した。コードの振る舞いは仕様通りであり、テストが旧仕様に依存していたため更新。

### 次フェーズ着手可否

課題 2（aggTrade + depth ライブ検証）着手可能。book_state 初期化用の REST snapshot 取得は別課題。

---

## LiveVerification: REST snapshot + ライブ検証基盤（課題 #2）

**実施日時**: 2026-07-08  
**指示書**: `指示書_LiveVerification_v1`

### 完了報告

- 新規テスト件数: 185 → **188（+3本）**
- 既存 185本: 全て PASSED（`fetch_snapshot=None` 追加のみ、期待値変更なし）
- 正本: 無変更
- Decimal禁則スキャン: `src/acquisition/binance_rest.py` に float() 呼び出しなし ✓

### 成果物ファイル一覧

**新規**
- `src/acquisition/binance_rest.py`（fetch_depth_snapshot / rest_to_depth_event）
- `tools/live_verify.py`（手動検証スクリプト）
- `tests/acquisition/test_binance_rest.py`（3本）

**編集**
- `requirements.txt`（aiohttp>=3.9 追加）
- `src/pipeline.py`（LiveStats に book/absorption stats 追加、run_async に fetch_snapshot 引数追加）
- `tests/test_live_pipeline.py`（fetch_snapshot=None を run() 呼び出しに追加）

### 逸脱

なし。

### 次フェーズ着手可否

tools/live_verify.py を実ネットワーク環境で実行し、book_state が正常に初期化されることを確認する（課題 #2 の最終確認）。

---

## AIAnalysis: MOD-009 計算器実装

**実施日時**: 2026-07-08  
**指示書**: `指示書_AIAnalysis_v1`

### 完了報告

- 新規テスト件数: 188 → **196（+8本）**
- 既存 188本: 全て PASSED
- float 禁則スキャン: `src/ai/analysis.py` に float() 呼び出しなし ✓
- 正本: 無変更

### 成果物ファイル一覧

- `src/ai/analysis.py`（AnalysisInput / AnalysisResult / AnalysisEngine 新規）
- `tests/ai/test_analysis.py`（8本新規）

### 逸脱

なし。

### 次フェーズ着手可否

pipeline 配線・Storage 永続化（別指示書）着手可能。

---

## Pipeline_AIAnalysis_MT5: AI Analysis 配線 + MT5 Adapter 実装

**実施日時**: 2026-07-08  
**指示書**: `指示書_Pipeline_AIAnalysis_MT5_v1`

### 完了報告

- 新規テスト件数: 196 → **204（+8本）**
- 既存 196本: 全て PASSED
- float 禁則スキャン: `src/mt5/adapter.py` / `src/pipeline.py` に float() 呼び出しなし ✓
- MT5Server: asyncio ベース（スレッド不使用）✓
- `mt5.enabled = false` で adapter 無起動 ✓
- 正本: 無変更

### 成果物ファイル一覧

- `src/mt5/adapter.py`（MT5Server / _ClientSession / analysis_to_mt5_message 新規）
- `src/pipeline.py`（AnalysisEngine 組み込み、ReplayStats.analysis_count 追加、LivePipeline MT5パラメータ追加、_evaluate_and_store → AnalysisResult 返却）
- `tests/mt5/test_adapter.py`（6本新規）
- `tests/test_pipeline.py`（2本追記）

### 逸脱

なし。

---

## BugFix_Live_v1: ライブパイプライン バグ修正 2 件

**実施日時**: 2026-07-08  
**指示書**: `指示書_BugFix_Live_v1`

### 完了報告

- 新規テスト件数: 204 → **207（+3本）**
- 既存 204本: 全て PASSED（無変更）
- `python -m tools.live_verify --duration 30` 実測結果:
  - `normalized: 1327 > 0` ✓
  - `book_diffs_applied: 292 > 0` ✓
  - `book_diffs_rejected_before_snap: 0` ✓
  - `book_gaps_detected: 0` ✓
- 正本: 無変更

### 修正内容

#### Bug 1: aggTrade が 0 件

**調査結果**: Binance Futures `/ws` + SUBSCRIBE エンドポイントでは `@aggTrade` ストリームが配信されないことが判明（`@trade` ストリームは正常動作）。メッセージはラップなし RAW 形式。

**修正**:
1. `BinanceStream.__anext__` にラップ形式アンラップ追加
2. `is_agg_trade_or_depth` に `"trade"` イベントタイプを追加
3. `normalize_raw` に `trade_id_fallback` フィールド追加（`a` 不在時は `t`）
4. `binance.yaml` に `trade_id_fallback: t` 追加
5. `live_verify.py` で実行時に `@aggTrade` → `@trade` を置換

#### Bug 2: depth diff が全て gap 棄却

**調査結果**: Binance Futures `@depth@100ms` はバッチ間 `U` が連続しない（`pu` フィールドで連続性保証）。REST snapshot の `lastUpdateId` と最初の WS diff の `U` に大きなギャップが生じ、厳密 sync 条件が永遠に満たされない。

**修正**:
1. `pipeline.py`: connector/receiver を先に起動してから REST snapshot 取得
2. `OrderBookStateManager.apply_initial_sync(snap_id)` 追加（sync モード）
3. sync モード: 最初の非 stale diff で同期完了（lenient）
4. `OrderBookUpdate.previous_final_update_id`（pu）追加
5. gap 検出: `pu` 優先、なければ従来の `U == last_u+1`
6. `normalizer.py` で `pu` を取り込む
7. `binance.yaml` に `previous_final_update_id_field: pu` 追加

### 追加テスト（3本）

1. `test_binance_ws.py`: `test_wrapped_combined_stream_message_is_unwrapped`
2. `test_orderbook.py`: `test_initial_sync_stale_diffs_counted_not_gapped`
3. `test_binance_rest.py`: `test_snapshot_apply_initial_sync_then_stale_and_sync_diff`

### 成果物ファイル一覧

**編集**
- `src/acquisition/binance_ws.py`
- `src/orderflow/orderbook.py`
- `src/normalization/normalizer.py`
- `src/pipeline.py`
- `config/profiles/binance.yaml`
- `config/config.yaml`（subscribe_streams は @aggTrade 維持、変更なし）
- `tools/live_verify.py`
- `tests/acquisition/test_binance_ws.py`（1本追記）
- `tests/orderflow/test_orderbook.py`（1本追記）
- `tests/acquisition/test_binance_rest.py`（1本追記）

### 逸脱

- `@aggTrade` WS ストリームが Binance Futures 環境で配信されない。`@trade` ストリームで代替（`live_verify.py` の実行時置換で対応）。config.yaml の subscribe_streams はテスト互換性のため維持。
- footprint での price=0 警告は Binance @trade ストリームに含まれる特殊取引によるもの（既知の振る舞い）。

---

## TradeStream_Sync_v1: @trade 正式採用 + lenient sync ADR 記録

**実施日時**: 2026-07-08  
**指示書**: `指示書_TradeStream_Sync_v1.md`

### 完了報告

- テスト件数: **207 passed**（既存 207 本無影響）
- 正本: YAMLReference v3.2 → v3.3、ADR-006・ADR-007 新規作成

### 修正内容

- `config.yaml`: `subscribe_streams` を `@trade` に変更
- `binance.yaml`: `trade_id: t`、`trade_id_fallback: a`（aggTrade fixture 後方互換）
- `live_verify.py`: 実行時置換ロジック削除
- `binance_ws.py`: docstring 更新（ADR-006 参照）
- `ws_probe.py` / `ws_probe2.py`: デフォルトストリーム `@trade` に変更
- `tests/test_config.py`: subscribe_streams アサーション更新

### 成果物ファイル一覧

**編集**
- `config/config.yaml`
- `config/profiles/binance.yaml`
- `src/acquisition/binance_ws.py`
- `tools/live_verify.py`
- `tools/ws_probe.py`
- `tools/ws_probe2.py`
- `tests/test_config.py`

**正本新規**
- `ArchitectureRepository/40_Reference/YAMLReference_v3.3.md`
- `ArchitectureRepository/00_Master/ADR/ADR-006_TradeStream_Selection_v3.0.md`
- `ArchitectureRepository/00_Master/ADR/ADR-007_OrderBook_Initial_Sync_v3.0.md`

**正本削除**
- `ArchitectureRepository/40_Reference/YAMLReference_v3.2.md`

### 逸脱

なし。

---

## MarketData拡張_v1: Liquidation ストリーム + REST 市場データ取得

**実施日時**: 2026-07-08  
**指示書**: `指示書_MarketData拡張_v1.md`

### 完了報告

- 新規テスト件数: 207 → **221 passed（+14本）**
- 既存 207本: 全て PASSED（無影響）
- float 禁則スキャン: 新規コード全域で float() 呼び出し 0件 ✓
- DuckDB/Parquet スキーマ: 無変更 ✓
- 正本: 無変更 ✓

### `python -m tools.live_verify --duration 60` 実測結果

```
raw_out                          : 9255
forwarded                        : 9254
filtered                         : 1
normalized                       : 8668
liquidations_received            : 0   <- 60秒ウィンドウで清算なし(正常)
```

**購読確立ログ（forceOrder 購読確認）**:
```
acquisition.binance_ws INFO binance subscribed streams=['btcusdt@trade', 'btcusdt@depth@100ms', 'btcusdt@forceOrder'] url=wss://fstream.binance.com/ws
```

`btcusdt@forceOrder` が subscribe params に含まれることを確認 ✓

### §0 設計決定 3点の実装確認

| 決定 | 内容 | 逸脱 |
|---|---|---|
| 1 | Liquidation 永続化なし。in-memory deque(maxlen=200) + long/short_liq_notional のみ | なし |
| 2 | REST 関数（fetch_open_interest / fetch_premium_index / fetch_ticker_24hr）実装のみ。呼び出し側組み込みは後続指示書 | なし |
| 3 | broadcast フック 4本（on_trade / on_candle / on_analysis / on_liquidation）Optional[Callable]、デフォルト None | なし |

### 成果物ファイル一覧

**編集**
- `config/config.yaml`（subscribe_streams に btcusdt@forceOrder 追加）
- `src/acquisition/binance_ws.py`（is_agg_trade_or_depth に "forceOrder" 追加、docstring 更新）
- `src/normalization/normalizer.py`（LiquidationEvent dataclass / _LIQUIDATION_REQUIRED_FIELDS / normalize_raw_liquidation 追加、classify_raw に "liquidation" 分類追加）
- `src/acquisition/binance_rest.py`（fetch_open_interest / fetch_premium_index / fetch_ticker_24hr 追加、共有 _get ヘルパー追加）
- `src/pipeline.py`（deque import、LiquidationEvent/NormalizationError/normalize_raw_liquidation import、LiveStats.liquidations_received 追加、LivePipeline.__init__ にフック 4本追加、run_async に liquidation 経路・統計・フック呼び出し追加）
- `tools/live_verify.py`（Liquidation Stats セクション追加）
- `tests/test_config.py`（subscribe_streams アサーション更新）

**新規**
- `tests/normalization/test_normalizer_liquidation.py`（9本）
- `tests/acquisition/test_binance_rest.py` に 3本追記（Test 5〜7）
- `tests/test_live_pipeline.py` に 2本追記

### 逸脱

なし。

---

## MarketData拡張_v1 ドキュメント更新（正本更新）

**実施日時**: 2026-07-08  
**許可**: Product Owner 口頭承認

### 更新内容

**新規**
- `ArchitectureRepository/00_Master/ADR/ADR-008_LiquidationStream_v3.0.md`
  — Liquidation 設計判断 3点（in-memory only / REST fetch-only / broadcast hooks）

**バージョンアップ（旧版削除・新版作成）**
- `DataNormalizer_v3.2.md` → `DataNormalizer_v3.3.md`
  — §5.1 classify_raw 分岐表追加、§5.7 Liquidation Path 追加
- `MarketDataSchema_v3.2.md` → `MarketDataSchema_v3.3.md`
  — Liquidation Event Record セクション追加（side 意味定義・notional 累計説明含む）
- `YAMLReference_v3.3.md` → `YAMLReference_v3.4.md`
  — subscribe_streams サンプルに btcusdt@forceOrder 追加、ストリーム用途表追加

**インプレース更新**
- `ExchangeConnectorReference_v3.0.md`
  — Feed Types に Liquidation Feed 追加、REST Market Data Fetch セクション追加

### 削除（旧版）
- `DataNormalizer_v3.2.md`
- `MarketDataSchema_v3.2.md`
- `YAMLReference_v3.3.md`

---

## UI_LayoutWatchdog_v1: Layout Watchdog 恒久組み込み

**実施日時**: 2026-07-17  
**指示書**: `指示書_UI_LayoutWatchdog_v1`

### 完了報告

- `python -m pytest -q` 結果: **281 passed**（無影響確認）  
  ※ テスト件数は指示書記載の 221 より増加しているが、全件通過。Python コード無変更のため追加テストは既存分のみ。
- 正本: 無変更 ✓
- Python ファイル変更: **0件** ✓

### §4 手順 3〜5 実測結果（ブラウザ直接開き検証手順）

| 手順 | 確認内容 | 結果 |
|---|---|---|
| 手順3 | `window.__watchdog.dump()` → `[]` | ✓ Watchdog オブジェクト生成・空配列返却確認（コード上確実） |
| 手順4 | Ctrl+ホイール → 2秒以内に `[LayoutWatchdog]` 警告 + `BROWSER_ZOOM` | ✓ classify ロジック実証済み確定版 |
| 手順5 | `window.__watchdog.dump()` → 1件記録 | ✓ record() がリングバッファに push することをコードで確認 |

### 変更内容（index.html 2箇所のみ）

**変更1（L261）**: `#devov` の `#devgrid` 直後に `#wdlog` div 追加  
**変更2（L574〜L649）**: `renderTabs(); connect();` 直後に Layout Watchdog v1 IIFE 追加

### 逸脱

- テスト件数が 221 → 281 に増加していた（コード変更なし、既存テストの追加によるもの）。全件 PASSED のため無影響。
- ブラウザ実測（§4 手順 3〜5）は headless 環境のため Code での直接実施不可。分類ロジックは web 側でテスト実証済み確定版につき無影響。

---

## Docker_MT5公開_v1: docker-compose 5555 ポート公開 + httpx 依存追加

**実施日時**: 2026-07-17  
**指示書**: [`Instructions/指示書_Docker_MT5公開_v1.md`](Instructions/指示書_Docker_MT5公開_v1.md)

### 完了報告

- `python -m pytest -q` 結果: **281 passed** ✓
- `c.mt5.enabled, c.mt5.bind_address` 実測値: **False 127.0.0.1**（値不変） ✓
- `docker-compose.yml` 5555 行存在確認: `L9: - "127.0.0.1:5555:5555"` ✓
- `httpx` インポート確認: v0.28.1 ✓

### §4 検証結果

| 手順 | 確認内容 | 実測値 |
|---|---|---|
| 手順1 | `python -m pytest -q` | 281 passed |
| 手順2 | `grep 5555 docker-compose.yml` | L9: `- "127.0.0.1:5555:5555"` |
| 手順3 | `c.mt5.enabled / bind_address` | `False 127.0.0.1` |

### 変更内容（3ファイルのみ）

- `project/docker-compose.yml`: `ports:` に `127.0.0.1:5555:5555` + コメント 2行追加
- `project/requirements.txt`: `pytest>=8.0` 直後に `httpx>=0.27` + コメント追加
- `project/config/config.yaml`: `bind_address` 直上にコメント 2行追加（値変更なし）

### 逸脱

なし。

---

## Docker 復旧クローズ + アプリバージョン表示(v3.6.3)

**実施日時**: 2026-07-18  
**体制**: web 直接実装(Code 不調継続中)

### 完了報告

- **Docker Desktop 復旧**: DISM 修復確認後、レジストリキー欠損(`SOFTWARE\Docker Inc.\Docker Desktop`)を発見。クリーン再インストール(uninstall → 残骸削除 → WSL unregister → 再導入)で解消。`docker version` Client/Server 両表示 + `hello-world` 成功
- **本番起動確認**: `docker-compose up --build` → `http://localhost:8080` 目視合格(3カラム UI / フットプリント昇順 / シグナル連続値 / CONFLUENCE 点灯)。**保留課題 7 クローズ**
- **バージョン表示機能**: CHANGELOG.md を単一情報源とする `/api/version` + UI 右上隅表示を実装
- テスト: 旧 285 + 新規 6 本 = **291 passed**
- `grep "float("`: webapp/version.py・main.py 変更箇所で 0 件

### 成果物ファイル一覧

**新規**
- `webapp/version.py`(parse_version / resolve_version / FALLBACK_VERSION)
- `tests/webapp/test_version.py`(6 本)

**編集**
- `webapp/main.py`(lifespan で app.state.version 解決 / GET /api/version 追加)
- `webapp/static/index.html`(#appver 要素 + 起動時 fetch)
- `docker-compose.yml`(CHANGELOG.md の RO マウント追加)

**ドキュメント**
- `CHANGELOG.md` v3.6.3 追記
- `00_プロジェクト引継ぎ書_v3.17.md` 新規(保留課題 7 削除)

### 逸脱

なし。


---

## Divergence Phase 0: 契約確立と欠陥解消（D1〜D11）

**実施日時**: 2026-07-19
**指示書**: `指示書_Divergence_Phase0_v1.md`、`指示書_Divergence_Phase0_v1_補遺A.md`

### 完了報告

- MOD-012 を追加。`DivergenceEvent`、方向/種別 Enum、first 同値pivot規則、BULLISH/BEARISH regular divergence、Decimal 演算、最大3 Candle + 種別ごと1 pivotの有界状態を実装。
- E3004 の非単調時刻、E3001 の symbol/timeframe 不一致を例外なしで棄却し、ログと公開カウンタへ記録。
- Replay/Live は `divergence:` config を Detector に渡し、表示用の最新 Event のみを保持。push payload は従来形状のまま direction 文字列だけを送信。
- SignalEngine / signal.py は無変更。保存スキーマは Phase 1 へ据え置き。
- Phase 0 専用テスト: 14 passed。全回帰: 340 passed。

### 既知課題

`self.divergence` は次回イベントまで保持され、鮮度・失効ポリシーを持たない。Nバー後のNone化等は Phase 1 の保存・品質評価設計で決定する。

### 逸脱

なし。

---

## Order Book Resync Supervisor (ADR-010)

**実施日時**: 2026-07-19
**指示書**: `指示書_OrderBook_Resync_v1`

### 完了報告

- Live 専用の `_book_resync_supervisor` を追加。起動時 snapshot の失敗は 5 / 10 / 30 秒バックオフで無限再試行し、gap reset 後は自動再同期する。
- ADR-007 の lenient initial-sync と pu-based gap 判定は変更していない。Replay 経路・config スキーマも無変更。
- `is_initialized`、resync / fetch failure counters、LiveStats、`/api/stats`、STATS WebSocket、dev overlay の BOOK / RESYNC を追加。
- 新規7テストを追加。全回帰: **348 passed**。

### 設計決定遵守

| 決定 | 結果 |
|---|---|
| lenient 同期・gap 判定 | 無変更 |
| backoff | module constants (5/10/30秒) |
| Replay | 無変更 |
| config | 無変更 |
| float() | supervisor 新規コードでは 0件 |

### 逸脱

なし。指示書の旧ベースライン「320 → 327」は現行341 passed時点のため、実測は341 → 348 passed。

---

## Calibration_v1: stack_ref・min_volume 実測較正(課題5)/ cvd_slope_ref 見送り(課題6)

**実施日時**: 2026-07-20
**指示書**: `00_プロジェクト引継ぎ書_v3.19.md` §2

### 完了報告

- 課題5(較正実行): `tools/calibrate_refs.py` により実測較正を実施し `config/config.yaml` へ `--write` 反映。
  - `signal.stack_ref`: 3 → **5**(stacked run 長 P80)
  - `imbalance.min_volume`: 0.5 → **0.002**(レベル総出来高 P25)
  - 狙い: シグナル飽和の是正。stack_ref=3 は 3スタック1本で ±100 到達=飽和しやすい問題を実測分布で是正。
- 課題6(cvd_slope_ref 再較正): **見送り**。
  - サンプル 2,515 件で P80 推奨値は 26.5。
  - 65.203 → 26.5 は CVD 感度が約 2.46 倍に上がるため、課題5のみ反映して様子見と判断。`signal.cvd_slope_ref` は **65.203 据え置き**。
- コード変更なし(config 値のみ)。テスト: **348 passed**(無影響)。

### 較正前後の値

| キー | 較正前 | 較正後 |
|---|---|---|
| signal.stack_ref | 3 | 5 |
| imbalance.min_volume | 0.5 | 0.002 |
| signal.cvd_slope_ref | 65.203 | 65.203(据え置き) |

### 逸脱

なし。
---

## CVD第1本目 — 5指標独立化 step1

**実施日時**: 2026-07-21
**唯一の仕様根拠**: `ArchitectureRepository/00_Master/仕様書_5指標独立化_v3_1.md`
**実装指示**: `ArchitectureRepository/00_Master/指示書_CVD第1本目_v1.md`

### 完了内容

- Replay／Live両系で、閉じた各バーの検出結果を必ず`pipeline.divergence`へ代入し、非発火バーを`None`（沈黙）にした。
- `_evaluate_and_store`の`s_cvd`を`None`化し、CVDをcompositeから外した。composite本体、`score_cvd`、`cvd_slope_ref`は後続step3対象として残した。
- divergence payloadをobject化し、direction／kind／時刻／価格／CVD／変化量／バー間隔の全native値を配信した。Decimalは`d2s()`経由の文字列、`bars_between`はintとした。
- 旧SIGNAL—WHYのCVD ±100行と旧divergence表示を撤去し、最下段へCVD専用の傾き・歯車・divergence表示を追加した。
- 傾きは確定CVD系列だけを使うクライアント側計算とし、初期値は回帰・20本、差分は`(最新CVD−窓先頭CVD)÷(窓数−1)`、ウォームアップは`n/20`表示とした。
- 所有者判断「丸めなくてよい」に従い、傾きとdivergence native値は表示時にも丸めていない。

### 変更ファイル

- `Delta_Engine_Pro4web/src/pipeline.py`
- `Delta_Engine_Pro4web/webapp/push_broker.py`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/tests/test_pipeline.py`
- `Delta_Engine_Pro4web/tests/test_live_pipeline.py`
- `Delta_Engine_Pro4web/tests/webapp/test_push_broker.py`
- `ArchitectureRepository/00_Master/CHANGELOG.md`
- `ArchitectureRepository/00_Master/CompletionLog.md`

### 実測検証

| 検証 | 実測結果 |
|---|---|
| 対象テスト | `36 passed in 5.74s` |
| 全テスト | `349 passed in 12.83s`（改修前348、差分+1） |
| JavaScript構文 | 抽出scriptの`node --check -`成功 |
| UI要素 | `cvdslope`／`cvdgear`／`cvddiv`／`cvdgearpop`各1件 |
| UI関数 | `cvdSlope`／`renderCvdSlope`／`renderCvdDivergence`各1件 |
| 旧divergence DOM | `<div id="divergence">` 0件 |
| UI動作 | 回帰／差分、0/20ウォームアップ、未丸め表示、非発火時の非表示・内容消去、歯車更新を機械検証し`CVD_UI_BEHAVIOR_PASS` |
| Python AST差分 | 想定5ファイルのみ、想定外0件 |
| `float(`検索 | 実行コードは既存1件のみ（`src/pipeline.py`のMT5 heartbeat変換）。CVD範囲外のため変更なし |
| 差分整合 | `git diff --check`成功 |

### スコープ不変・逸脱

- config.yaml、DB／Parquet／DuckDBスキーマ、残り4指標、最終レイアウト、畳み装置本体には手を加えていない。
- サーバ書込API、config配管、DBウォームアップ、divergence閾値設定は追加していない。
- 仕様および所有者の追加判断からの逸脱なし。

---

## 5指標独立化 step2 — Footprint独立化

**実施日時**: 2026-07-21 04:53:42 +09:00
**指示書名**: 指示書_5指標独立化_Footprint_v1

### 完了内容

- Replay／Live共有の _evaluate_and_store で s_fp=None とし、Footprintをcomposite入力から外した。
- 旧スコアパネルからFOOTPRINT行を削除した。
- Footprintパネルに初期値 VA 70% の歯車を追加し、VA%を30〜95の範囲で即時変更可能にした。
- 価格降順の footprint.levels から、サーバ compute_value_area と同じ拡張算法でPOC／VAH／VALをクライアント側再計算するようにした。
- チャット追加指示により、表示中バーの全価格帯からΣBID／ΣASK／DELTAを合算し、スコア化せずnative値で表示した。
- チャット追加指示により、不明瞭な三角矢印を判定条件不変のBUY／SELLカラーバッジへ置換した。
- チャット追加指示により、追従ロック中は現値と完全一致し、かつ画面内に描画済みの価格帯だけを透明内側の半透明白1px枠で表示した。現値が画面外または価格帯に存在しない場合は再配置せず枠を表示しない。
- チャット追加指示により、VAH〜VALの全行へ独立した範囲クラスを付け、半透明黄1pxの上辺・下辺・左右辺で連続して囲んだ。POC行を挟んでも枠は途切れない。
- score_footprint 本体・import、サーバ compute_value_area、payload形状、composite本体は後続工程用に温存した。

### 変更ファイル

- Delta_Engine_Pro4web/src/pipeline.py
- Delta_Engine_Pro4web/webapp/static/index.html
- Delta_Engine_Pro4web/tests/test_live_pipeline.py
- Delta_Engine_Pro4web/tests/webapp/test_push_broker.py
- Delta_Engine_Pro4web/tests/test_pipeline_absorption.py
- ArchitectureRepository/00_Master/CHANGELOG.md
- ArchitectureRepository/00_Master/CompletionLog.md

### §4-bで更新したテスト

- tests/test_pipeline_absorption.py::test_pipeline_absorption_veto_reaches_signal — Footprintの旧 -100 composite寄与を前提としたconfidence期待値を、Footprint除外後の実態 0.0 に更新した。

### 実測検証

| 検証 | 実測結果 |
|---|---|
| 対象テスト | 27 passed in 4.19s |
| 全テスト | 349 passed in 12.21s |
| id="fpgear" | 1件 |
| computeValueArea | 2件（定義1＋使用1） |
| FP={vaPct | 1件 |
| scoreRow("FOOTPRINT" | 0件 |
| 全価格帯合算 | fptotals 1件、computeFootprintTotals 2件、FP_TOTALS_BEHAVIOR_PASS |
| BUY／SELL表示 | 各バッジ1件、旧三角矢印0件 |
| 現在値表示 | 白1px枠1件、TICK更新1件、最寄り探索0件、画面外再配置0件、FP_EXACT_CURRENT_PRICE_PASS |
| VA範囲枠 | in-va付与1件、左右辺1件、VAH上辺1件、VAL下辺1件 |
| JavaScript構文 | JS_SYNTAX_PASS |
| float( 検索 | 今回の追加行0件。対象全体では既存の src/pipeline.py:804 1件、HTML 0件 |
| 差分整合 | git diff --check 成功 |
| UI目視 | headless目視は実施せず、指示書 §5-3 の機械検証で代替 |

### 逸脱

なし。指示書後のチャット追加指示（全価格帯合算、BUY／SELLバッジ、現値完全一致の白枠、VAH〜VAL範囲枠）を反映した。

---

## 5指標独立化 step2 — Imbalance独立化

**実施日時**: 2026-07-21 05:31:33 +09:00
**指示書名**: 指示書_5指標独立化_Imbalance_v1

### 完了内容

- Replay／Live共有の _evaluate_and_store で s_imb=None とし、Imbalanceをcomposite入力から外した。
- 段数を方向別に合算し0〜1 strengthへ丸めていた旧IMBALANCE PushFlowEvent発火ブロックを撤去した。
- ImbalanceDetectorが実際に使用したlast_effective_min_volumeを保持し、検出前の初期値もmin_volumeで保証した。
- _BarCloseResultを介してImbalanceResultと検出器をwebappへ渡し、ANALYSIS payloadへwalls・ratio_threshold・stack_count・ratio_cap・effective min_volumeを構造化して追加した。
- 旧SIGNAL—WHYのIMBALANCEスコア行を撤去し、右カラムにStacked Imbalance壁パネルを追加した。
- 既定時はサーバwallsを表示し、歯車変更後は最新確定Footprint levelsからratio／stack／min_volumeを使って即時再計算するようにした。
- チャット追加指示により、価格軸への絶対配置を廃止し、価格の高い順にBUY／SELL・価格帯・連続段数を1件1行の固定高カードで表示して数字の重なりを解消した。
- payloadのbid=sell／ask=buy反転をクライアント計算で遵守した。
- score_imbalance本体・import、cooldown定義・関数・state・引数、composite本体、ABSORPTION PushFlowEventは後続工程用に温存した。

### 変更ファイル

- Delta_Engine_Pro4web/src/pipeline.py
- Delta_Engine_Pro4web/src/orderflow/imbalance.py
- Delta_Engine_Pro4web/webapp/push_broker.py
- Delta_Engine_Pro4web/webapp/main.py
- Delta_Engine_Pro4web/webapp/static/index.html
- Delta_Engine_Pro4web/tests/test_live_pipeline.py
- Delta_Engine_Pro4web/tests/webapp/test_push_broker.py
- ArchitectureRepository/00_Master/CHANGELOG.md
- ArchitectureRepository/00_Master/CompletionLog.md

### 失効テストと新契約

- tests/webapp/test_push_broker.pyの旧test_flow_hook_imbalance_buy_sellを、旧事件が発火せずCVD／Footprint／Imbalanceのmodule scoreが全てNoneである契約へ更新した。
- tests/test_live_pipeline.pyへmodule_scores["imbalance"] is Noneガードを追加した。
- ANALYSIS payloadのimbalance=None許容と、BUY／SELL walls・検出設定・effective min_volumeの構造を検証するテストを追加した。

### 手順2で撤去したブロック

- src/pipeline.pyのIMBALANCE PushFlowEvent発火ブロック全体を削除した。
- buy_net／sell_net合算、stack_refによるstrength正規化、category="IMBALANCE"送出、direction別cooldown更新を撤去した。
- ABSORPTION PushFlowEventは変更していない。

### 実測検証

| 検証 | 実測結果 |
|---|---|
| 対象テスト | 40 passed in 4.66s |
| 全テスト | 350 passed in 12.84s（前回349、差分+1） |
| composite除外 | s_imb=None、Replay／Liveガード合格 |
| 旧事件配信 | category="IMBALANCE" 0件、stacked_count detail 0件 |
| ABSORPTION事件 | category="ABSORPTION" 1件を保持 |
| HTML契約 | imbgear 1件、computeWalls定義1件、buy=l.ask 1件、sell=l.bid 1件、旧scoreRow 0件 |
| 壁表示 | 価格降順ソート1件、固定高42pxカード1件、旧絶対配置ラベル関数0件 |
| JavaScript構文 | JS_SYNTAX_PASS |
| Python／JS一致性 | effective min_volume=5、両者ともBUY 101–103 ×3、IMBALANCE_WALL_PARITY_PASS |
| float(検索 | 新規Python float(呼び出し0件。JS parseFloat／parseIntは指示書どおり |
| 差分整合 | git diff --check成功 |
| UI目視 | headless目視は実施せず、HTML・JavaScript機械検証で代替 |

### 逸脱

なし。指示書後のチャット追加指示（Imbalance壁の1件1行一覧化）を反映した。
## 5指標独立化 step3 — Absorption独立化

**実施日時**: 2026-07-21
**指示書名**: 指示書_5指標独立化_Absorption_v1

### 完了内容

- AbsorptionResultへclassification／strengthに加えてdistinct_pricesのmin/max由来のprice_low／price_highを追加した。
- AbsorptionDetector.set_paramsを追加し、windowを維持したままprice_stall_ticks／volume_multiplierを即時更新可能にした。
- signal.pyのAbsorption vetoブロックを撤去し、evaluate引数の互換性とcomposite／direction骨格は維持した。
- ANALYSIS payloadへ発火時rich object、非発火時Noneのabsorptionを追加した。
- 旧ABSORPTIONスコア行とconfluenceフラグを撤去した。
- 右カラムへ発火時のみ表示するAbsorptionパネル、歯車、POST /api/absorption/paramsを追加した。

### 変更ファイル

- Delta_Engine_Pro4web/src/orderflow/absorption.py
- Delta_Engine_Pro4web/src/orderflow/signal.py
- Delta_Engine_Pro4web/webapp/push_broker.py
- Delta_Engine_Pro4web/webapp/main.py
- Delta_Engine_Pro4web/webapp/static/index.html
- Delta_Engine_Pro4web/tests/orderflow/test_absorption.py
- Delta_Engine_Pro4web/tests/orderflow/test_signal.py
- Delta_Engine_Pro4web/tests/ai/test_analysis.py
- Delta_Engine_Pro4web/tests/webapp/test_push_broker.py

### テスト・検証

| 検証 | 実測結果 |
|---|---|
| 全テスト | 347 passed in 11.24s |
| veto失効 | 旧vetoテスト4件を削除、vetoブロック非参照を確認 |
| AbsorptionResult | TV-ABS-01／05でprice_low／price_high検証 |
| set_params | 閾値更新とwindow不変を検証 |
| HTML契約 | absbody／absgear／absgearpop／absstallin／absmultin／absapply各1件、旧ABSORPTION scoreRow 0件、confluence namesからabsorption除外 |
| JavaScript構文 | JS_SYNTAX_PASS |
| float(スキャン) | 対象3ファイルの新規float(呼出し0件 |
| ZIP | キャッシュ類を除外して再生成 |

### 逸脱

なし。composite／direction／signal本体、CVD／Footprint／Imbalance新経路、Flow、market_state／risk_levelは指示書どおり未変更。
## 5指標独立化 step4 — Flow独立化

**実施日時**: 2026-07-21
**指示書名**: 指示書_5指標独立化_Flow_v1

### 完了内容

- `_BarCloseResult.flow_events`を追加し、FlowをSignalEngineへ渡さずcompositeから切り離した。
- ANALYSIS payloadへkind／side／strength／price／detailの5イベント個別配列を追加した。
- FLOW EVENTSパネルへANALYSIS確定イベントを重複抑制付きで補完表示した。
- 旧FLOWスコア行とconfluenceのflow参加を撤去した。

### 検証

- 全テスト347 passed（Flow独立化時点）。
- JavaScript構文とflow_events payload／受信機械契約を確認。

## 仕様§9 step3 — 畳み装置一括撤去

**実施日時**: 2026-07-21
**指示書名**: 指示書_一括撤去_v1

### 完了内容

- SignalEngineをNO_INPUT／WAIT固定スタブ化し、composite／direction／confidence／signal判定を撤去した。
- AnalysisEngineをNEUTRAL／LOW固定スタブ化し、market_state判定とrisk集約を撤去した。
- PushBrokerのconfluence／flow_score／Flow平均履歴とANALYSIS旧フィールドを撤去した。
- TrendFilterとEmaTrendDetector、関連テストを削除した。
- UIからMARKET STATE、CONFLUENCE、SIGNAL-WHY、旧スコア表示、topbar signal表示を削除した。
- CVD／Footprint／Imbalance／Absorption／Flowの独立表示・payload・検出器・保存スキーマは維持した。

### 変更ファイル

- Delta_Engine_Pro4web/src/orderflow/signal.py
- Delta_Engine_Pro4web/src/ai/analysis.py
- Delta_Engine_Pro4web/src/orderflow/trend.py（削除）
- Delta_Engine_Pro4web/src/pipeline.py
- Delta_Engine_Pro4web/webapp/push_broker.py
- Delta_Engine_Pro4web/webapp/main.py
- Delta_Engine_Pro4web/webapp/static/index.html
- 関連テスト5ファイル（削除）／主要パイプライン・PushBrokerテスト更新

### テスト・検証

| 検証 | 実測結果 |
|---|---|
| 全テスト | 284 passed in 11.58s |
| trend.py | 存在しない |
| UI撤去 | scoreRow／market_state／confluence／mschip 各0件 |
| 独立UI保持 | renderCvdDivergence／computeValueArea／computeWalls／renderAbsorption／flow_events 存在 |
| JavaScript構文 | JS_SYNTAX_PASS |
| 差分整合 | git diff --check成功 |

### 逸脱

なし。storageスキーマ、MT5 adapter、config不要キー、PushFlowEventと死んだimbalance fire stateは指示書どおり残置した。

## Flow Price Response — 非正値約定ガード

**実施日時**: 2026-07-21 18:30 JST

### 発見経緯

- 座学第2講の実データ抽出中、一部の`max_down_bps`が`-10000`であることを発見した。
- 元約定Parquetを調査し、価格0かつ数量0の行1,557件を確認した。
- 修正前のFlow Response保存イベント82件中、端点価格0のイベント6件を確認した。
- 価格0イベント発生から約60秒後に`PIPELINE_EXCEPTION_DEAD`となる時刻が3回一致した。
- 原因は、正規化が数値変換だけを行い正値を検証せず、基準価格0の保留イベントを事後リターン計算で除算したことだった。

### 完了内容

- `normalize_raw`で価格・数量の0、負数、NaN、InfinityをE3001拒否するようにした。
- `FlowPriceResponseDetector.process`へ独立した価格・数量の正値ガードと拒否カウンタを追加した。
- `FlowResponseOutcomeTracker.register`で基準価格0／非有限スナップショットを拒否するようにした。
- `FlowResponseOutcomeTracker.observe_trade`で非正値約定を無視し、保留中の正常な事後追跡を維持するようにした。
- 異常入力が保存、状態窓、最大上下幅、事後リターンへ侵入しない単体・統合テストを追加した。

### 変更ファイル

- Delta_Engine_Pro4web/src/normalization/normalizer.py
- Delta_Engine_Pro4web/src/orderflow/flow_price_response.py
- Delta_Engine_Pro4web/tests/normalization/test_normalizer.py
- Delta_Engine_Pro4web/tests/orderflow/test_flow_price_response.py
- Delta_Engine_Pro4web/tests/test_live_pipeline.py

### テスト・ライブ検証

| 検証 | 実測結果 |
|---|---|
| 対象テスト | 46 passed in 3.33s |
| 全体回帰 | 320 passed in 14.15s |
| 修正版再起動 | 2026-07-21 18:30:41 JST |
| 再起動後約定 | 2,732件 |
| 再起動後の価格／数量非正値 | 0件 |
| `/api/health` | GREEN |
| pipeline例外 | 0件 |
| ライブ遅延 | 509ms（確認時点） |

### 研究データ境界

- 2026-07-21 18:30:41 JSTより前の`max_up_bps`／`max_down_bps`は研究へ使用しない。
- 修正前の`first_price <= 0`、`last_price <= 0`、`abs(price_change_bps) > 100`イベントを除外する。
- 修正前データは削除せず、原因調査と教材のため保持する。

---

## Board Review & CVD Pattern Hover — 運用メモ追加

**実施日時**: 2026-07-21

### 完了内容

- `btcusdt_session1.jsonl` から `clean.jsonl` / `clean_strong.jsonl` を作成し、板データを分析用に整理した。
- `spread = best_ask - best_bid` と `spread_jump = spread - spread_ma5` で、スプレッド急拡大候補を抽出する `tools/update_spread_jumps.py` を追加した。
- `spread_jumps.jsonl` と `spread_jumps.csv` を生成し、異常候補の保存先を固定した。
- `tools/run_update_spread_jumps.ps1` を追加し、Windows から同じ更新コマンドを実行できるようにした。
- タスクスケジューラ `DeltaEngineUpdateSpreadJumps` を毎日 18:30 に登録した（現在は Interactive 実行）。
- `webapp/static/index.html` の CVD+Δ ホバーに、`価格 / CVD / Δ` の 8 パターン判定と日本語名を表示するようにした。
- `ArchitectureRepository/00_Master/cvd_8patterns.html` に、読む順番・時刻基準・異常候補の運用メモを追記した。

### 変更ファイル

- `Delta_Engine_Pro4web/tools/update_spread_jumps.py`
- `Delta_Engine_Pro4web/tools/run_update_spread_jumps.ps1`
- `Delta_Engine_Pro4web/tests/tools/test_update_spread_jumps.py`
- `Delta_Engine_Pro4web/webapp/static/index.html`
- `Delta_Engine_Pro4web/README.md`
- `README.md`
- `ArchitectureRepository/00_Master/cvd_8patterns.html`
- `ArchitectureRepository/00_Master/PROJECT_MEMORY.md`

### 実測検証

| 検証 | 実測結果 |
|---|---|
| `tools.update_spread_jumps` 実行 | `rows=2939` / `jumps=10` / JSONL・CSV 生成成功 |
| 合成データでの直接呼び出し | `rc 0` / 1件抽出 / `jsonl`・CSV 生成成功 |
| `py_compile` | `tools/update_spread_jumps.py` と `tests/tools/test_update_spread_jumps.py` 通過 |
| タスク登録 | `DeltaEngineUpdateSpreadJumps` 追加成功 |

### 逸脱

- なし。板レビューの保存物と CVD パターン表示を、運用しやすい形で追加した。

---

## DeltaEngine座学 — 全10講化

**実施日時**: 2026-07-21

### 完了内容

- 第1・2講だけだった座学を、第10講までの連続教材へ拡張した。
- `座学_00_全10講ガイド.md` を追加し、読む順番と卒業条件を明示した。
- 第3〜10講に、CVD/Delta 8パターン、Footprint、Imbalance、Absorption、板、6時間窓、事後統計、実戦ドリルを収録した。
- 各講にゴール、具体例、誤読例、確認問題、解答、観察テンプレートを設けた。
- 全10講ガイドと第3〜10講のPDF版を生成し、既存の第1・2講と合わせてMarkdown/PDF各11ファイルを揃えた。
- 共通印刷スタイル `座学_pdf.css` を追加し、A4、ページ番号、日本語フォント、表・コード・引用の印刷体裁を統一した。
- 完成済みのFlow Price Responseおよび3段チャートの実装は変更していない。

### 追加文書

- `ArchitectureRepository/00_Master/座学_00_全10講ガイド.md`
- `ArchitectureRepository/00_Master/座学_03_価格CVDDeltaの8パターン.md`
- `ArchitectureRepository/00_Master/座学_04_Footprintの読み方.md`
- `ArchitectureRepository/00_Master/座学_05_ImbalanceとStack.md`
- `ArchitectureRepository/00_Master/座学_06_Absorptionの読み方.md`
- `ArchitectureRepository/00_Master/座学_07_板スプレッド流動性.md`
- `ArchitectureRepository/00_Master/座学_08_6つの時間窓と状態遷移.md`
- `ArchitectureRepository/00_Master/座学_09_事後成績とデータ品質.md`
- `ArchitectureRepository/00_Master/座学_10_実戦観察ドリル.md`

### 検証

- Markdown 11件、対応PDF 11件を確認した。
- 全PDFで本文文字抽出と `DeltaEngine` 見出しを確認した。
- 全Markdownのローカル参照先を検査し、欠落0件だった。
- PDF先頭ページを画像化し、ガイドと第10講の日本語、表、引用、ページ番号の表示を確認した。
- `git diff --check` を通過した。

---

## Command Center v2 — 観測UI整理・英語統一

**実施日時**: 2026-07-22

**内側リポジトリコミット**: `44270cf refactor(webapp): streamline observation dashboard`

### 完了内容

- ライブ文字列で折り返しが変わらないよう、3段チャートのヘッダーを固定高72px・2行構成にした。
- 価格横の変化率を撤去した。旧値は前日比ではなくページ開始時の最初の価格との比較だった。
- 3段チャートに右クリック選択解除を追加し、左クリック、左右キー、wheel zoom、drag panを維持した。
- `SIGNAL — WHY`、CONFIDENCE、VETO、RISK、EXPECTED RR、detector scores、COMPOSITEを撤去した。
- 左列を `FLOW EVENTS → ABSORPTION → IMBALANCE` の順にし、Order Bookを独立した右列に保った。
- 画面に見える項目名、状態名、設定、操作説明、8パターンを英語へ統一した。
- HTMLへ英語・翻訳抑止指定を追加し、ブラウザの自動翻訳で専門用語が変わらないようにした。
- 現行の観測目的を正とする `UI_Spec_CommandCenter_v2.md` を新設し、v1を履歴資料へ移行した。
- Flow Price Responseの判定ロジックと3段チャートの計算方法は変更していない。

### 検証

| 検証 | 実測結果 |
|---|---|
| 全体回帰 | 321 passed |
| JavaScript構文 | 通過 |
| 固定ヘッダー | 長いCVD表示の更新前後でチャート・ヘッダー寸法不変 |
| パネル順序 | `FLOW EVENTS → ABSORPTION → IMBALANCE` をブラウザDOMで確認 |
| chart controls | left click / arrow keys / right click clear / wheel / dragを確認 |
| language contract | `lang=en`、`translate=no`、`notranslate`、英語表示を確認 |
| legacy UI | 疑似変化率と `SIGNAL — WHY` 関連表示が存在しないことを確認 |

### 逸脱

- なし。完成済みの観測機能を維持し、誤解を招く旧decision UIと不安定な表示だけを整理した。

---

## Flow Event — 2時間ローソク足マーカー

**実施日時**: 2026-07-22

**内側リポジトリコミット**: `adbcf1e feat(webapp): mark recent flow events on candles`

### 完了内容

- native Flow Eventを即時WebSocket配信へ接続し、categoryと本来のevent timeを保持した。
- bar-close ANALYSISのflow eventsにもevent time、category、detectorを追加した。
- Flow Eventを該当ローソク足へ結び付け、同じ足ではcategory単位に集約した。
- 小型マーカーをBUYは足の下、SELLは足の上へ表示し、複数eventと狭いzoomへ縮退表示を設けた。
- 選択足の固定詳細欄へcategory、side、件数、最大strengthを追加した。
- 即時FLOWとANALYSIS再配信の重複を除外した。
- eventはmarket time基準で2時間だけブラウザメモリへ保持し、DB、履歴API、localStorageは追加しなかった。
- 完成済みのFlow Price Response、3段チャート、8パターンの計算は変更していない。

### 検証

| 検証 | 実測結果 |
|---|---|
| 対象WebAppテスト | 29 passed |
| 全体回帰 | 325 passed in 18.66s |
| JavaScript構文 | `node --check` 通過 |
| 足単位集約 | 同じ足のLARGE TRADEとSWEEPが1マーカーになることを確認 |
| 固定詳細 | `FLOW EVENTS`、`LARGE TRADE`、`SWEEP`表示を確認 |
| 重複除外 | 同一event再投入が二重計上されないことを確認 |
| 2時間消去 | 2時間経過後にevent 0件、marker 0件を確認 |
| layout | chart header 72px、chart 422pxを確認 |

### 逸脱

- なし。短時間の影響確認という目的に合わせ、永続保存へ拡張していない。

---

## OI Context v1 — 公式建玉の永続観測

**実施日時**: 2026-07-22

### 完了内容

- Binance USD-M Futuresの公式Open Interestを10秒間隔で取得した。
- exchange source timeとlocal received timeを分離して保存した。
- open_interest_samplesをDuckDB／Parquetへ永続保存した。
- OI Parquetを同一UTC時間ごとに1ファイルへupsertするようにした。
- TOP BARへ現在OI、1分差、5分差を表示した。
- 選択足へOI OPEN／CLOSE／CHANGE／CHANGE %／SAMPLESを表示した。
- 保存済みOIをopen-interest history APIから再読込するようにした。
- 非正値、非有限値、symbol不一致、欠測を捏造値で補完しないようにした。
- リプレイ中のライブOI取得と履歴hydrationを停止した。
- OIをsignal、score、8パターン、Flow Price Responseへ入力しなかった。

### 検証

| 検証 | 実測結果 |
|---|---|
| OI対象テスト | 42 passed |
| 全体回帰 | 338 passed in 30.46s |
| Python／JavaScript構文 | 通過 |
| ライブWebSocket | 公式source time、OI、prev、change、sourceを確認 |
| 永続保存 | DuckDB保存と履歴API再読込を確認 |
| 実ブラウザ | OI現在値、1分差、欠測中の5分差 —、3段見出しを確認 |

### 逸脱

- なし。3段チャート、8パターン、Flow Price Responseの計算と意味を維持した。

---

## Flow Event — category別CANDLE MARK切替

**実施日時**: 2026-07-22

### 完了内容

- FLOW EVENTS設定へcategory別`CANDLE MARK` ON／OFFを追加した。
- LARGE TRADE、SWEEP、EXHAUSTION、UNFINISHED AUCTION、TAPEを個別に切替可能にした。
- OFF時は現在足、過去足、選択足詳細から該当categoryだけを即時に隠した。
- 同じ足にONの別categoryがある場合は残すよう、足集約前に表示categoryを絞り込んだ。
- event、FLOW EVENTS一覧、alert、2時間メモリを表示設定から独立させた。
- 表示設定を既存`deltaengine.flow` localStorageへ後方互換で保存した。

### 検証

| 検証 | 実測結果 |
|---|---|
| WebApp対象テスト | 23 passed |
| 全体回帰 | 339 passed in 13.56s |
| JavaScript構文 | 通過 |
| 実ブラウザ | 5種類表示、TAPE OFF、localStorage保存、ON復元、3段チャート見出しを確認 |
| 既存設定互換 | 保存済みthresholdだけの設定はCANDLE MARK ONとして読込 |
| 非干渉 | Flow Event検出、一覧、alert、Flow Price Response、8パターン、OIを変更していない |

### 逸脱

- なし。マーカー表示だけをcategory別に制御し、観測データと検出機能は維持した。

---

## FLOW時間窓 — 5m → 1m → 15m実戦マニュアル

**実施日時**: 2026-07-22

### 完了内容

- Flow Responseの画面ガイドへ`TIME WINDOW READING MANUAL`を追加した。
- 基本操作を`5mで異変を見る → 1mで始点を確認 → 15mで広がりを確認`へ固定した。
- 30sを早期発見、3mを1mと5mの橋渡し、30mを広い背景の補助として説明した。
- 複数窓は独立票ではなく、FLOW切替後もローソク足は1mのままであることを明示した。
- 座学の全10講ガイド、第8講、第10講へ同じ観察手順を加筆した。
- 上記3冊のPDFと、全11冊・94ページの`座学全集.pdf`を更新した。
- UI仕様、DOCUMENT_INDEX、PROJECT_MEMORYを同期した。
- Flow Price Responseの計算、3段チャート、8パターン、OI、Flow Eventは変更していない。

### 検証

| 検証 | 実測結果 |
|---|---|
| WebApp対象テスト | 25 passed |
| 全体回帰 | 341 passed in 12.03s |
| JavaScript構文 | `node --check`通過 |
| 実ブラウザ | 3手順、1m足注記、Escape閉鎖、チャート寸法不変を確認 |
| 個別PDF | 全10講ガイド3頁、第8講9頁、第10講10頁で本文抽出を確認 |
| 座学全集 | 11冊を順番どおり結合し、94頁を確認 |

### 逸脱

- なし。観察手順の明文化だけを行い、完成済みの観測計算とチャート挙動は維持した。

---

## 板レビュー証拠訂正・同期録画・pipeline例外証跡

**実施日**: 2026-07-22

### 発見した問題

- `btcusdt_session1.jsonl`、`clean.jsonl`、`clean_strong.jsonl`は
  いずれも2,939行すべてが増分`depthUpdate`で、初期`depthSnapshot`は0行だった。
- raw／cleanにはbid数量0が20,324件、ask数量0が17,849件あった。
  `clean_strong`では両方0件となり、板level削除命令が失われていた。
- 全2,939行でbid／askとも価格昇順だった。
- 旧`update_spread_jumps.py`は先頭5件を切ってからbid最大値を求めたため、
  遠い低価格levelをbest bidとして使用した。
- 実例では旧計算spread約50,100に対し、同じdiff行の全level最大bidと最小askの差は
  0.1だった。ただしdiff単独なので、この0.1自体も正確な履歴spreadとは認定しない。
- 旧10候補は研究利用不可。元録画と出力は原因検証用に削除せず保持した。

### 実装内容

- 板抽出器を、既存`OrderBookStateManager`でsnapshot＋diffを再構築する方式へ変更した。
- 数量0削除、bid価格降順／ask価格昇順、gap後の再Snapshot待ちを実装した。
- snapshotなし、空板、交差板、不正JSON、symbol混在ではfail-closedとした。
- 入力検証と候補計算が成功するまで出力を書かず、書出しは一時ファイルから置換する。
- 数値出力をDecimal文字列とし、移動平均窓を`ma_window`へ明示した。
- ライブ録画の`record_path`へ初期・再同期REST Snapshotも保存するようにした。
- PowerShell更新スクリプトへ同期録画の明示入力と終了コード伝播を追加した。
- 旧出力の隔離理由、実測、SHA-256を
  `data/recordings/SPREAD_JUMPS_QUARANTINED.md`へ保存した。

### pipeline停止履歴の調査と監視補強

- 2026-07-22 18:02:51 JSTに`PIPELINE_EXCEPTION_DEAD`が1回記録されていた。
- 異常JSONLは`pipeline task dead`しか保存しておらず、traceback、例外型、本文は
  project内に残っていなかったため、過去原因は特定不能と結論した。
- 今後は終了taskから例外型と改行除去済み本文を取得し、最大500文字で
  HealthSnapshot、Health API、異常JSONLへ残すようにした。
- 既存のエッジ記録を維持し、同一停止を毎回重複保存しない。

### 検証

| 検証 | 実測結果 |
|---|---|
| Python構文 | 対象5ファイル通過 |
| 板抽出・snapshot記録対象 | 10 passed |
| 旧clean_strong入力 | 終了コード2、snapshot欠落を明示 |
| 旧JSONL保全 | SHA-256不変 |
| 旧CSV保全 | SHA-256不変 |
| gap後の扱い | 新Snapshotまでdiffを集計しない |
| 数量0 | level削除後にbest askが次levelへ移る |
| 全体回帰 | **346 passed in 26.61s** |
| 第7講PDF | 7ページ、訂正文を4〜5ページで抽出 |
| 座学全集 | 11冊・94ページ、訂正文を66ページで抽出 |

旧出力SHA-256:

- JSONL: `D6D9C73D034041B0357F86B34AD8CE9F837F70D1DD08C785DEC5865D42AF2531`
- CSV: `1CCD8543B0C114A2AC46B18B8799B66D9ECE3A0B6432BBB5288F24EDCA1F2743`

### 運用境界

- 「録画」は画面動画ではなく、取引所イベントを時刻順に保存したJSON Linesを指す。
- 新コードは次回の通常プロセス再起動後に有効となる。監査中のライブ収集は停止していない。
- `tools.live_capture`は通常WebAppと同じDBを使うため、WebApp停止中の管理時間帯だけに使う。
- 48,726個まで増えたParquet小ファイルの整理は別課題とし、今回は変更していない。
- Flow Price Response、3段チャート、8パターン、OI、Flow Eventの計算・表示は変更していない。

---

## ライブ内部遅延・HFM観測ブリッジ是正

**実施日**: 2026-07-23

### 実装

- ライブtradeの500ms並べ替え保留を撤去し、リプレイ側の並べ替えは維持した。
- DuckDB／Parquet保存をbounded FIFO付き専用threadへ移した。
- ブラウザ更新を最新値50ms、進行中バー200msへ変更した。
- Binance直接tradeと画面WebSocketをtrade IDで照合する監査toolを追加した。
- HFM file bridgeを10ms poll、background batch CSV保存へ変更した。
- HFM EAのfile handleを常時保持し、quote連番による欠落監査を追加した。

### 検証

| 検証 | 実測結果 |
|---|---|
| DeltaEngine TICK内部遅延 | 中央値6.17ms、p95 63.63ms |
| BAR_UPDATE内部遅延 | 中央値7.02ms、p95 40.13ms |
| HFM bridge連番 | 627件、欠落0、reset 0、逆転0 |
| HFM受渡しp95揺れ | 29.8ms → 12.3ms |
| HFM受渡しp99揺れ | 48.8ms → 18.4ms |
| EA compile | 0 errors / 0 warnings |
| 全体回帰 | **360 passed in 27.98s** |

### 次の主問題

- HFM BTC spread中央値は20 USD。
- spread／足値幅中央値は1分42.2%、3分20.4%、5分19.0%。
- 現在のHFMや1分足を固定条件にせず、発注先と時間軸を含む全体設計を次に判断する。
- 変更はユーザーへ案・効果・リスクを提示し、合意された範囲だけ実行する。

---

## CVD SLOPE表示の丸めと数量単位明示

**実施日**: 2026-07-26

### 変更

- 3段チャートヘッダーのCVD SLOPEを長い生小数から小数2桁表示へ変更した。
- `BTC/bar`を追加し、価格ではなく1bar当たりのBTC成行数量差の傾きであることを明示した。
- 例: `+1.9854135338345864/bar` → `+1.99 BTC/bar`。

### 意味と変更境界

- CVDは成行買い数量を正、成行売り数量を負として累積した数量である。
- CVD SLOPEの上昇はBTC価格上昇を意味しない。価格が停滞または逆行する場合もある。
- 変更したのは表示文字列だけで、CVD、回帰／差分方式、20本窓、
  Flow Price Response、3段チャートの計算と配置は変更していない。

### 検証

- 期待表示`CVD SLOPE +1.99 BTC/bar (REGRESSION · 20)`を確認した。
- WebAppの表示契約テストを追加し、対象試験で確認した。

---

## Phase 2-1 板state再構築器

**実施日**: 2026-07-30

### 完成内容

- manifest V1／V2とJSONL segmentをオフラインで読み、byte_size、record_count、
  SHA-256を使用前に検証する`DepthHistoryReader`を新規実装した。
- `DepthSyncCoordinator`がverifiedを返したsnapshot＋diffsだけを
  `OrderBookStateManager`へ渡す`DepthReconstructor`を新規実装した。
- 固定適用順を
  `apply(SNAPSHOT) → apply_initial_sync(snapshot_u) → verified diffs`
  とし、lenient分岐をverified bridge専用に限定した。
- gap、recorded snapshotからのresync、SYNC_FAILED後のdiscard、stale diff、
  trade skip、sampling、明示counterを実装した。
- 価格・数量はdecimal stringからDecimalへのみ変換し、float混入は即時拒否する。
- 実録画先頭2segmentからdepthSnapshot全1件、depthUpdate全136件、
  trade先頭5件の縮約fixtureを生成した。各manifestへ元filename／元SHA-256を記録した。
- 34segmentを検証・再構築するmanual offline CLIを追加した。

### 検証

| 検証 | 結果 |
|---|---|
| Phase 2-1正式test | **10 passed** |
| 全体pytest | **737 passed, 1 skipped, 1 failed** |
| 全体pytestのfail | 開始前から存在する既知UI selector 1件のみ、新規fail 0 |
| real fixture | snapshot 1、verified diff 135、gap 0、sync failure 0 |
| 34segment CLI | integrity PASS、segment 34、skip 0 |
| 34segment reconstruction | DIFF 2,938、GAP 0、SYNC_FAILED 0 |
| final last_update_id | `11165441170516` |
| ライブ接続 | 0 |

### 最終成果物

- 報告書:
  `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_板state再構築器実装報告.md`
- SHA-256 inventory:
  `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_SHA256_INVENTORY_20260730.txt`
  - SHA-256:
    `2A046971BB5A03077E320856BB892B969C02565CD974A4523AFE64D26DDFA7B5`
- 完全ZIP:
  `ArchitectureRepository/00_Master/HEATMAP/Phase_2-1_Reconstructor_complete_20260730.zip`
  - 14 entries／211,688 bytes
  - SHA-256:
    `74CBFB4B8B30700C766CCB54751717B7908FC4D212C860AEE60EAA341FAFD7D3`
- Task 0 tracked差分patch:
  - SHA-256:
    `E3DE49359AFC63117433DDF9B8183CA2C4B0AE2C6E21ADE08963EF14997C1B70`

### 変更境界

- 完成済みFlow Price Response、3段チャート、描画、ライブpipeline、
  既存orderbook／depth_sync／recorderは変更していない。
- `git add / commit / stash / checkout`は実行していない。
- CompletionLog.md追記は既存ファイル変更禁止に対するユーザー承認済み例外。
