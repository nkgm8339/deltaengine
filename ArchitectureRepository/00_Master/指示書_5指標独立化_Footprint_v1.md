# 指示書_5指標独立化_Footprint_v1

## Order Flow Analysis Platform / DeltaEngine ── Codex 実装用

> 母体仕様: `仕様書_5指標独立化_v3.1（確定版）`。本書はその §9 step2 の**1本目＝Footprint 独立化**のみを実装対象とする。実装者は Codex。
> 根拠はすべて実物（ZIP `Delta_Engine_Pro4web/`）の file:行。推測で経路を書き換えない。本書に無いことを足さない。

---

## 0. Codex への絶対命令

1. **確認や承認を求めず、本書の全手順を上から順に即座に実行せよ。** 途中で選択肢を提示して止まらない。
2. 本書に明記された変更**以外**を一切行わない。リファクタ・整形・命名変更・「ついで修正」を禁ずる。
3. 各変更は本書に埋め込んだ before/after のとおりに適用する。行番号は着手時点の実物とズレうるため、**アンカー文字列（before ブロック）で位置を特定**すること。
4. 完了後、§6 の完了条件（pytest 緑・`float(` スキャン・HTML 機械検証・3点セット）を満たして報告せよ。

---

## 1. スコープ（Footprint 1指標のみ）

- 仕様書 §9 step2 は「残り4指標を**1つずつ**移す（Footprint→Imbalance→Absorption→Flow）」と定める。本書は **Footprint だけ**。Imbalance 以降は別指示書（各々の実物確認後）。
- 本書で **composite / market_state / signal / confluence / veto の本体撤去は行わない。** それらは全5指標が独立した後の一括撤去（§9 step3）。本書は Footprint を composite から**抜く**だけ（`s_fp=None`）。
- これにより過渡的に旧スコアパネルの COMPOSITE 等は「痩せた不完全値」になる（仕様書 §9 但し書き）。**これは想定内。異常ではない。**

---

## 2. 現在地（実物確認済・根拠付き）

**CVD は既に独立済み。同じ型を Footprint に横展開する。**

| 事実 | 実物根拠 |
|---|---|
| CVD は composite から抜かれ済み（`s_cvd=None`） | `src/pipeline.py:534` |
| CVD の傾きはクライアント側で native 単位計算 | `webapp/static/index.html:708-729`（`cvdSlope()` 差分/回帰・窓可変） |
| CVD の歯車ポップアップ（方式・窓・即時反映） | `index.html:344-360`（markup）/ `:757-770`（handler IIFE） |
| CVD 独立時、旧スコアパネルから CVD 行を削除した | `index.html:665-668`（`scoreRow` 列は FOOTPRINT 始まり＝CVD 行なし。L665 にコメント） |
| Footprint の native 所見 POC/VA は **既に** webapp で計算 | `webapp/push_broker.py:37-59`（`compute_value_area`、VA%=`0.7` を L48 でハードコード） |
| POC/VA は **既に** CANDLE payload に搭載 | `push_broker.py:206,225`（`poc_price/vah_price/val_price` + `footprint.levels` に `price/bid/ask`） |
| 進行中バーも同形で搭載 | `push_broker.py:305,315`（`on_bar_update`） |
| levels は価格**降順**で配信 | `webapp/main.py:99-113`（`reversed(fp_bar.levels)`。`to_levels()` は昇順契約のため反転） |
| POC/VA は **既に** UI 描画済み（バッジ＋VA陰影） | `index.html:568-585`（`fpRow`）/ `:587-618`（`renderFootprint`） |
| Footprint を composite に畳む部品 `score_footprint` | `src/orderflow/signal.py:296-308`（**本書では消さない**。step3 で撤去） |
| composite への投入点 | `src/pipeline.py:535`（`s_fp = score_footprint(buy_total, sell_total)`） |
| `_evaluate_and_store` は Replay/Live 共有（1箇所で両系に効く） | `src/pipeline.py:469`（仕様書 §5.1: 畳み装置の芯は共有。**Footprint の変更は二重化の罠に該当しない**） |
| module_scores 契約 | `src/pipeline.py:467,561`（`{"cvd","footprint","imbalance"}`） |

**結論**: Footprint に足りないのは (A) 歯車、(B) composite からの切り離し（`s_fp=None`）、(C) 旧スコアパネルからの Footprint 行削除。native 計算器の新規追加は不要（材料は payload にある）。

---

## 3. 採用設計（VA% は歯車でクライアント側再計算）

- VA% をクライアント側で再計算する。CANDLE payload に各帯の `bid/ask` があるため往復不要・即時反映（仕様書 §7）。CVD 傾きをクライアント計算した型（`index.html:708-729`）と同型。
- **サーバ `compute_value_area`（`push_broker.py:37-59`）は無変更。** 既存テスト（`tests/webapp/test_push_broker.py` / `test_bar_update.py`）を緑のまま維持するため。クライアントは自前の VA を描画に使うだけで、サーバ値との突き合わせはしない（自己完結）。
- クライアント再計算はサーバ算法を**逐語移植**する（POC=総出来高最大の帯、そこから上下の大きい隣接を足して `grand×vaPct` に到達するまで拡張）。これで VA%=70 のときサーバと実質一致する。

---

## 4. 変更手順

### 手順1 ── Python: Footprint を composite から抜く（`src/pipeline.py`）

**アンカー（before）** ── `_evaluate_and_store` 内、`s_cvd = None` の直後:

```python
    s_cvd = None
    s_fp = score_footprint(buy_total, sell_total)
    s_imb = score_imbalance(imbalance_result, stack_ref)
```

**after:**

```python
    s_cvd = None
    # Footprint is now an independent native indicator (spec §9 step2, same
    # treatment as CVD): pull it out of composite by passing None. Its native
    # reading (POC / Value Area) is computed webapp-side and rendered in the
    # footprint panel with a gear-adjustable VA%. score_footprint is left in
    # place and removed later in the bulk teardown (spec §9 step3).
    s_fp = None
    s_imb = score_imbalance(imbalance_result, stack_ref)
```

- `buy_total` / `sell_total` の算出行（直上）は**残す**。E9001 警告と `AnalysisInput.fp_buy_total/fp_sell_total` で使用中（`pipeline.py` 同関数内）。
- `score_footprint` の import（`pipeline.py:69`）も**残す**。step3 で撤去。
- 共有関数のため Replay/Live 両系にこの1変更で効く（§2 の `pipeline.py:469` 根拠）。**他に触る箇所なし。**

---

### 手順2 ── index.html: 旧スコアパネルから FOOTPRINT 行を削除（CVD 前例に一致）

**アンカー（before）** ── `index.html:665-668` 付近:

```javascript
  // CVD is independent now; slope + event render in the dedicated CVD strip.
  renderCvdDivergence(a.divergence);
  $("scores").innerHTML=
    scoreRow("FOOTPRINT",sc.footprint)+scoreRow("IMBALANCE",sc.imbalance)+
    scoreRow("ABSORPTION",sc.absorption,{zeroToOne:true})+scoreRow("FLOW",sc.flow,{zeroToOne:true})+
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
```

**after:**

```javascript
  // CVD is independent now; slope + event render in the dedicated CVD strip.
  renderCvdDivergence(a.divergence);
  // Footprint is independent now; POC / Value Area render in the footprint
  // panel with a gear-adjustable VA%. Removed from the composite score panel
  // to mirror the CVD treatment (spec §9 step2).
  $("scores").innerHTML=
    scoreRow("IMBALANCE",sc.imbalance)+
    scoreRow("ABSORPTION",sc.absorption,{zeroToOne:true})+scoreRow("FLOW",sc.flow,{zeroToOne:true})+
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
```

---

### 手順3 ── index.html: Footprint 歯車（VA%）＋クライアント VA 再計算

#### 3-a. フットプリントパネルに `position:relative` を付与（ポップアップの位置基準）

**アンカー（before）** ── `index.html:281` 付近（center 直下の最初の panel）:

```html
    <div id="center">
      <div class="panel" style="flex:1">
        <div class="phead">
          <span class="ptitle" id="fptitle">FOOTPRINT</span>
```

**after:**

```html
    <div id="center">
      <div class="panel" style="flex:1;position:relative">
        <div class="phead">
          <span class="ptitle" id="fptitle">FOOTPRINT</span>
```

#### 3-b. phead の `.ctl` に VA% ラベル＋歯車を追加

**アンカー（before）** ── `index.html:284-289` 付近:

```html
          <span class="ctl">
            <button id="prevbar">◀</button><span class="idx" id="baridx">—/—</span><button id="nextbar">▶</button>
            <span style="width:1px;height:14px;background:var(--line);margin:0 4px"></span>
            <button id="zin">＋</button><button id="zout">－</button>
            <button id="plock" class="lock">🔒</button>
          </span>
        </div>
```

**after:**

```html
          <span class="ctl">
            <span id="fpva" style="font-size:11px;font-weight:800;color:var(--warn);letter-spacing:.03em">VA 70%</span>
            <button id="fpgear" title="Value Area %" style="background:none;border:1px solid var(--line);color:var(--sub);border-radius:4px;cursor:pointer;font-size:12px;line-height:1;padding:2px 6px">⚙</button>
            <button id="prevbar">◀</button><span class="idx" id="baridx">—/—</span><button id="nextbar">▶</button>
            <span style="width:1px;height:14px;background:var(--line);margin:0 4px"></span>
            <button id="zin">＋</button><button id="zout">－</button>
            <button id="plock" class="lock">🔒</button>
          </span>
        </div>
        <div id="fpgearpop" style="display:none;position:absolute;z-index:50;margin:4px 12px;padding:8px 10px;background:var(--panel);border:1px solid var(--line);border-radius:6px;font-size:11px;color:var(--sub)">
          <div>VA% <input id="fpvapct" type="number" min="30" max="95" value="70" style="width:56px;background:#0A0D12;color:var(--text);border:1px solid var(--line);border-radius:4px;padding:2px 4px"></div>
        </div>
```

#### 3-c. FP 状態＋クライアント VA 再計算関数を追加

**アンカー（before）** ── `index.html:587`、`function renderFootprint(){` の直前:

```javascript
function renderFootprint(){
```

**after（renderFootprint の直前に挿入）:**

```javascript
// ---- Footprint independent indicator: client-side native Value Area ----
// Mirrors server compute_value_area (push_broker.py:37-59) so numbers match at
// VA%=70. levels arrive price-descending (main.py:99-113). Prices are returned
// as the level's original string to preserve badge string-equality.
const FP={vaPct:70};
function computeValueArea(levels,vaPct){
  if(!levels||!levels.length)return {poc:null,vah:null,val:null};
  const tot=levels.map(l=>N(l.bid)+N(l.ask));
  let poc=0; for(let i=1;i<tot.length;i++)if(tot[i]>tot[poc])poc=i;
  const grand=tot.reduce((a,b)=>a+b,0);
  const target=grand*(vaPct/100);
  let lo=poc,hi=poc,acc=tot[poc];
  while(acc<target&&(hi>0||lo<tot.length-1)){
    const up=hi>0?tot[hi-1]:-1;
    const dn=lo<tot.length-1?tot[lo+1]:-1;
    if(up>=dn){hi--;acc+=up;}else{lo++;acc+=dn;}
  }
  return {poc:levels[poc].price,vah:levels[hi].price,val:levels[lo].price};
}
function renderFootprint(){
```

#### 3-d. renderFootprint 内で client VA を使う（fpRow は無変更）

**アンカー（before）** ── renderFootprint 冒頭:

```javascript
  const bar=useLive?S.liveBar:S.bars[idx]; const fp=bar.footprint;
  const isLatest=idx===S.bars.length-1;
```

**after:**

```javascript
  const bar=useLive?S.liveBar:S.bars[idx]; const fp=bar.footprint;
  // Recompute POC/VA client-side at the gear-selected VA% and overlay onto a
  // shallow copy so fpRow (which reads poc_price/vah_price/val_price) stays
  // unchanged. Server values remain the fallback shape but are not used here.
  const _va=computeValueArea(fp.levels,FP.vaPct);
  const fpv={...fp,poc_price:_va.poc,vah_price:_va.vah,val_price:_va.val};
  const isLatest=idx===S.bars.length-1;
```

**アンカー（before）** ── 同関数内、POC 中央寄せ:

```javascript
    let center=lv.findIndex(l=>l.price===fp.poc_price);
```

**after:**

```javascript
    let center=lv.findIndex(l=>l.price===fpv.poc_price);
```

**アンカー（before）** ── 同関数内、行生成:

```javascript
  const rows=lv.slice(start,end).map(l=>fpRow(l,fp,max)).join("");
```

**after:**

```javascript
  const rows=lv.slice(start,end).map(l=>fpRow(l,fpv,max)).join("");
```

> 注: `fpRow`（`index.html:568-585`）は**一切変更しない**。`fpv` を渡すことで挙動が切り替わる。

#### 3-e. 歯車ハンドラ（即時反映）

**アンカー（before）** ── `index.html:804` 付近、`// footprint controls` ブロックの直前か直後（既存の footprint コントロール群に隣接させる）。既存アンカー:

```javascript
// footprint controls
```

**after（`// footprint controls` の直後に挿入）:**

```javascript
// footprint controls
// --- Footprint VA% gear (immediate, no reload; spec §7) ---
(function(){
  const gear=$("fpgear"),pop=$("fpgearpop"),input=$("fpvapct"),label=$("fpva");
  gear.onclick=()=>{pop.style.display=pop.style.display==="none"?"block":"none";};
  input.onchange=()=>{
    const v=parseInt(input.value,10);
    if(v>=30&&v<=95){FP.vaPct=v;label.textContent=`VA ${v}%`;renderFootprint();}
    else{input.value=String(FP.vaPct);}
  };
})();
```

---

### 手順4 ── テスト（仕様書 §10 準拠）

#### 4-a. Footprint None ガードを追加（CVD 前例のミラー）

CVD には `module_scores["cvd"] is None` を検証する前例がある。同じ2箇所に Footprint 版を**追記**する。

- **`tests/test_live_pipeline.py:103`** ── 既存:
  ```python
      assert pipeline._last_bar_close.module_scores["cvd"] is None
  ```
  直後に追記:
  ```python
      assert pipeline._last_bar_close.module_scores["footprint"] is None
  ```

- **`tests/webapp/test_push_broker.py:310`** ── 既存:
  ```python
      assert result.module_scores["cvd"] is None
  ```
  直後に追記:
  ```python
      assert result.module_scores["footprint"] is None
  ```

#### 4-b. 失効テストの扱い（延命禁止）

- `s_fp=None` により、**composite / signal に Footprint の寄与を前提していたテスト**が失敗しうる。
- 仕様書 §10 の方針に従う: 「テストを緑にするために撤去対象を延命しない」。
  - 失敗原因が「Footprint が composite から抜けたことによる期待値変化」なら、**新しい実態（Footprint 除外後の composite/signal）に期待値を更新**する。
  - そのテストの目的自体が「Footprint の composite 寄与の検証」だったなら、step3 の撤去を先取りせず、**本書時点では当該アサーションのみ Footprint 除外に合わせて修正**（テストファイルの削除は step3 まで行わない）。
- **`score_footprint` 単体テスト（`tests/orderflow/test_signal_normalization.py`）は無変更。** 関数本体は残すため緑のまま。
- **`compute_value_area` 系テスト（`tests/webapp/test_push_broker.py` / `test_bar_update.py`）は無変更。** サーバ算法据え置きのため緑のまま。

---

## 5. 検証手順（Codex が実行して結果を報告）

1. **pytest 緑**: `python -m pytest -q`。全件パス。件数は実測を報告（仕様書 §10 によりテスト群は増減する。固定目標値と照合しない）。
2. **Decimal 禁則スキャン**: `grep -rn "float(" src/pipeline.py webapp/static/index.html` ── 本書の変更行に `float(` を新規混入させていないこと（JS の `parseInt` は可、`float()` Python 呼び出し 0 件）。
3. **HTML 機械検証**（変更が入ったことを grep で確認）:
   - `grep -n "id=\"fpgear\"" webapp/static/index.html` → 1 件
   - `grep -n "computeValueArea" webapp/static/index.html` → 定義1 + 使用1 = 2 件以上
   - `grep -n "FP={vaPct" webapp/static/index.html` → 1 件
   - `grep -n "scoreRow(\"FOOTPRINT\"" webapp/static/index.html` → **0 件**（旧行が消えたこと）
4. **目視（可能なら）**: `docker-compose up --build` → `http://localhost:8080`。フットプリントパネル右上に `VA 70%` と ⚙。歯車を開き VA% を変えると POC/VAH/VAL 帯が即時に変化。旧スコアパネルの FOOTPRINT 行が消えている。headless で不可なら §5-3 の grep 合格を以て代替とし、その旨を報告。

---

## 6. 完了条件（3点セット）

1. `CompletionLog.md` に完了報告を追記（実施日時・指示書名・変更ファイル一覧・pytest 件数・逸脱有無・§4-b で更新/修正したテスト名）。
2. `CHANGELOG.md` に新エントリを追記（バージョン規律。Footprint 独立化。UI バージョン表示が自動追従）。
3. 変更全体を ZIP（`DeltaEngine_Footprint独立化_完了.zip`）で提出し、チャットにも同内容を報告。

---

## 7. 触ってはいけないもの（明示）

- `src/orderflow/signal.py` の `score_footprint` 本体（step3 で撤去）。
- `webapp/push_broker.py` の `compute_value_area` とサーバ payload 形状。
- CVD の傾き・divergence・歯車（`index.html` の CVD 系）。
- divergence / trend の Replay/Live 二重化配線（Footprint とは無関係。§2 の `pipeline.py:469` 共有ゆえ本件は二重化に該当しない）。
- composite / market_state / signal / confluence / veto の**本体**（step3 の一括撤去まで温存）。
- 保存スキーマ（`storage.add_signal` / `signal_to_row`）。旧 signal 列の去就は step3 で判断（仕様書 §10）。
- 他指標（Imbalance / Absorption / Flow）の経路。

---

## 8. 次工程（本書対象外・予告のみ）

仕様書 §9 step2 の順序に従い、Footprint 着地後に **Imbalance → Absorption → Flow** を各々別指示書で同型実装する（各々の実物確認後）。全5指標が独立した時点で初めて §9 step3（composite 本体の一括撤去）に入る。**本書で step3 を先取りしない。**
