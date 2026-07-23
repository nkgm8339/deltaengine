# 指示書_5指標独立化_Absorption_v1

## Order Flow Analysis Platform / DeltaEngine ── Codex 実装用

> 本書は `仕様書_5指標独立化_v3_1.md` の §9 step3（Footprint→Imbalance→**Absorption**→Flow）の3番目、Absorption 1指標の独立化を指示する。CVD/Footprint/Imbalance と同型。本書に無いことは足さない。

---

## 0. Codex への絶対命令

1. 確認や承認を求めず、全手順を即座に完全実行せよ。
2. 本書のパッチは実物の行番号・現行コードを根拠にしている。**貼る前に該当箇所を grep で再確認し、周辺が一致することを検めてから**当てよ。行番号がズレていたら現行コードの一致で位置を特定せよ。
3. 一括変換で他指標（CVD/Footprint/Imbalance）の新経路を壊すな。§8 の禁止事項を厳守。
4. `float(` を新規コードに書くな。Decimal→str は `d2s` を使え。
5. 完了後、§7 の完了条件（pytest 緑・`float(` スキャン・HTML 機械検証・3点セット）を満たして報告せよ。

---

## 1. スコープ（Absorption 1指標のみ）

- Absorption を「veto という役」から**完全に外す**。何かを打ち消す役には二度と就けない。
- Absorption の native 所見（classification / strength / **発生価格帯**）を、丸めずに数字のまま独立所見として ANALYSIS payload に載せ、専用パネルに表示する。
- 事件もの扱い。**発火時（`absorption_result` が非 None）だけ表示、非発火は沈黙**。飾りで点灯させない。
- 歯車ポップアップで `price_stall_ticks` / `volume_multiplier` をその場調整（即時反映）。

**本書対象外**: composite / direction / signal 本体の撤去（= 仕様 §9 step3 の最終一括撤去）は Flow 独立化後。**本書で先取りしない。** ただし **absorption veto だけは本書で撤去する**（仕様 §4.6「veto は残さない」。veto は Absorption 固有の装置なので Absorption 独立化に含める）。

---

## 2. 確定仕様（お館様承認済み）

- 仕様 §3.1: Absorption の出す数字は **classification（BUY吸収/SELL吸収）と strength と発生価格**。
- 仕様 §4.6: absorption veto を撤去。residual として残さない。
- **発生価格の取り方（本書で確定）**: `_evaluate()` が集計する `distinct_prices`（stall した価格集合、`len ≤ price_stall_ticks`）の **min / max** を `price_low` / `price_high` として持たせる。丸めて1点にしない。集合が1要素なら low==high。追加計算ゼロ（既存の集合から取れる）。
- **歯車の即時反映方式（本書で確定）**: Absorption は order book snapshot 依存（`_evaluate` が `current_snap.bid_quantity_at` / `ask_quantity_at` と `_window_start_snapshot` を使用）。クライアントに book 履歴が無く、Footprint/Imbalance のようなクライアント再計算は**不可**。よって歯車値を **POST でサーバに送り、稼働中の `AbsorptionDetector` のパラメータを即時更新**する。`price_stall_ticks` / `volume_multiplier` は判定閾値のみで窓バッファの作り直し不要（`__init__` は属性代入のみ、`_window` は別管理）ゆえ即反映可能。

---

## 3. 現在地（実物確認済・根拠付き）

すべて `Delta_Engine_Pro4web/` 配下。

| 事項 | 実物箇所 | 現状 |
|---|---|---|
| AbsorptionResult | `src/orderflow/absorption.py` L50-51 | `classification: str` と `strength: Decimal` のみ。**発生価格フィールド無し** |
| 集計する価格集合 | `src/orderflow/absorption.py` L123, L131 | `_evaluate` が `distinct_prices: set[Decimal]` を作る。stall 条件で `len ≤ _price_stall_ticks` |
| 判定 return | `src/orderflow/absorption.py` L173-179 | BUY/SELL 分岐で `AbsorptionResult(classification=..., strength=...)` を返す |
| 歯車対象の属性 | `src/orderflow/absorption.py` L71-72 | `self._price_stall_ticks` / `self._volume_multiplier`（kw引数 `price_stall_ticks`/`volume_multiplier`） |
| veto 本体 | `src/orderflow/signal.py` L236-247 | step5。`against` 判定が `direction`（composite 符号）依存、`strength ≥ absorption_veto_threshold` で veto=True → L255 で signal を WAIT 強制 |
| evaluate 署名 | `src/orderflow/signal.py` L171-173 | `absorption_result` を受ける（veto 専用） |
| detector 露出 | `webapp/main.py` L171, L325 | `getattr(pipeline, "absorption_detector", None)` で既に参照可能 |
| on_analysis payload | `webapp/push_broker.py` L230, L236 | `scores["absorption"] = absorption_result.strength`（strength だけ・旧表示） |
| imbalance payload の型 | `webapp/push_broker.py` L274-287 | None 許容 rich object。**Absorption はこの型に倣う** |
| on_analysis 呼び出し | `webapp/main.py` L118-125 | `bc.absorption_result` を broker に渡している |
| 旧 ABSORPTION スコア行 | `webapp/static/index.html` L872 | `scoreRow("ABSORPTION",sc.absorption,{zeroToOne:true})`（旧表示・撤去対象） |
| confluence 名 | `webapp/static/index.html` L840 | `names=["cvd","footprint","imbalance","absorption","flow"]`（absorption 撤去対象） |
| render 型見本 | `webapp/static/index.html` L766-796 | `renderImbalance()`（renderAbsorption の型見本） |
| IMBALANCE パネル型見本 | `webapp/static/index.html` L332-347 | panel + phead + 歯車 + gearpop + body |

---

## 4. サーバ変更

### 手順1 ── AbsorptionResult に発生価格帯を追加（`src/orderflow/absorption.py`）

docstring（L42-48 付近）の項目説明に price_low/price_high を追記し、dataclass 本体（L50-51）にフィールドを2本追加する。

現行:
```python
@dataclass(frozen=True)
class AbsorptionResult:
    ...
    classification: str
    strength: Decimal
```
に変更:
```python
@dataclass(frozen=True)
class AbsorptionResult:
    ...
    classification: str
    strength: Decimal
    price_low: Decimal
    price_high: Decimal
```

`_evaluate` の Step6（L172-179）で `distinct_prices` から min/max を取り、両 return に渡す:
```python
        # Step 6: Judgment — BUY_ABSORPTION priority on double-direction tie (decision 5).
        p_low = min(distinct_prices)
        p_high = max(distinct_prices)
        if buy_replenished and sell_replenished:
            self.double_direction_events += 1
            sell_replenished = False

        if buy_replenished:
            strength = min(agg_sell / threshold, _ONE)
            self.events_detected += 1
            return AbsorptionResult(
                classification="BUY_ABSORPTION", strength=strength,
                price_low=p_low, price_high=p_high,
            )
        else:
            strength = min(agg_buy / threshold, _ONE)
            self.events_detected += 1
            return AbsorptionResult(
                classification="SELL_ABSORPTION", strength=strength,
                price_low=p_low, price_high=p_high,
            )
```
`distinct_prices` は Step3 到達時点で必ず1要素以上（空なら window が空 → 手前で return 済み）。min/max は安全。

**波及**: `AbsorptionResult(...)` を位置引数で組んでいる既存テストがあれば、price_low/price_high 追加でシグネチャが変わる。frozen dataclass に必須フィールドを足すため、テスト側のコンストラクタ呼び出しを新シグネチャに更新する（§6）。

### 手順2 ── absorption veto を撤去（`src/orderflow/signal.py`）

step5 veto ブロック（L236-247）を**丸ごと削除**し、`veto` を参照する箇所を安全化する。

削除対象（L236-247、"step 5: absorption veto" ブロック全体）:
```python
        # --- step 5: absorption veto (decision 8, priority 2) ----------------
        veto = False
        if absorption_result is not None:
            cls_ = absorption_result.classification
            strength = _to_decimal(absorption_result.strength)
            against = (
                (direction == 1 and cls_ == _SELL_ABSORPTION)
                or (direction == -1 and cls_ == _BUY_ABSORPTION)
            )
            if against and strength >= self.absorption_veto_threshold:
                veto = True
                reasons.append(REASON_ABSORPTION_VETO)
```

step7 の最終 signal 決定（L254-260 付近）は `veto` を参照している。`veto` を消したので条件から外す:
```python
        # --- step 7: final signal ---
        if low_conf or direction == 0:
            signal = "WAIT"
        elif direction == 1:
            signal = "BUY"
        else:
            signal = "SELL"
```
（`veto or` を除去。low_conf / direction はそのまま。composite/direction 本体は §9 step3 まで残す方針ゆえ触らない。）

`evaluate` は引き続き `absorption_result` を受けてよいが、veto で使わなくなる。**引数は残す**（呼び出し側の署名互換のため。用途消滅の明示コメントを1行付す）:
```python
        absorption_result: Optional[AbsorptionResult] = None,  # spec §4.6: veto removed; kept for signature compat, unused
```

`REASON_ABSORPTION_VETO` / `_SELL_ABSORPTION` / `_BUY_ABSORPTION` / `self.absorption_veto_threshold` が veto 削除後に他所で未使用なら import/定義/代入を残置でよい（撤去は §9 step3 の掃除に回す。**本書で composite 本体に踏み込まない**）。ただし未使用 lint で赤が出る場合のみ、その1箇所を無害化せよ。

### 手順3 ── absorption を ANALYSIS payload に rich object で載せる（`webapp/push_broker.py`）

`on_analysis`（L230-）内。imbalance payload（L274-287）の直後に absorption ブロックを追加する。`absorption_result` は既に引数で渡っている（L230 署名）。

`"imbalance": None if imbalance_result is None else { ... },` の**直後**に追加:
```python
            "absorption": None if absorption_result is None else {
                "classification": absorption_result.classification,
                "strength": d2s(absorption_result.strength),
                "price_low": d2s(absorption_result.price_low),
                "price_high": d2s(absorption_result.price_high),
            },
```

### 手順4 ── 旧 absorption スコア／confluence 参加を撤去（`webapp/push_broker.py`）

新表示（手順3）を立てた後に旧表示を落とす（仕様 §9「新表示を立ててから旧を消す」）。

(4-a) `scores` dict（L232-238）から `"absorption"` 行を削除:
```python
        scores: dict[str, Optional[Decimal]] = {
            "cvd": module_scores.get("cvd"),
            "footprint": module_scores.get("footprint"),
            "imbalance": module_scores.get("imbalance"),
            "flow": self.flow_score(now),
        }
```

(4-b) `confluence()`（L150-190 付近）の absorption フラグ（L185-186）を削除。フラグ辞書の初期化（L175 の `flags = {k: False for k in (...)}`）からも `"absorption"` を除く。confluence の names 集合は cvd/footprint/imbalance/flow の4つになる。
※ confluence 本体は composite 依存で §9 step3 の一括撤去対象だが、**本書では absorption をそこから抜くだけ**（他指標のフラグは触らない）。

### 手順5 ── 歯車パラメータの即時更新（`src/orderflow/absorption.py` + `webapp/main.py`）

(5-a) `AbsorptionDetector` に setter を追加（`__init__` 直後あたり）:
```python
    def set_params(self, *, price_stall_ticks: Optional[int] = None,
                   volume_multiplier: Optional[Decimal] = None) -> None:
        """Live-adjust detection thresholds (spec §7 gear). Window buffer untouched."""
        if price_stall_ticks is not None:
            self._price_stall_ticks = int(price_stall_ticks)
        if volume_multiplier is not None:
            self._volume_multiplier = Decimal(str(volume_multiplier))
```
`_window` / `_window_start_snapshot` / カウンタには触れない（閾値のみ変更。作り直し不要）。

(5-b) `webapp/main.py` に POST エンドポイントを追加（既存 `getattr(pipeline, "absorption_detector", None)` の露出を利用）:
```python
@app.post("/api/absorption/params")
async def set_absorption_params(payload: dict):
    ab = getattr(pipeline, "absorption_detector", None)
    if ab is None:
        return {"ok": False, "reason": "detector_unavailable"}
    pst = payload.get("price_stall_ticks")
    vm = payload.get("volume_multiplier")
    ab.set_params(
        price_stall_ticks=int(pst) if pst is not None else None,
        volume_multiplier=Decimal(str(vm)) if vm is not None else None,
    )
    return {
        "ok": True,
        "price_stall_ticks": ab._price_stall_ticks,
        "volume_multiplier": d2s(ab._volume_multiplier),
    }
```
`pipeline` / `app` / `Decimal` / `d2s` が main.py スコープにある前提（実物で import を確認し、無ければ足せ）。`pipeline.absorption_detector` 属性が実在することは L171/L325 の `getattr` 使用で確認済み。

---

## 5. クライアント変更（`webapp/static/index.html`）

### 手順6 ── 旧 ABSORPTION スコア行を撤去（L872）

現行:
```javascript
  $("scores").innerHTML=
    scoreRow("ABSORPTION",sc.absorption,{zeroToOne:true})+scoreRow("FLOW",sc.flow,{zeroToOne:true})+
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
```
に変更（ABSORPTION 行のみ除去。FLOW は Flow 独立化で撤去、本書では残す）:
```javascript
  $("scores").innerHTML=
    scoreRow("FLOW",sc.flow,{zeroToOne:true})+
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
```

confluence names（L840）から `"absorption"` を除去（サーバ側手順4-b と対で、UI 契約を合わせる）:
```javascript
  const cf=a.confluence||{}; const names=["cvd","footprint","imbalance","flow"];
```
星の上限は5→4に連動（`Math.min(4,cf.count||0)` / `"★".repeat(4-cnt)`）。※ confluence 表示自体は §9 step3 で撤去予定。本書は absorption を抜くのみ。

### 手順7 ── ABSORPTION パネルを新設（右カラム、IMBALANCE パネルの型に一致）

`#right` 内、IMBALANCE パネル（L332-347）の直後に挿入。歯車は price_stall_ticks / volume_multiplier:
```html
      <div class="panel" style="position:relative">
        <div class="phead">
          <span class="ptitle">ABSORPTION</span>
          <span style="display:flex;align-items:center;gap:8px">
            <span id="abshint" class="hint" style="font-size:11px">—</span>
            <button id="absgear" title="stall ticks / volume ×" style="background:none;border:1px solid var(--line);color:var(--sub);border-radius:4px;cursor:pointer;font-size:12px;line-height:1;padding:2px 6px">⚙</button>
          </span>
        </div>
        <div id="absgearpop" style="display:none;position:absolute;z-index:50;margin:4px 12px;padding:8px 10px;background:var(--panel);border:1px solid var(--line);border-radius:6px;font-size:11px;color:var(--sub)">
          <div style="margin-bottom:6px">停滞ticks <input id="absstallin" type="number" min="1" max="20" step="1" style="width:60px;background:#0A0D12;color:var(--text);border:1px solid var(--line);border-radius:4px;padding:2px 4px"></div>
          <div style="margin-bottom:6px">出来高倍率 <input id="absmultin" type="number" min="1" max="10" step="0.5" style="width:60px;background:#0A0D12;color:var(--text);border:1px solid var(--line);border-radius:4px;padding:2px 4px"></div>
          <button id="absapply" style="background:none;border:1px solid var(--line);color:var(--sub);border-radius:4px;cursor:pointer;padding:2px 8px">反映</button>
        </div>
        <div id="absbody" style="padding:8px 12px"><div class="dash" style="text-align:center">—</div></div>
      </div>
```

### 手順8 ── renderAbsorption + ANALYSIS 受信 + 歯車 POST（JS）

(8-a) 事件もの表示関数。**非発火（null）は沈黙**（`—` を出すのみ、飾りで点灯しない）:
```javascript
// ---- Absorption independent indicator: event-only native reading ----
let ABS=null;
function renderAbsorption(){
  const el=$("absbody"), hint=$("abshint");
  if(!ABS){el.innerHTML='<div class="dash" style="text-align:center">—</div>'; hint.textContent="—"; return;}
  const buy=ABS.classification==="BUY_ABSORPTION";
  const c=buy?BUY:SELL;
  const pct=Math.round(N(ABS.strength)*100);
  hint.textContent=buy?"BUY 吸収":"SELL 吸収";
  hint.style.color=c;
  el.innerHTML=
    `<div style="display:flex;flex-direction:column;gap:6px">`
    +`<div style="font-size:15px;color:${c};font-weight:600">${buy?"BUY ABSORPTION":"SELL ABSORPTION"}</div>`
    +`<div style="display:flex;align-items:center;gap:8px"><span style="color:${SUB};font-size:11px">strength</span>`
    +`<div style="flex:1;height:6px;background:var(--line);border-radius:3px;overflow:hidden"><div style="width:${pct}%;height:100%;background:${c}"></div></div>`
    +`<span style="color:${c};font-size:12px">${pct}%</span></div>`
    +`<div style="display:flex;justify-content:space-between;font-size:12px"><span style="color:${SUB}">price</span>`
    +`<span style="color:${c}">${ABS.price_low} – ${ABS.price_high}</span></div>`
    +`</div>`;
}
```

(8-b) ANALYSIS 受信箇所（`a.imbalance` を取り込む L854 付近と同じ関数内）に追加:
```javascript
  ABS = a.absorption || null;   // event-only; null = silence
  renderAbsorption();
```

(8-c) 歯車の開閉と反映 POST（renderImbalance 直後の IIFE 群に倣う）:
```javascript
(function(){
  const gear=$("absgear"),pop=$("absgearpop"),st=$("absstallin"),mu=$("absmultin"),ap=$("absapply");
  gear.onclick=()=>{pop.style.display=pop.style.display==="none"?"block":"none";};
  ap.onclick=async()=>{
    const body={};
    const s=parseInt(st.value,10), m=parseFloat(mu.value);
    if(s>=1)body.price_stall_ticks=s;
    if(m>=1)body.volume_multiplier=String(m);
    try{
      const r=await fetch("/api/absorption/params",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
      const j=await r.json();
      if(j&&j.ok){st.value=j.price_stall_ticks; mu.value=j.volume_multiplier;}
    }catch(e){}
    pop.style.display="none";
  };
})();
```
（Imbalance 歯車と違い、Absorption はクライアント再計算せずサーバへ送るだけ。§2 の即時反映方式に一致。）

---

## 6. テスト（仕様 §10 失効方針）

1. **veto テストの失効処理**: `tests/orderflow/test_signal.py` / `tests/orderflow/test_signal_flow.py` / `tests/test_pipeline_absorption.py` の中で **absorption veto の発火（forced WAIT / REASON_ABSORPTION_VETO）を検証していたテストは削除**。テストを緑にするために veto を延命しない。veto 非依存の signal 挙動テストは期待値を「veto されない」新実態へ更新。
2. **AbsorptionResult シグネチャ更新**: `AbsorptionResult(...)` を組む既存テスト（`tests/orderflow/test_absorption.py` 等）を price_low/price_high 込みの新シグネチャへ更新。TV-ABS-01〜05 の期待値に price_low/price_high の検証を1行ずつ足す（`distinct_prices` の min/max と一致すること）。
3. **新規テスト**（新契約）:
   - `absorption.py`: `set_params` が閾値のみ更新し `_window` を触らないこと（1本）。
   - `push_broker`: ANALYSIS payload に `absorption` キーが載ること（発火時 rich object・非発火時 None、2ケース）（1本）。
4. `float(` を新規コードに入れない。

---

## 7. 検証・完了条件

1. `python -m pytest -q` が緑。テスト増減を報告（失効削除・新規追加の内訳）。
2. `grep -rn "float(" src/orderflow/absorption.py webapp/push_broker.py webapp/main.py` が新規コードで0件。
3. HTML 機械検証:
   - `#absbody` / `#absgear` / `#absgearpop` / `#absstallin` / `#absmultin` / `#absapply` 要素が存在。
   - `scoreRow("ABSORPTION"` が index.html から消えている。
   - confluence names に `"absorption"` が無い。
4. 即時反映チェック: `POST /api/absorption/params` に `{"price_stall_ticks":2,"volume_multiplier":"3.0"}` を送り、レスポンスの反映値が一致。稼働中 detector の `_price_stall_ticks==2` / `_volume_multiplier==Decimal("3.0")` を確認。
5. `CHANGELOG.md`（`ArchitectureRepository/00_Master/CHANGELOG.md`）に新エントリ（パッチ番号+1）。`CompletionLog.md` に実施記録（変更ファイル・テスト増減・逸脱有無・手順2で削除した veto ブロック・手順4で外した confluence フラグ・即時反映チェック結果）。
6. **3点セット**: CompletionLog 追記 / `DeltaEngine_<ID>_完了.zip` 提出 / チャット報告。

---

## 8. 触ってはいけないもの

- CVD / Footprint / Imbalance の新経路（`s_cvd`/`s_fp`/`s_imb` の None 化、各 render 関数、各歯車、各 payload ブロック）。
- **composite / direction / signal 本体**（`signal.py` L204 composite、L207-216 direction、L254-260 signal 決定の骨格）。veto 参照を外す最小改変のみ許可。撤去は §9 step3。
- Flow 経路（`SimpleAverageFlowScorer` / `score_flow_events` / `w_flow` / FLOW スコア行）。Flow は次工程。
- storage 保存スキーマ（`signal_to_row` / `add_signal`）・DuckDB DDL・Parquet。
- `market_state` / `risk_level`（§9 step3 の一括撤去対象。本書では触らない）。

---

## 9. 次工程（本書対象外・予告）

Absorption 着地・web 検証合格の後、最後の **Flow** を同型で独立化（`SimpleAverageFlowScorer` 撤去、5イベントを平均せず個別に強さと側で出す。別指示書）。全5指標独立後に仕様 §9 step3（composite / market_state / signal / confidence / confluence 本体の一括撤去）へ入る。**本書で step3 を先取りしない。**
