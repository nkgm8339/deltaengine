この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_Pipeline_AIAnalysis_MT5_v1

**対象**: AI Analysis pipeline 配線 + MT5 Adapter 実装
**参照正本**: AIAnalysis_v3.1.md / MT5Adapter_v3.0.md / JSONSchema_v3.2.md §3
**前提**: 196 passed。`src/ai/analysis.py` の AnalysisEngine 実装済み。

---

## 0. スコープ

1. `_evaluate_and_store` に AnalysisEngine を組み込み、AnalysisResult を生成
2. MT5 Adapter（TCP socket server）を新規実装
3. pipeline から MT5 Adapter へ AnalysisResult / CVD / Imbalance / Absorption を push
4. テスト

正本無変更。

---

## 1. pipeline.py 配線

### 1.1 AnalysisEngine 組み込み

`_evaluate_and_store` に `analysis_engine: AnalysisEngine` 引数を追加。SignalResult 取得後:

```python
analysis_input = AnalysisInput(
    analysis_time=candle.bar_time,
    symbol=candle.symbol,
    signal_result=signal_result,
    cvd_delta=candle.delta,
    fp_buy_total=buy_total,
    fp_sell_total=sell_total,
    imbalance_result=imbalance_result,
    absorption_result=absorption_result,
)
analysis_result = analysis_engine.evaluate(analysis_input)
```

`analysis_result` を返す（現在 `_evaluate_and_store` は None を返す → `AnalysisResult` を返すよう変更）。

### 1.2 MT5 push

`_evaluate_and_store` の呼び出し元で、返却された `analysis_result` を MT5 Adapter に push する（§2 参照）。

ReplayPipeline / LivePipeline の両方で AnalysisEngine を構築し `_evaluate_and_store` に渡す。`from_config` には `confidence_threshold` パラメータ不要（デフォルト 0.70 で固定）。

---

## 2. MT5 Adapter（新規: `src/mt5/adapter.py`）

### 2.1 MT5Server

```python
class MT5Server:
    def __init__(
        self,
        bind_address: str = "127.0.0.1",
        port: int = 5555,
        max_clients: int = 3,
        heartbeat_interval: float = 5.0,
        max_buffer_messages: int = 1000,
    ) -> None: ...

    async def start(self) -> None:
        """asyncio.start_server で listen 開始。"""

    async def stop(self) -> None:
        """サーバー停止、全クライアント切断。"""

    async def broadcast(self, msg: dict) -> None:
        """全接続クライアントに newline-delimited JSON を送信。
        slow consumer は §2.3 のドロップポリシー適用。"""
```

### 2.2 メッセージ形式（MT5Adapter_v3.0 §5.1 準拠）

```json
{"type": "SIGNAL", "time": "...", "symbol": "...", "payload": {...}}
```

type は `SIGNAL | CVD | IMBALANCE | ABSORPTION | HEARTBEAT`。

AnalysisResult から SIGNAL メッセージを構築するヘルパー:

```python
def analysis_to_mt5_message(result: AnalysisResult) -> dict:
    return {
        "type": "SIGNAL",
        "time": result.analysis_time.isoformat(),
        "symbol": result.symbol,
        "payload": {
            "market_state": result.market_state,
            "confidence": str(result.confidence),
            "risk_level": result.risk_level,
            "summary": result.summary,
            "reasons": list(result.reasons),
        },
    }
```

### 2.3 ドロップポリシー（MT5Adapter_v3.0 §5.2）

クライアントごとに asyncio.Queue(maxsize=max_buffer_messages) を持つ。満杯時:
1. 非 SIGNAL メッセージを古い順にドロップ
2. それでも満杯なら SIGNAL をドロップ
3. ドロップ件数をカウント・ログ

### 2.4 Heartbeat

`heartbeat_interval` 秒ごとに `{"type": "HEARTBEAT", ...}` を送信。クライアントからの ACK を 3 回連続欠落で切断。

### 2.5 config

`config.yaml` の `mt5:` セクション（正本 §6 のデフォルト値）:

```yaml
mt5:
  enabled: true
  bind_address: "127.0.0.1"
  port: 5555
  max_clients: 3
  heartbeat_interval: 5
  max_buffer_messages: 1000
```

`src/config.py` に mt5 スキーマ追加。`mt5.enabled = false` の場合、adapter を起動しない。

### 2.6 Pipeline 統合

- LivePipeline: `run_async` 開始時に `mt5.enabled` なら `MT5Server.start()` をコルーチンとして起動。終了時に `stop()`
- ReplayPipeline: MT5 は起動しない（オフライン分析のため）
- バー確定時に `server.broadcast(analysis_to_mt5_message(result))` を呼ぶ

---

## 3. テスト

### 新規 `tests/mt5/test_adapter.py`（6 本）

1. サーバー start/stop（ポート listen → close）
2. クライアント接続 → SIGNAL broadcast 受信 → JSON パース成功
3. HEARTBEAT 受信
4. max_clients 超過時の接続拒否
5. バッファ満杯時のドロップポリシー（非 SIGNAL 先行ドロップ）
6. クライアント切断後のリソース解放

### 新規 `tests/test_pipeline.py` 追記（2 本）

7. ReplayPipeline で AnalysisResult が生成されること（`_evaluate_and_store` の返却値確認）
8. MT5 disabled 時に adapter が起動しないこと

合計: 196 + 8 = **204 本以上**。既存 196 本無変更。

---

## 4. 完了条件

- [ ] 204 本以上 green、既存 196 本無影響
- [ ] float 禁則 0 件
- [ ] MT5Server が asyncio ベース（スレッド不使用）
- [ ] `mt5.enabled = false` で adapter 無起動
- [ ] 正本無変更

---

## 5. 報告

CompletionLog.md 追記 + `DeltaEngine_PipelineMT5_完了.zip` + チャット報告
