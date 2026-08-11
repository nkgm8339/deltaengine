# VWAPコード監査

監査日: 2026-07-29 JST
対象: VWAP計算・セッション・Decimal・配信・描画コードのみ
制約: 調査のみ。コード変更・commit・checkout・reset・patchなし。

## 監査結果

【数学】OK

【セッション】OK

【配信】OK（ただしフロントのNumber変換に精度リスクあり）

【描画】OK（フロントでVWAP再計算なし）

## 根拠コード（VWAP関連部分）

### session_vwap.py

```python
class SessionVwapAccumulator:
    """Exact Decimal accumulator for ``sum(price*qty) / sum(qty)``."""

    @property
    def current_value(self) -> Decimal | None:
        if self._volume <= _ZERO:
            return None
        return self._notional / self._volume

    def seed(self, seed: SessionVwapSeed) -> int:
        if seed.symbol != self._symbol:
            raise ValueError(f"seed symbol mismatch: {seed.symbol!r}")
        if self._session_start_ns is not None:
            raise RuntimeError("session VWAP accumulator is already initialized")
        self._session_start_ns = _datetime_ns(seed.session_start)
        self._last_event_ns = _datetime_ns(seed.last_event_time)
        self._last_trade_id = seed.last_trade_id
        self._notional = seed.notional
        self._volume = seed.volume
        self._trade_count = seed.trade_count
        self._session_complete = seed.session_complete
        return self._trade_count

    def observe_trade(self, trade: object) -> bool:
        event_time = _as_utc(getattr(trade, "event_time", None))
        event_ns = _datetime_ns(event_time)
        session_start = _utc_session_start(event_time)
        session_start_ns = _datetime_ns(session_start)
        price = _positive_decimal(getattr(trade, "price", None), "trade price")
        quantity = _positive_decimal(getattr(trade, "quantity", None), "trade quantity")
        trade_id = getattr(trade, "trade_id", None)

        if self._session_start_ns is None or session_start_ns > self._session_start_ns:
            self._reset_session(
                session_start_ns=session_start_ns,
                first_event_time=event_time,
                session_start=session_start,
            )
        elif session_start_ns < self._session_start_ns:
            return False

        if self._last_event_ns is not None:
            if event_ns < self._last_event_ns:
                return False
            if (event_ns == self._last_event_ns
                and self._last_trade_id is not None
                and trade_id <= self._last_trade_id):
                return False

        self._notional += price * quantity
        self._volume += quantity
        self._trade_count += 1
        self._last_event_ns = event_ns
        self._last_trade_id = trade_id
        return True

    def value_at(self, source_time_ns: int) -> Decimal | None:
        if not isinstance(source_time_ns, int):
            raise TypeError("source_time_ns must be int")
        if (self._session_start_ns is None
            or self._last_event_ns is None
            or not self._session_complete
            or self._volume <= _ZERO):
            return None
        if self._last_event_ns > source_time_ns:
            return None
        if _session_start_ns(source_time_ns) != self._session_start_ns:
            return None
        return self._notional / self._volume
```

`_positive_decimal()` は有限かつ正数だけを受け付ける。内部計算は`Decimal`で、計算中の丸めはない。

### snapshot_producer.py

```python
self._session_vwap = SessionVwapAccumulator(symbol)

def seed_session_vwap(self, seed: SessionVwapSeed) -> int:
    return self._session_vwap.seed(seed)

def observe_trade(self, trade: object) -> None:
    self._require_symbol(trade)
    event_time_ns = _datetime_ns(_required_datetime(trade, "event_time"))
    price = _decimal(getattr(trade, "price"))
    if (self._price_history and
        event_time_ns < self._price_history[-1].engine_time_ns):
        return
    if not self._session_vwap.observe_trade(trade):
        return
    self._price_history.append(TimeSample(engine_time_ns=event_time_ns, value=price))

def build_market_state(...):
    observation_time_ns = source_time_ns if source_time_ns is not None else engine_time_ns
    session_vwap = self._session_vwap.value_at(observation_time_ns)
    return MarketStateSnapshot(
        ...,
        session_vwap=session_vwap,
        session_open_avwap=session_vwap,
        ...,
    )
```

### market_state.py

```python
session_vwap: Decimal | None = None
session_open_avwap: Decimal | None = None

for name in ("session_vwap", "session_open_avwap"):
    raw = getattr(self, name)
    if raw is None:
        continue
    value = raw if isinstance(raw, Decimal) else Decimal(str(raw))
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive when present")
    object.__setattr__(self, name, value)
```

### session_vwap_warm_start.py

```python
latest = con.execute(
    "SELECT max(event_time) FROM trades WHERE symbol = ?", [symbol]
).fetchone()[0]
...
aggregate = con.execute(
    "SELECT min(event_time), max(event_time), "
    "sum(price * quantity), sum(quantity), count(*) "
    "FROM trades WHERE symbol = ? "
    "AND event_time >= ? AND event_time < ?",
    [symbol, session_start, session_end],
).fetchone()
...
return SessionVwapSeed(
    symbol=symbol,
    session_start=session_start,
    first_event_time=_as_utc(first_event),
    last_event_time=_as_utc(last_event),
    notional=notional,
    volume=volume,
    trade_count=int(trade_count),
    last_trade_id=int(last_trade_id),
)
```

DB schemaの`trades.price`と`trades.quantity`は`DECIMAL(20,8)`。

### main.py

```python
def _chart_session_vwap(pipeline: Any):
    state = getattr(pipeline, "_last_market_state", None)
    exact = getattr(state, "session_vwap", None)
    if exact is not None:
        return exact, "EXACT"

    producer = getattr(pipeline, "_snapshot_producer", None)
    accumulator = getattr(producer, "_session_vwap", None)
    current = getattr(accumulator, "current_value", None)
    if current is None:
        return None, None
    status = "EXACT" if getattr(accumulator, "session_complete", False) else "PARTIAL"
    return current, status
```

CANDLEとBAR_UPDATEの両方で、上記の値をbrokerへ渡している。Pipeline側は`build_market_state(..., source_time_ns=...)`を呼んでいる。

### push_broker.py

```python
def _vwap_status(value, status):
    if value is None:
        return None
    if status not in {"EXACT", "PARTIAL"}:
        raise ValueError("vwap_status must be EXACT or PARTIAL when vwap is present")
    return status
```

CANDLE/BAR_UPDATE payloadは次の通り。

```python
"vwap": d2s(session_vwap),
"vwap_status": quality,
```

`d2s()`は`Decimal`/`int`を文字列化し、floatを受け付けない。

### history.py

```python
"SELECT bar_time, timeframe, open, high, low, close, volume, delta, cvd, "
"NULL AS vwap, NULL AS vwap_status "
```

履歴DBの既存candlesからVWAPを再計算していない。

### index.html

```javascript
const N=s=>s==null?null:Number(s);

function rememberVwap(p){
  const time=Date.parse(p.bar_time),value=N(p.vwap);
  if(!Number.isFinite(time)||!Number.isFinite(value))return;
  const status=p.vwap_status==="PARTIAL"?"PARTIAL":"EXACT";
  S.vwapHistory.set(time,{value,status});
}

function normalizeMarketBar(raw,live=false){
  const vwap=N(raw.vwap),
    vwapStatus=Number.isFinite(vwap)
      ?(raw.vwap_status==="PARTIAL"?"PARTIAL":"EXACT")
      :null;
  return {...,vwap:Number.isFinite(vwap)?vwap:null,vwapStatus,...,live};
}
```

描画側は受け取った値を使用するだけで、VWAPを再計算していない。

```javascript
const vwapLine=vwapPath
  ?`<path d="${vwapPath}" fill="none" stroke="${WARN}" stroke-width="2.2" stroke-dasharray="7,5"/>`
  :"";
```

### footprint_canvas.js

```javascript
const lines = [
  { value: this.data.vwap, color: CYAN, dash: [5, 4], label: "VWAP" },
  { value: this.data.currentPrice, color: TEXT, dash: [], label: "LAST" },
];
```

ここも再計算せず、`this.data.vwap`を描画するだけ。

## 数学判定

OK。コード上の式は`Σ(price×quantity)/Σ(quantity)`。

## セッション判定

OK。UTC日単位の切替、状態リセット、seed、warm start、途中再起動の復元、`value_at()`のcoverage/time検証が実装されている。

## Decimal判定

Backend: OK。`Decimal`、有限値検証、DB`DECIMAL(20,8)`、文字列payload化。

Frontend: 注意。`index.html`の`Number(s)`でDecimal文字列をIEEE-754 Numberへ変換している。値域によっては末尾精度が失われる。コード上で実際にこの変換が存在するため、精度リスクは確定。

## 配信判定

OK。BackendのDecimal値は、Snapshotの`session_vwap`、`main.py`の投影、`push_broker.py`のCANDLE/BAR_UPDATE、WebSocket JSONへ同じ値として渡される。backend内で別計算はない。

ただし、frontend受信時の`Number(s)`変換で精度が変わり得る。

## 描画判定

OK。`index.html`と`footprint_canvas.js`はpayloadのVWAPを線として描画し、フロント側でVWAPを再計算していない。

## 危険箇所

1. **B: Frontend精度変換**
   - 根拠: `const N=s=>s==null?null:Number(s)`
   - Decimal文字列をNumber化するため、高精度値では表示位置・ラベル値の末尾が変わり得る。

2. **C: payload例外の黙殺**
   - 根拠: `handle()`全体の`catch(_){/* ... */}`
   - malformedなVWAP payloadが届いても、画面にエラーを出さずメッセージ単位で捨てる。

3. **C: 履歴VWAPは常にnull**
   - 根拠: `history.py`の`NULL AS vwap, NULL AS vwap_status`
   - 過去履歴にはVWAPが描画されない。DB履歴に約定単位VWAPが存在しないため、コードは再計算していない。

4. **C: partial表示経路**
   - 根拠: `main.py`が`current_value`を`PARTIAL`として配信。
   - 計算値は式として正しいが、UTC 00:00 coverage不足の値も表示される。statusで区別する契約に依存する。

## 重大度

- S: 該当なし
- A: 該当なし
- B: Frontend Number変換による精度リスク
- C: payload黙殺、履歴null、partial表示の契約依存

## 修正推奨

- VWAP表示値はfrontendでNumber化せず、文字列またはDecimal相当の固定小数処理で保持する。
- VWAP payloadの異常時は、全messageを黙殺せず、VWAP専用の可視警告またはログを出す。
- 履歴VWAPを必要とする場合のみ、約定テーブルのas-of集計APIを別途設計する。OHLCVから推定してはいけない。

## 重大バグ

S/A相当の確定重大バグは確認できない。

確認テスト: VWAP関連既存テストを権限付き環境で実行し、`28 passed`。
