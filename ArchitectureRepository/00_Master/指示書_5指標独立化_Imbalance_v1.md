# 指示書_5指標独立化_Imbalance_v1

## Order Flow Analysis Platform / DeltaEngine ── Codex 実装用

> 母体仕様: `仕様書_5指標独立化_v3.1（確定版）`。本書はその §9 step2 の**3本目＝Imbalance 独立化**のみを実装対象とする。CVD・Footprint は独立済み。
> 実装体制: Codex。根拠はすべて実物（最新 ZIP v3.6.9・Footprint 反映済み）の file:行。推測で経路を書き換えない。本書に無いことを足さない。

---

## 0. Codex への絶対命令

1. **確認や承認を求めず、本書の全手順を上から順に即座に実行せよ。** 途中で選択肢を提示して止まらない。
2. 本書に明記された変更**以外**を一切行わない。「ついで修正」「整形」「リファクタ」を禁ずる。
3. 行番号は着手時点の実物とズレうる。**アンカー文字列（before ブロック）で位置を特定**すること。
4. 完了後、§7 の完了条件（pytest 緑・`float(` スキャン・HTML 機械検証・3点セット）を満たして報告せよ。

---

## 1. スコープ（Imbalance 1指標のみ）

- 本書は **Imbalance だけ**。次の Absorption 以降は別指示書。
- **composite / market_state / signal / confluence / veto の本体撤去は行わない**（全5指標独立後の §9 step3）。本書は Imbalance を composite から**抜く**（`s_imb=None`）だけ。
- Imbalance は3番目。抜いた後も composite には Absorption・Flow が残るため、composite は縮小生存を続ける（無表示区間は生じない）。過渡的に旧 COMPOSITE 等が痩せた不完全値になるのは仕様どおり（§9 但し書き）。**補正しない。**

---

## 2. 確定仕様（お館様承認済み）

Imbalance の native 所見は **「壁」＝ Stacked Imbalance**。見せ方は **案3（価格軸レイアウト）**。

- **案3**: 値段軸の上に壁を帯として置く。価格帯（start〜end）が主役、段数(count)は小さく `×N` で従。方向は色（BUY=緑 / SELL=赤）。
- **事件もの**: 壁が検出されたバーだけ表示。壁ゼロなら沈黙（飾りで点灯させない）。
- **丸めない**: 段数・価格帯を生の数字で出す。0〜1 の strength や共通スケールに畳まない。**現状の strength(0〜1)配信は撤去する。**
- **歯車（その場再計算）**: `ratio_threshold`（初期 3.0）・`stack_count`（初期 3）・`min_volume` を歯車ポップアップで即時調整。CVD/Footprint と同型のクライアント側再計算。

---

## 3. 現在地（実物確認済・根拠付き）

| 事実 | 実物根拠 |
|---|---|
| `s_imb = score_imbalance(...)` が composite に投入中 | `src/pipeline.py:541` |
| 旧 `scoreRow("IMBALANCE", sc.imbalance)` が右パネルに残存 | `webapp/static/index.html:753` |
| 壁の事件配信は strength(0〜1)＋detail文字列に丸めて送出（撤去対象） | `pipeline.py:495-518`（IMBALANCE PushFlowEvent ブロック） |
| その配信は段数を方向ごとに**合算**し、価格帯(start/end)を**捨てている** | `pipeline.py:499-500`（buy_net/sell_net 合算） |
| サーバは壁を検出済み。壁は方向・段数・価格帯を保持 | `src/orderflow/imbalance.py:66-71`（`StackedImbalance`: start_price/end_price/count/direction） |
| `_BarCloseResult.imbalance_result` に壁がある | `pipeline.py:464,563` |
| **payload の bid/ask は反転**（`bid=sell_volume` / `ask=buy_volume`） | `webapp/main.py:107` ★移植で最重要 |
| CANDLE の footprint.levels は**価格降順**で配信 | `main.py:104-109` / `push_broker.py:298` |
| サーバ検出は **volume_ref（実行時較正）** で min_volume を底上げしうる（隠れ状態） | `imbalance.py:179-184`（`effective_min_volume = max(volume_ref.current(), min_volume)`） |
| ANALYSIS payload（壁の差込先） | `push_broker.py:230-273`（envelope("ANALYSIS", ...)） |
| ANALYSIS 配線 | `webapp/main.py:115-123`（on_analysis_cb → broker.on_analysis） |

**移植の2大罠（必ず遵守）**
- ★罠1: payload の `bid`=sell / `ask`=buy。クライアント移植で `buy = N(l.ask)` / `sell = N(l.bid)` とすること。逆にすると BUY/SELL の壁が入れ替わる。
- ★罠2: サーバ検出は `effective_min_volume`（volume_ref で底上げ後）を使う。クライアントは volume_ref を受け取れない。**素朴に config の min_volume で再計算するとサーバと壁が食い違う。** → 本書は §5 でサーバから `effective_min_volume` を payload に載せ、クライアントの既定 min_volume に使う。これで既定歯車値ではサーバの壁と一致する。

---

## 4. サーバ変更

### 手順1 ── Imbalance を composite から抜く（`src/pipeline.py`）

**before**（`pipeline.py:541`）:
```python
    s_imb = score_imbalance(imbalance_result, stack_ref)
```
**after:**
```python
    # Imbalance is now an independent native indicator (spec §9 step2-3, same
    # treatment as CVD/Footprint): pull it out of composite by passing None. Its
    # native reading (stacked walls) is sent structured in the ANALYSIS payload
    # and rendered price-axis (案3). score_imbalance is left in place and removed
    # later in the bulk teardown (spec §9 step3).
    s_imb = None
```
- `score_imbalance` 関数・import は**残す**（step3 で撤去）。`imbalance_result` の算出（`pipeline.py:493`）は**残す**（壁配信に使う）。
- 共有関数 `_evaluate_and_store`（`pipeline.py:470`）内のため Replay/Live 両系に1変更で効く。

### 手順2 ── 丸めた IMBALANCE 事件配信を撤去（`src/pipeline.py`）

`pipeline.py:495-518` の **IMBALANCE PushFlowEvent 発火ブロック全体**を削除する。範囲は「`# IMBALANCE flow events ...` コメントから、`on_webapp_flow_event(PushFlowEvent(... category="IMBALANCE" ...))` とその cooldown 更新（`imbalance_fire_state[direction] = ...` の elif 分岐まで）」の一塊。

**before**（該当ブロックの外枠。実物で全体を特定して丸ごと削除）:
```python
    # IMBALANCE flow events (2 directions each fired separately). Strength is
    # net/(stack_ref*2) capped at 1 (Task-A: halved so strong-but-not-extreme
    # stacks no longer saturate at 1.00), gated by a same-direction cooldown.
    if on_webapp_flow_event is not None:
        buy_net = sum(si.count for si in imbalance_result.stacked_imbalances if si.direction == "BUY")
        ...
            elif imbalance_fire_state is not None and bars_since is not None:
                # Age the cooldown only once it has fired at least once.
                imbalance_fire_state[direction] = {"bars_since": bars_since + 1, "last_net": last_net}
```
**after:** （ブロックごと削除。ABSORPTION の PushFlowEvent 発火＝`pipeline.py:980` 付近は**触らない**）

- 削除により未使用化する `_imbalance_should_fire` / `_IMBALANCE_COOLDOWN_BARS` / `imbalance_fire_state` 引数は、**定義・引数はそのまま残す**（dead code 化のみ・削除しない。widening を避ける。最終掃除は step3）。

### 手順3 ── 検出器が使った effective_min_volume を露出（`src/orderflow/imbalance.py`）

`detect()` 内で `effective_min_volume` を確定した直後、`return` の前に1行足して保持する。

**before**（`imbalance.py` detect 冒頭、`effective_min_volume` 確定部）:
```python
        else:
            effective_min_volume = self.min_volume

        levels = bar.levels
```
**after:**
```python
        else:
            effective_min_volume = self.min_volume
        # Expose the floor actually used (may be raised by volume_ref) so the
        # webapp client can recompute walls faithfully (Imbalance独立化: ★罠2).
        self.last_effective_min_volume = effective_min_volume

        levels = bar.levels
```
- `__init__` に `self.last_effective_min_volume = self.min_volume` を初期化として1行追加（detect 未実行時の既定）。`__init__` 末尾（`self.invalid_pairs = 0` の直後）へ。

### 手順4 ── 壁を ANALYSIS payload に載せる（`webapp/push_broker.py` + `webapp/main.py`）

**4-a. `push_broker.on_analysis` に壁を追加**

`on_analysis` シグネチャに `imbalance_result=None, imbalance_detector=None` を追加する。

**before**（`push_broker.py:230`）:
```python
    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result, divergence=None) -> None:
```
**after:**
```python
    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result, divergence=None, imbalance_result=None, imbalance_detector=None) -> None:
```

ANALYSIS envelope（`push_broker.py:244` の `await self._broadcast(envelope("ANALYSIS", ...))` の dict）に、`"divergence": ...` と同階層で `"imbalance"` キーを追加する。

**追加する dict（envelope 内、`"divergence"` エントリの直後にカンマ区切りで挿入）:**
```python
            "imbalance": None if imbalance_result is None else {
                "walls": [
                    {
                        "side": si.direction,
                        "count": si.count,
                        "price_start": d2s(si.start_price),
                        "price_end": d2s(si.end_price),
                    }
                    for si in imbalance_result.stacked_imbalances
                ],
                "ratio_threshold": d2s(imbalance_detector.ratio_threshold) if imbalance_detector is not None else None,
                "stack_count": imbalance_detector.stack_count if imbalance_detector is not None else None,
                "ratio_cap": d2s(imbalance_detector.ratio_cap) if imbalance_detector is not None else None,
                "min_volume": d2s(imbalance_detector.last_effective_min_volume) if imbalance_detector is not None else None,
            },
```
- `d2s` は push_broker 既存の Decimal→str ヘルパー。`float(` は使わない。

**4-b. 検出器を `_BarCloseResult` に載せる（`src/pipeline.py`）★重要**

`imbalance_detector` は pipeline のローカル変数（`pipeline.py:358/879`）で `self` 属性ではない。したがって webapp からは `_BarCloseResult` 経由で受け取る。`_evaluate_and_store` は既に `imbalance_detector` を引数に持つ（`pipeline.py:473`）ので、返り値に載せるだけでよい。

**before**（`_BarCloseResult` dataclass、`pipeline.py:461-467`）:
```python
@dataclass(frozen=True)
class _BarCloseResult:
    """All outputs from a single bar-close evaluation."""
    analysis_result: Optional[Any]
    imbalance_result: ImbalanceResult
    signal_result: SignalResult
    absorption_result: Optional[Any]
    module_scores: dict  # {"cvd": Decimal|None, "footprint": Decimal|None, "imbalance": Decimal|None}
```
**after:** （末尾に1フィールド追加）
```python
@dataclass(frozen=True)
class _BarCloseResult:
    """All outputs from a single bar-close evaluation."""
    analysis_result: Optional[Any]
    imbalance_result: ImbalanceResult
    signal_result: SignalResult
    absorption_result: Optional[Any]
    module_scores: dict  # {"cvd": Decimal|None, "footprint": Decimal|None, "imbalance": Decimal|None}
    imbalance_detector: Any = None  # exposed for webapp wall payload (Imbalance独立化)
```

**before**（`_BarCloseResult(...)` の構築、`pipeline.py:561-566`）:
```python
    return _BarCloseResult(
        analysis_result=analysis_engine.evaluate(analysis_input),
        imbalance_result=imbalance_result,
        signal_result=signal_result,
        absorption_result=absorption_result,
        module_scores={"cvd": s_cvd, "footprint": s_fp, "imbalance": s_imb},
    )
```
**after:**
```python
    return _BarCloseResult(
        analysis_result=analysis_engine.evaluate(analysis_input),
        imbalance_result=imbalance_result,
        signal_result=signal_result,
        absorption_result=absorption_result,
        module_scores={"cvd": s_cvd, "footprint": s_fp, "imbalance": s_imb},
        imbalance_detector=imbalance_detector,
    )
```

**4-c. `main.py` の on_analysis_cb で壁を渡す**

**before**（`webapp/main.py:118-123`）:
```python
            asyncio.create_task(broker.on_analysis(
                analysis_result,
                bc.signal_result,
                bc.module_scores,
                bc.absorption_result,
                getattr(pipeline, "divergence", None),
            ))
```
**after:**
```python
            asyncio.create_task(broker.on_analysis(
                analysis_result,
                bc.signal_result,
                bc.module_scores,
                bc.absorption_result,
                getattr(pipeline, "divergence", None),
                bc.imbalance_result,
                bc.imbalance_detector,
            ))
```

---

## 5. クライアント変更（`webapp/static/index.html`）

### 手順5 ── 旧 IMBALANCE スコア行を撤去（CVD/Footprint 前例に一致）

**before**（`index.html:753`）:
```javascript
    scoreRow("IMBALANCE",sc.imbalance)+
```
**after:** （行ごと削除。ABSORPTION/FLOW/COMPOSITE 行は残す）

### 手順6 ── 案3 IMBALANCE パネルを右カラムに新設

`#right`（`index.html:327`）の先頭、MARKET STATE パネル（`:328`）の**直前**に新パネルを挿入する。配置は暫定（最終レイアウトは仕様 §11 で後決め）。

**before**（`index.html:327-329`）:
```html
    <div id="right">
      <div class="panel">
        <div class="phead"><span class="ptitle">MARKET STATE</span><span class="hint">FROM SIGNALENGINE</span></div>
```
**after:**
```html
    <div id="right">
      <div class="panel" style="position:relative">
        <div class="phead">
          <span class="ptitle">IMBALANCE</span>
          <span style="display:flex;align-items:center;gap:8px">
            <span id="imbratio" class="hint" style="font-size:11px">ratio ≥ 3.0</span>
            <button id="imbgear" title="ratio / stack / min_volume" style="background:none;border:1px solid var(--line);color:var(--sub);border-radius:4px;cursor:pointer;font-size:12px;line-height:1;padding:2px 6px">⚙</button>
          </span>
        </div>
        <div id="imbgearpop" style="display:none;position:absolute;z-index:50;margin:4px 12px;padding:8px 10px;background:var(--panel);border:1px solid var(--line);border-radius:6px;font-size:11px;color:var(--sub)">
          <div style="margin-bottom:6px">倍率 <input id="imbratioin" type="number" min="1" max="20" step="0.5" style="width:60px;background:#0A0D12;color:var(--text);border:1px solid var(--line);border-radius:4px;padding:2px 4px"></div>
          <div style="margin-bottom:6px">段数 <input id="imbstackin" type="number" min="2" max="20" step="1" style="width:60px;background:#0A0D12;color:var(--text);border:1px solid var(--line);border-radius:4px;padding:2px 4px"></div>
          <div>下限 <input id="imbminvin" type="number" min="0" step="0.001" style="width:72px;background:#0A0D12;color:var(--text);border:1px solid var(--line);border-radius:4px;padding:2px 4px"></div>
        </div>
        <div id="imbbody" style="padding:8px 12px"><div class="dash" style="text-align:center">—</div></div>
      </div>
      <div class="panel">
        <div class="phead"><span class="ptitle">MARKET STATE</span><span class="hint">FROM SIGNALENGINE</span></div>
```

### 手順7 ── 状態・壁再計算・描画・歯車（JS）

`index.html` の CVD/Footprint 系ロジック群の近く（例: `renderFootprint` 定義群の後）に、以下を追加する。`$()` `N()` `BUY` `SELL` `SUB`(=`var(--sub)`相当) `DIS` は既存の共有ヘルパー/定数を用いる（`N` は `index.html:377`）。

```javascript
// ---- Imbalance independent indicator: client-side wall detection (案3) ----
// Ports src/orderflow/imbalance.py detect(): diagonal qualify + stacked runs.
// ★罠1: payload bid=sell / ask=buy (main.py:107). ★罠2: minVol defaults to the
// server's effective_min_volume (volume_ref-adjusted) so default gear == server.
const IMB={ratio:3.0,stack:3,minVol:0.002,ratioCap:10,serverWalls:null,custom:false};
function imbQualify(num,den,combined,ratio,ratioCap,minVol){
  if(combined<minVol)return null;
  if(den===0)return num>=minVol?ratioCap:null;
  const r=num/den;
  return r>=ratio?r:null;
}
function computeWalls(levels,ratio,stack,minVol,ratioCap){
  if(!levels||!levels.length)return [];
  const asc=levels.slice().sort((a,b)=>N(a.price)-N(b.price));
  const px=asc.map(l=>N(l.price));
  const buy=asc.map(l=>N(l.ask));   // ★罠1: ask = buy_volume
  const sell=asc.map(l=>N(l.bid));  // ★罠1: bid = sell_volume
  const valid=asc.map((_,i)=>buy[i]>=0&&sell[i]>=0);
  const n=asc.length;
  const buyQ=[],sellQ=[];
  for(let i=0;i<n;i++){
    if(!valid[i])continue;
    if(i>=1&&valid[i-1]&&px[i-1]<px[i]){
      const combined=buy[i]+sell[i]+buy[i-1]+sell[i-1];
      if(imbQualify(buy[i],sell[i-1],combined,ratio,ratioCap,minVol)!==null)buyQ.push([i,px[i]]);
    }
    if(i<n-1&&valid[i+1]){
      const combined=buy[i]+sell[i]+buy[i+1]+sell[i+1];
      if(imbQualify(sell[i],buy[i+1],combined,ratio,ratioCap,minVol)!==null)sellQ.push([i,px[i]]);
    }
  }
  const runs=(q,side,out)=>{
    if(!q.length)return;
    let s=0;
    for(let i=1;i<=q.length;i++){
      if(i===q.length||q[i][0]!==q[i-1][0]+1){
        if(i-s>=stack)out.push({side,count:i-s,ps:q[s][1],pe:q[i-1][1]});
        s=i;
      }
    }
  };
  const out=[];
  runs(buyQ,"BUY",out);runs(sellQ,"SELL",out);
  return out;
}
function currentImbWalls(){
  // Default gear → use server walls (perfect fidelity). Custom gear → recompute
  // from the latest closed bar's footprint levels.
  if(!IMB.custom&&IMB.serverWalls)return IMB.serverWalls;
  const bar=S.bars[S.bars.length-1];
  if(!bar||!bar.footprint||!bar.footprint.levels)return IMB.serverWalls||[];
  return computeWalls(bar.footprint.levels,IMB.ratio,IMB.stack,IMB.minVol,IMB.ratioCap)
    .map(w=>({side:w.side,count:w.count,price_start:String(w.ps),price_end:String(w.pe)}));
}
function renderImbalance(){
  const el=$("imbbody");
  const walls=currentImbWalls();
  if(!walls||!walls.length){el.innerHTML='<div class="dash" style="text-align:center">—</div>';return;}
  const prices=[];
  for(const w of walls){prices.push(N(w.price_start),N(w.price_end));}
  let lo=Math.min(...prices),hi=Math.max(...prices);
  const pad=(hi-lo)*0.15||1;lo-=pad;hi+=pad;
  const H=240,span=hi-lo||1;
  const y=p=>((hi-N(p))/span)*H;
  let bands="";
  for(const w of walls){
    const yt=Math.min(y(w.price_start),y(w.price_end));
    const yb=Math.max(y(w.price_start),y(w.price_end));
    const h=Math.max(6,yb-yt);
    const c=w.side==="BUY"?BUY:SELL;
    bands+=`<div style="position:absolute;top:${yt.toFixed(1)}px;left:70px;right:6px;height:${h.toFixed(1)}px;background:${c}22;border-left:3px solid ${c};display:flex;align-items:center;justify-content:space-between;padding:0 8px;box-sizing:border-box">`
      +`<span style="color:${SUB};font-size:11px">×${w.count}</span>`
      +`<span style="color:${c};font-size:12px">${w.price_start} – ${w.price_end}</span></div>`;
  }
  let ticks="";
  for(let k=0;k<=4;k++){
    const p=hi-(span*k/4),ty=(H*k/4);
    ticks+=`<div style="position:absolute;top:${(ty-7).toFixed(1)}px;left:0;width:64px;text-align:right;color:${DIS};font-size:11px">${Math.round(p).toLocaleString()}</div>`
      +`<div style="position:absolute;top:${ty.toFixed(1)}px;left:70px;right:0;border-top:0.5px solid var(--line);opacity:.4"></div>`;
  }
  el.innerHTML=`<div style="position:relative;height:${H}px">${ticks}${bands}</div>`;
}
(function(){
  const gear=$("imbgear"),pop=$("imbgearpop"),ri=$("imbratioin"),si=$("imbstackin"),mi=$("imbminvin");
  gear.onclick=()=>{pop.style.display=pop.style.display==="none"?"block":"none";};
  const apply=()=>{
    const r=parseFloat(ri.value),s=parseInt(si.value,10),m=parseFloat(mi.value);
    if(r>=1)IMB.ratio=r; if(s>=2)IMB.stack=s; if(m>=0)IMB.minVol=m;
    IMB.custom=true;
    $("imbratio").textContent=`ratio ≥ ${IMB.ratio}`;
    renderImbalance();
  };
  ri.onchange=apply;si.onchange=apply;mi.onchange=apply;
})();
```

### 手順8 ── ANALYSIS 受信で壁を取り込む

ANALYSIS メッセージ処理（`renderAnalysis` 相当。旧 scoreRow を消した関数と同じ）内、`renderCvdDivergence(a.divergence)` 呼び出しの近くに、壁の取り込み＋描画を追加する。

**追加（`renderCvdDivergence(a.divergence);` の直後など、ANALYSIS 処理内）:**
```javascript
  if(a.imbalance){
    IMB.serverWalls=a.imbalance.walls||[];
    if(!IMB.custom){
      if(a.imbalance.ratio_threshold!=null)IMB.ratio=N(a.imbalance.ratio_threshold);
      if(a.imbalance.stack_count!=null)IMB.stack=a.imbalance.stack_count;
      if(a.imbalance.min_volume!=null)IMB.minVol=N(a.imbalance.min_volume);
      if(a.imbalance.ratio_cap!=null)IMB.ratioCap=N(a.imbalance.ratio_cap);
      $("imbratio").textContent=`ratio ≥ ${IMB.ratio}`;
      if($("imbratioin"))$("imbratioin").value=String(IMB.ratio);
      if($("imbstackin"))$("imbstackin").value=String(IMB.stack);
      if($("imbminvin"))$("imbminvin").value=String(IMB.minVol);
    }
  }
  renderImbalance();
```

---

## 6. テスト（仕様 §10 失効方針）

1. `python -m pytest -q`。失敗を1件ずつ判定:
   - 旧 imb-in-composite / 旧 IMBALANCE flow-event(strength) の振る舞いを検証していたテスト → 期待値を新実態へ更新、または撤去対象の検証そのものなら削除。**テストを緑にするため `s_imb` を戻したり flow-event を復活させない。**
   - `score_imbalance` 単体テストは無変更（関数本体を残すため緑）。
2. 新契約ガードを追加: `_evaluate_and_store` の返す `module_scores["imbalance"] is None` を固定（CVD/Footprint の None ガードに倣い、`tests/test_live_pipeline.py` / `tests/webapp/test_push_broker.py` の既存 None ガードと同じ2箇所に追記）。
3. push_broker の ANALYSIS payload に `imbalance` キーが載ることを検証する新テストを1本（walls 構造・None 許容）。
4. 完了時 pytest 全件 green（実数を報告。件数は §10 により増減する）。

---

## 7. 検証・完了条件

1. `python -m pytest -q` 全件 green（実数併記）。
2. `grep -rn "float(" src/pipeline.py src/orderflow/imbalance.py webapp/ ` で新規 float 追加ゼロ（既存例外のみ。JS の `parseFloat`/`parseInt` は可）。
3. HTML 機械検証:
   - `grep -c 'id="imbgear"' webapp/static/index.html` → 1
   - `grep -c 'function computeWalls' webapp/static/index.html` → 1
   - `grep -c 'l.ask' webapp/static/index.html`（★罠1 の buy=ask 実装が入ったこと）→ 1 以上
   - `grep -c 'scoreRow("IMBALANCE"' webapp/static/index.html` → **0**
   - inline `<script>` を抽出し `node --check`（不可環境なら同等の構文検査）で構文エラーゼロ。
4. 一致性チェック（★罠2 の検証・必須）: 既定歯車値（サーバ config 相当・`min_volume`=送信された effective 値）で `computeWalls` の出力が、同一 levels に対するサーバ `ImbalanceDetector.detect()` の `stacked_imbalances` と**一致**することを、同一入力のユニット比較（JS テスト or 手動スクリプト実行ログ）で示す。
5. CHANGELOG（`ArchitectureRepository/00_Master/CHANGELOG.md`）に新エントリ（パッチ番号+1）。CompletionLog.md に実施記録（変更ファイル・テスト増減・逸脱有無・§4-b 手順2で削除したブロック・一致性チェック結果）。

**完了3点セット**: (1) CompletionLog 追記 (2) `DeltaEngine_Imbalance独立化_完了.zip`（全体） (3) チャット報告と ZIP の両方提出。

---

## 8. 触ってはいけないもの

- `src/orderflow/imbalance.py` の検出ロジック本体（`_qualify` / `_find_stacked` / `detect` の判定）。追加するのは `last_effective_min_volume` の保持1行のみ。
- `score_imbalance` 本体（step3 で撤去）。
- ABSORPTION の PushFlowEvent（`pipeline.py:980` 付近）。
- composite / market_state / signal / confluence / veto の本体（step3）。
- CVD・Footprint の独立化済みロジック（傾き・divergence・VA・各歯車）。
- 保存スキーマ（`storage.add_signal` / `signal_to_row`）。
- Absorption / Flow の経路（後続 step）。

---

## 9. 次工程（本書対象外・予告）

Imbalance 着地・web 検証合格の後、**Absorption → Flow** を同型で順に独立化（各々の実物確認後・別指示書）。全5指標独立後に §9 step3（composite 本体の一括撤去）へ入る。**本書で step3 を先取りしない。**
