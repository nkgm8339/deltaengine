# Big Trades V2 Phase 0 Completion Report

- 完了時刻: 2026-08-12 01:30:51 JST
- phase: 工程0 baseline／design lock
- status: `COMPLETE_AWAITING_USER_APPROVAL_FOR_PHASE1`
- source implementation: 未着手
- application behavior change: 0

## 1. Restore point

```text
branch = feature/big-trades-v1
HEAD = 8e81cb389d459afa68bb5a85bbe4e593d7bfe19b
tag = pre-big-trades-20260811
tag object = 8e81cb389d459afa68bb5a85bbe4e593d7bfe19b
HEAD == tag = true
tracked staged change = 0
tracked unstaged change = 0
```

工程0完了時点でもapplication source、config、runtime、UIのtracked差分は0。

## 2. Source hash lock

- 起動／test入口: 6 file。
- Big Trades接続予定箇所: 9 file。
- protected source: 9 file。
- missing: 0。
- protected hash mismatch: 0。

詳細は`SOURCE_HASH_MANIFEST.md`。

## 3. Test baseline

```text
python -m pytest -q
1 failed, 846 passed, 1 skipped in 334.12s
```

failure:

```text
tests/webapp/test_dom_tape_fusion_ui.py::test_fixed_fusion_layout_keeps_indicators_and_removes_old_book_presentation
```

既知のUI selector一件と一致。Big Trades由来のfailure 0。

詳細は`PYTEST_BASELINE.md`。

## 4. Runtime／browser baseline

- existing containerを再起動せず取得。
- `/health`、`/api/version`、`/api/health`、`/api/stats`: HTTP 200。
- browser Console error: 0。
- page error: 0。
- failed request: 0。
- local resource response: 全200。
- WebSocket receive: PASS。
- horizontal overflow: 0 px。
- existing screenshot: `existing_app_1280x900_full.png`。
- protected chart geometry: 記録済み。

開始前runtime state:

```text
/api/health = RED
reason = memory RSS 2066 MB
screen = MARKET DATA SYNCING
Tape = TAPE GAP
receiver queue overflow total = 9122
```

これらはV2実装前baselineであり、V2の新規failureとして扱わない。増加量と発生時刻を後工程で比較する。

詳細は`RUNTIME_BROWSER_BASELINE.md`。

## 5. Quantity／settings baseline

production identity:

```text
BINANCE BTCUSDT
price tick = 0.1 USDT
quantity step = 0.001 BTC
```

existing filter:

```text
Flow Event individual LargeTrade Min = 5.0 BTC
Tape MIN QTY = 0
Tape MIN NOTIONAL = 0
Tape LARGE >= 10000 USDT
```

V2専用settingは現行appに存在しない。

read-only sample:

```text
completed Parquet files = 1800
elapsed = 2.903499 hours
raw trades = 523986
V2 40ms clusters = 72657
cluster p99 = 6.297 BTC
cluster p99.5 = 10.149 BTC
cluster p99.9 = 26.486 BTC
cluster max = 205.471 BTC
```

未承認Manual候補:

| Min | Max | observed clusters/hour |
|---:|---:|---:|
| 5 BTC | 0／unbounded | 358.533 |
| 20 BTC | 0／unbounded | 41.674 |
| 50 BTC | 0／unbounded | 8.955 |

production Manual Minは未選択。工程1 pure core開始には不要だが、runtime接続前にuser決定が必要。

詳細は`QUANTITY_SETTINGS_BASELINE.md`。

## 6. Static UI mock

- HTML: `BIG_TRADES_STATIC_UI_MOCK.html`。
- screenshot: `big_trades_static_ui_mock_1280x900.png`。
- screenshot dimensions: 1280×900。
- horizontal overflow: 0 px。
- page errors: 0。
- current application file変更: 0。

mockの配置:

1. existing `PRICE × FLOW RESPONSE` 3段chartを上段に保持。
2. central modeを`FOOTPRINT | HEATMAP | BIG TRADES`にする。
3. Big Trades Canvasへmarker、Reaction Zone、price path、source gapを表示。
4. selected Zone detailへeffortとresult timelineを表示。
5. system factsとuser assessmentを分離。
6. existing Tapeを変更しない。

mock内のManual Min 20 BTCは表示例であり、production採用値ではない。

詳細は`V1_V2_SCOPE_AND_UI_MOCK_REVIEW.md`。

## 7. V1／V1.1からV2への変更

| capability | V1／V1.1 | V2 |
|---|---|---|
| Manual Min／Max | あり | 継承 |
| Automatic Size Filter | あり | 継承 |
| event marker／history | あり | 継承・拡張 |
| execution-range Reaction Zone | なし | 追加 |
| first exit／touch／reentry／cross | なし | 追加 |
| horizon price result | なし | 追加 |
| candle close／wick result | なし | 追加 |
| repeated same-area Big Trade link | なし | 追加 |
| effort／result同一画面比較 | なし | 追加 |

## 8. Existing feature invariance

- protected source 9 file hash delta: 0。
- Flow Price Response source delta: 0。
- CVD／Footprint／Absorption／Imbalance source delta: 0。
- Time & Sales／Footprint Canvas／Heatmap source delta: 0。
- tracked application file delta: 0。
- service restart: 0。
- DB migration／backfill: 0。
- production config change: 0。

## 9. Open decisions

工程1 pure core開始に必要:

- userによる工程1開始承認。

工程2以降までに必要:

- production Manual Minを5／20／50 BTCまたは別値から選ぶ。
- production初期modeをManualまたはAutomaticから選ぶ。
- Automatic scheduleをManual／Weekly／Monthlyから選ぶ。
- calibration activation policyをManual OnlyまたはScheduled Session Boundaryから選ぶ。
- user assessmentを初回releaseへ含めるか決める。

工程5 UI開始までに必要:

- static UI mockの配置承認または修正指示。

## 10. Baseline conditions requiring separation

次は開始前から存在し、Big Trades工程1 pure coreの直接blockerではない。

1. pytest UI selector failure一件。
2. runtime memory health RED。
3. market syncing banner。
4. Tape gap表示。
5. receiver queue overflow／drop累計。

pipeline統合、performance、production activationでは必ず再比較する。値が悪化した場合はV2側の工程を止める。

## 11. Next phase boundary

次に開始可能なのはV2 instruction §60「工程1：pure core」である。

工程1の範囲:

- ordering。
- 40ms aggregation。
- Manual／Automatic pure filter。
- deterministic IDs。
- event／fill models。
- Reaction Zone pure model。
- relation／interaction。
- zone index／price path。
- horizon／candle observation。
- fixed vectorsとpure tests。

工程1でも次は行わない。

- production config変更。
- pipeline接続。
- DB migration。
- WebSocket／API接続。
- current app UI変更。
- service restart。
- feature enable。

工程1開始はuserの明示承認後とする。
