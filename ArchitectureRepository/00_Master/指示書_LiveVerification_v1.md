この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_LiveVerification_v1

**対象**: aggTrade + depth ライブ検証（課題 #2）
**前提**: B-2 完了（185 passed）

---

## 0. スコープ

1. REST depth snapshot 取得モジュール新規作成
2. LivePipeline に snapshot 初期化フロー追加
3. 手動ライブ検証スクリプト新規作成
4. REST 取得のユニットテスト

**正本無変更。pipeline 既存テスト無影響。**

---

## 1. REST snapshot 取得（新規: `src/acquisition/binance_rest.py`）

```python
async def fetch_depth_snapshot(
    symbol: str,
    limit: int = 1000,
    base_url: str = "https://fapi.binance.com",
) -> dict:
    """GET /fapi/v1/depth?symbol={symbol}&limit={limit} → raw dict.

    ConnectionError on HTTP error / timeout.
    """
```

`aiohttp` を使用。レスポンスは Binance Futures REST 形式:
```json
{"lastUpdateId": 123, "E": 1234567890123, "T": 1234567890123,
 "bids": [["100.0","5.0"], ...], "asks": [["101.0","3.0"], ...]}
```

これを normalizer に通すため、`depthSnapshot` 形状に変換するヘルパーを同モジュールに置く:

```python
def rest_to_depth_event(raw_rest: dict, symbol: str) -> dict:
    """REST /depth レスポンスを normalizer.process_depth が受理する形に変換。

    event_type_field = "e" → "depthSnapshot"
    symbol_field = "s" → symbol
    event_time_field = "E" → raw_rest["E"]
    final_update_id_field = "u" → raw_rest["lastUpdateId"]
    bids_field = "b" → raw_rest["bids"]
    asks_field = "a" → raw_rest["asks"]
    """
```

---

## 2. LivePipeline snapshot 初期化

`LivePipeline.run_async` の WS 接続直後・イベント処理ループ開始前に:

1. `fetch_depth_snapshot(symbol)` を呼ぶ
2. `rest_to_depth_event()` で変換
3. `normalizer.process_depth()` → `book_state.apply()` で初期 snapshot 適用
4. `book_state.snapshots_applied == 1` を assert（失敗時は warning log + 続行）

これにより WS の depthUpdate diff が即座に適用可能になる。

**`fetch_depth_snapshot` を `None` に差し替え可能にする**: `run_async` に `fetch_snapshot: Optional[Callable] = fetch_depth_snapshot` 引数を追加。既存テストは `fetch_snapshot=None`（または lambda returning None）で snapshot skip する。既存テストの期待値は変更しない。

---

## 3. 手動ライブ検証スクリプト（新規: `tools/live_verify.py`）

```python
"""aggTrade + depth ライブ検証。

Usage: python -m tools.live_verify --duration 60
"""
```

- config.yaml を読み、LivePipeline を構築して `run_async` を実行
- 終了後に以下を stdout に出力:
  - LiveStats 全フィールド
  - `book_state.snapshots_applied` / `diffs_applied` / `diffs_rejected_before_snapshot` / `gaps_detected`
  - `absorption.events_detected`
  - パス: Parquet / DuckDB ファイルの実サイズ

ネットワーク接続が必要なため pytest には含めない。

---

## 4. テスト

### 新規 `tests/acquisition/test_binance_rest.py`（3 本）

1. `rest_to_depth_event` が正しい形状を返す（normalizer.process_depth で受理→SNAPSHOT 型 OrderBookUpdate）
2. `fetch_depth_snapshot` の HTTP エラー時 ConnectionError（aiohttp モック）
3. snapshot → diff 適用順序テスト: rest_to_depth_event → process_depth → book_state.apply(SNAPSHOT) → diff apply が accepted

### 既存テスト

`test_live_pipeline.py` の 2 本は `fetch_snapshot=None` で既存挙動を維持。**変更しない。**

合計: 185 + 3 = **188 本以上**

---

## 5. 完了条件

- [ ] 188 本以上 green、既存 185 本無影響
- [ ] `fetch_depth_snapshot` がネットワーク不要でテスト可能（モック注入）
- [ ] `tools/live_verify.py` が単体で実行可能
- [ ] 正本無変更

---

## 6. 報告

CompletionLog.md 追記 + `DeltaEngine_LiveVerification_完了.zip` + チャット報告（テスト件数・逸脱有無）
