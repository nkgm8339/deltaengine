# 指示書_5指標独立化_Flow_v1

## Order Flow Analysis Platform / DeltaEngine — Codex 実装用

> 母体仕様: `仕様書_5指標独立化_v3.1（確定版）`。本書はその §9 step2 の**最後＝Flow 独立化**のみを実装対象とする。CVD/Footprint/Imbalance/Absorption は独立済み。
> 実装体制: Codex。根拠はすべて実物（最新 ZIP・Absorption 反映済み）の file:行。推測で経路を書き換えない。本書に無いことを足さない。

---

## 0. Codex への絶対命令

1. **確認や承認を求めず、本書の全手順を上から順に即座に実行せよ。** 途中で選択肢を提示して止まらない。
2. 本書に明記された変更**以外**を一切行わない。「ついで修正」「整形」「リファクタ」を禁ずる。
3. 行番号は着手時点の実物とズレうる。**アンカー文字列（before ブロック）で位置を特定**すること。
4. `float(` を新規コードに書くな。Decimal→str は `d2s` を使え。
5. 完了後、§7 の完了条件（pytest 緑・`float(` スキャン・HTML 機械検証・3点セット）を満たして報告せよ。

---

## 1. スコープ（Flow 1指標のみ・最後の独立化）

- 本書は **Flow だけ**。これが5指標独立化の最後の1つ。
- **composite / market_state / signal / confluence の本体撤去は行わない**（仕様 §9 step3 は別指示書「指示書_一括撤去_v1」）。本書は Flow を composite から**抜く**（`flow_events` を渡さない）だけ。
- Flow を抜いた後、composite の entries は**空**になる（CVD/FP/IMB は既に None、Flow が最後）。composite は NO_INPUT で WAIT を返す。旧スコアパネルの COMPOSITE 行は「0」相当になるが、**次の一括撤去指示書で消すため補正しない。**
- 現状 Flow は SimpleAverageFlowScorer で5イベントを1スコアに畳んでいる（仕様 §4.7）。独立化後は**5イベントを平均せず個別に ANALYSIS payload に載せる**。
- 事件もの扱い。**発火時（バッファにイベントあり）だけ表示、空なら沈黙。**

---

## 2. 確定仕様（お館様承認済み）

- 仕様 §3.1: Flow の出す数字は **5イベント(large/sweep/exhaustion/unfinished/tape)を平均せず個別に、強さと側**。
- 仕様 §4.7: `SimpleAverageFlowScorer` / `score_flow_events` / `w_flow` は撤去対象。ただし**本書では撤去しない**（step3 で一括撤去）。本書では composite に flow を渡さないことで切り離すだけ。
- **歯車（本書で確定）**: Flow 検出器は5種あり各々パラメータが異なる。Absorption と同様にサーバ POST 方式（クライアント再計算不可。検出器は内部状態 deque を持つ）。ただし**パラメータ数が多いため、本書では歯車は実装しない**。Flow パネルの5イベント個別表示のみ。歯車は後続で追加可能な構造にしておく。

---

## 3. 現在地（実物確認済・根拠付き）

| 事実 | 実物根拠 |
|---|---|
| `flow_events=list(flow_event_buffer)` が `_evaluate_and_store` に渡されている | `pipeline.py:1004,1139`（Live の2箇所） |
| Replay では `flow_events` 未渡し（デフォルト None） | `pipeline.py:406-411,436-441`（flow_events 引数なし） |
| `_evaluate_and_store` が `signal_engine.evaluate` に `flow_events` を渡す | `pipeline.py:524` |
| `evaluate` 内で `w_flow > 0` かつ `flow_events is not None` のとき `score_flow_events` 呼び出し | `signal.py:178-179` |
| flow_score が None でなければ entries に追加され composite に合流 | `signal.py:189-190` |
| ANALYSIS payload の `scores["flow"]` は `push_broker.flow_score(now)` | `push_broker.py:234` |
| `flow_score()` は `_flow_history` の加重平均（PushFlowEvent 受信で蓄積） | `push_broker.py:133-148` |
| 旧 `scoreRow("FLOW", sc.flow, {zeroToOne:true})` が右パネルに残存 | `index.html:906` |
| confluence names に `"flow"` が残存 | `index.html:872` |
| FLOW WS メッセージは `PushFlowEvent` → `broker.on_flow_event` で配信 | `push_broker.py:294-300` |
| 既存 FLOW EVENTS パネル（`#flowpanel`）が中央下部に存在 | `index.html:322-328` |
| `onFlow` ハンドラが `S.flows` に追加し `renderFlow()` を呼ぶ | `index.html:510-518` |
| 5検出器は Live 専用（`pipeline.py:883-897`）。FlowEvent は `kind/side/strength/price/detail` を持つ | `flow_detector.py:17-23` |
| `_BarCloseResult` に flow_events フィールドはない | `pipeline.py:460-468` |
| ABSORPTION の PushFlowEvent 配信（`pipeline.py:955-967`）は**残す** | Absorption 独立化済みだが FLOW EVENTS パネルへの表示は継続 |

**結論**: Flow に足りないのは (A) ANALYSIS payload に5イベント個別データを載せる、(B) composite から切り離す（`flow_events` を渡さない）、(C) 旧スコアパネルから FLOW 行を削除、(D) confluence names から "flow" を除去。

---

## 4. サーバ変更

### 手順1 — Flow を composite から抜く（`src/pipeline.py`）

`_evaluate_and_store` 内で `flow_events` を `evaluate` に渡さないようにする。

**アンカー（before）** — `pipeline.py:521-525`:
```python
    signal_result = signal_engine.evaluate(
        s_cvd, s_fp, s_imb,
        absorption_result=absorption_result,
        flow_events=flow_events,
    )
```

**after:**
```python
    # Flow is now an independent native indicator (spec §9 step2, last of 5):
    # pull it out of composite by not passing flow_events. The 5 detectors
    # continue to run and emit FlowEvents via on_flow_event / PushFlowEvent;
    # individual events are sent structured in the ANALYSIS payload.
    # SimpleAverageFlowScorer / score_flow_events / w_flow are left in place
    # and removed later in the bulk teardown (spec §9 step3).
    signal_result = signal_engine.evaluate(
        s_cvd, s_fp, s_imb,
        absorption_result=absorption_result,
        flow_events=None,
    )
```

- `flow_events` 引数自体は残す（`_evaluate_and_store` の署名互換）。呼び出し側（`pipeline.py:1004,1139`）も**そのまま**（渡しても evaluate 内で使わなくなるだけだが、明示的に None にするのが明瞭。ただし呼び出し側の変更は最小にするため `_evaluate_and_store` 内で上書きする方式を取る）。
- 共有関数のため Replay/Live 両系にこの1変更で効く。

### 手順2 — `_BarCloseResult` に flow_events を追加（`src/pipeline.py`）

ANALYSIS payload で個別イベントを送出するため、bar 確定時のバッファ内容を `_BarCloseResult` 経由で webapp に渡す。

**アンカー（before）** — `pipeline.py:460-468`:
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

**after:**
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
    flow_events: Optional[list] = None  # exposed for ANALYSIS payload (Flow独立化)
```

返り値の組み立て（`pipeline.py:539-546`）に `flow_events` を追加:

**アンカー（before）**:
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

**after:**
```python
    return _BarCloseResult(
        analysis_result=analysis_engine.evaluate(analysis_input),
        imbalance_result=imbalance_result,
        signal_result=signal_result,
        absorption_result=absorption_result,
        module_scores={"cvd": s_cvd, "footprint": s_fp, "imbalance": s_imb},
        imbalance_detector=imbalance_detector,
        flow_events=flow_events,
    )
```

### 手順3 — 5イベントを ANALYSIS payload に載せる（`webapp/push_broker.py`）

`on_analysis` シグネチャに `flow_events=None` を追加し、ANALYSIS envelope に `"flow_events"` キーを追加する。

**アンカー（before）** — `push_broker.py:228`:
```python
    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result, divergence=None, imbalance_result=None, imbalance_detector=None) -> None:
```

**after:**
```python
    async def on_analysis(self, analysis_result, signal_result, module_scores, absorption_result, divergence=None, imbalance_result=None, imbalance_detector=None, flow_events=None) -> None:
```

ANALYSIS envelope（`push_broker.py:241-292` の `await self._broadcast(envelope("ANALYSIS", ...))` dict 内）に、`"absorption": ...` ブロックの直後、閉じ `}))` の直前に追加:

```python
            "flow_events": None if not flow_events else [
                {
                    "kind": fe.kind,
                    "side": fe.side,
                    "strength": d2s(fe.strength),
                    "price": d2s(fe.price),
                    "detail": fe.detail if isinstance(fe.detail, dict) else {},
                }
                for fe in flow_events
            ],
```

- `fe` は `FlowEvent` dataclass（`flow_detector.py:17-23`）。
- `detail` は既に dict（各検出器が dict を返す）。型ガードは念のため。

### 手順4 — `webapp/main.py` の `on_analysis_cb` で flow_events を渡す

**アンカー（before）** — `main.py:118-126`:
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
                bc.flow_events,
            ))
```

---

## 5. クライアント変更（`webapp/static/index.html`）

### 手順5 — 旧 FLOW スコア行を撤去 + confluence から "flow" を除去

**アンカー（before）** — `index.html:905-907`:
```javascript
  $("scores").innerHTML=
    scoreRow("FLOW",sc.flow,{zeroToOne:true})+
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
```

**after:**
```javascript
  // All 5 indicators are now independent; only COMPOSITE remains (entries empty
  // → NO_INPUT → 0). The entire score panel is removed in the bulk teardown.
  $("scores").innerHTML=
    `<div id="whydivider"></div>`+scoreRow("COMPOSITE",a.composite,{composite:true});
```

**アンカー（before）** — confluence names（`index.html:872`）:
```javascript
  const cf=a.confluence||{}; const names=["cvd","footprint","imbalance","flow"];
```

**after:**
```javascript
  const cf=a.confluence||{}; const names=["cvd","footprint","imbalance"];
```

星の上限を4→3に連動:
**アンカー（before）**（同付近）:
```javascript
  const cnt=Math.max(0,Math.min(4,cf.count||0));
  $("confstars").innerHTML="★".repeat(cnt)+`<span style="color:${LINE}">${"★".repeat(4-cnt)}</span>`;
```

**after:**
```javascript
  const cnt=Math.max(0,Math.min(3,cf.count||0));
  $("confstars").innerHTML="★".repeat(cnt)+`<span style="color:${LINE}">${"★".repeat(3-cnt)}</span>`;
```

### 手順6 — ANALYSIS 受信で個別 flow_events を FLOW EVENTS パネルに反映

既存の `onFlow` ハンドラ（`index.html:510-518`）は `PushFlowEvent`（FLOW WS メッセージ）を受信して `S.flows` に追加する。これは**そのまま残す**（リアルタイム表示）。

加えて、ANALYSIS 受信時にもバー確定時点の flow_events を `S.flows` に補完表示する。`renderAnalysis()` 内、`renderAbsorption()` 呼び出しの直後に追加:

**アンカー（before）** — `index.html:900-901`:
```javascript
  ABS=a.absorption||null;   // event-only; null = silence
  renderAbsorption();
```

**after:**
```javascript
  ABS=a.absorption||null;   // event-only; null = silence
  renderAbsorption();
  // Flow独立化: bar-close flow_events を FLOW EVENTS パネルに反映。
  // リアルタイム FLOW WS メッセージ（onFlow）と重複しうるが、kind+side+price の
  // 組み合わせが異なるイベントのみ追加する簡易 dedup。
  if(a.flow_events&&a.flow_events.length){
    for(const fe of a.flow_events){
      const dup=S.flows.some(f=>f.category===fe.kind&&f.side===fe.side&&f.strength===fe.strength);
      if(!dup){
        S.flows.unshift({event_time:m.time,category:fe.kind.toUpperCase(),side:fe.side,
          strength:fe.strength,detector:fe.kind,detail:JSON.stringify(fe.detail||{})});
        if(S.flows.length>40)S.flows.pop();
      }
    }
    renderFlow();
  }
```

> 注: `m` は ANALYSIS メッセージの envelope（`renderAnalysis` の呼び出し元 `case "ANALYSIS": S.analysis=p; renderAnalysis(); renderTopSignal();` の `m`）。`renderAnalysis` 内で `m` にアクセスできない場合は、`S.analysis` に `time` が載っている（envelope の `time`）ため `a` 経由で代替する。

**確認が必要**: `renderAnalysis()` の呼び出しスコープで `m`（envelope）にアクセスできるか。`index.html:477` の `case "ANALYSIS"` は `onMsg` 内であり、`renderAnalysis` はそこから直接呼ばれている。`renderAnalysis` 内で `m` を参照していない（独立関数）。したがって **`m` は使えない**。代わりに `S.analysis` の親 envelope 時刻を使う。

修正: `m.time` → `(S.analysis&&S.analysis._time)||new Date().toISOString()` ... ただし payload には `_time` がない。

**より安全な方式**: ANALYSIS の `case` ブロック側で flow_events を処理する。

**最終方式（手順6 修正版）**: `renderAnalysis()` 内ではなく、`case "ANALYSIS"` ブロック内で処理する。

**アンカー（before）** — `index.html:477`:
```javascript
      case "ANALYSIS": S.analysis=p; renderAnalysis(); renderTopSignal(); break;
```

**after:**
```javascript
      case "ANALYSIS":
        S.analysis=p; renderAnalysis(); renderTopSignal();
        // Flow独立化: ANALYSIS payload の flow_events を FLOW EVENTS パネルに反映
        if(p.flow_events&&p.flow_events.length){
          for(const fe of p.flow_events){
            const dup=S.flows.some(f=>f.category===(fe.kind||"").toUpperCase()&&f.side===fe.side&&f.strength===fe.strength);
            if(!dup){
              S.flows.unshift({event_time:m.time,category:(fe.kind||"").toUpperCase(),side:fe.side,
                strength:fe.strength,detector:fe.kind||"",detail:JSON.stringify(fe.detail||{})});
              if(S.flows.length>40)S.flows.pop();
            }
          }
          renderFlow();
        }
        break;
```

**手順6で先の「renderAbsorption() 直後」の追加は行わない。** 上記 case ブロック内の修正のみ。

---

## 6. テスト（仕様 §10 失効方針）

1. `python -m pytest -q`。失敗を1件ずつ判定:
   - flow_score が composite に寄与することを前提としたテスト → 期待値を新実態（flow 除外後の composite=NO_INPUT）へ更新。
   - `score_flow_events` / `SimpleAverageFlowScorer` 単体テストは**無変更**（関数本体を残すため緑）。
   - `test_flow_score_present_in_signal_result`（`tests/test_live_pipeline.py:255`）: `flow_events=None` を渡すようになったため `flow_score` が None になる。**期待値を `is None` に更新**。
2. 新契約ガードを追加:
   - `tests/test_live_pipeline.py`: 既存の `module_scores["imbalance"] is None` の直後に、`signal_result.flow_score is None` を検証する行を追記（flow が composite から外れたことの恒久ガード）。
   - `tests/webapp/test_push_broker.py`: ANALYSIS payload に `flow_events` キーが載ることを検証する新テストを1本（イベントあり時は list of dict、なし時は None）。
3. `_BarCloseResult.flow_events` が渡されることの検証は手順2の既存テスト（`test_evaluate_and_store_excludes_imbalance_score_and_flow_events`）の拡張で行う。
4. 完了時 pytest 全件 green（実数を報告）。

---

## 7. 検証・完了条件

1. `python -m pytest -q` 全件 green（実数併記）。
2. `grep -rn "float(" src/pipeline.py webapp/push_broker.py webapp/main.py` で新規 float 追加ゼロ。
3. HTML 機械検証:
   - `grep -c 'scoreRow("FLOW"' webapp/static/index.html` → **0**（旧行が消えたこと）
   - `grep -c '"flow_events"' webapp/push_broker.py` → 1 以上（payload に載ったこと）
   - `grep -c 'flow_events' webapp/static/index.html` → 1 以上（受信処理が入ったこと）
   - confluence names に `"flow"` が無いこと: `grep 'names=\[' webapp/static/index.html` で確認
4. `CHANGELOG.md`（`ArchitectureRepository/00_Master/CHANGELOG.md`）に新エントリ（パッチ番号+1）。`CompletionLog.md` に実施記録（変更ファイル・テスト増減・逸脱有無）。

**完了3点セット**: (1) CompletionLog 追記 (2) `DeltaEngine_Flow独立化_完了.zip`（全体） (3) チャット報告と ZIP の両方提出。

---

## 8. 触ってはいけないもの

- `src/orderflow/signal.py` の `SimpleAverageFlowScorer` / `score_flow_events` / `w_flow` 本体（step3 で撤去）。
- `src/orderflow/flow_detector.py` の検出器ロジック本体（5種すべて）。
- CVD / Footprint / Imbalance / Absorption の新経路（各 render 関数、各歯車、各 payload ブロック）。
- composite / direction / signal / confidence / market_state 本体（step3 で撤去）。
- storage 保存スキーマ（`signal_to_row` / `add_signal`）。
- 既存の FLOW WS メッセージ配信（`push_broker.on_flow_event` / `PushFlowEvent`）とそのハンドラ（`onFlow`）。
- ABSORPTION の PushFlowEvent 配信（`pipeline.py:955-967`）。
- `push_broker.flow_score()` / `_FlowRecord` / `_flow_history`（step3 で confluence とともに撤去）。

---

## 9. 次工程（本書対象外・予告）

Flow 着地・web 検証合格の後、全5指標が独立完了。**仕様 §9 step3（composite / market_state / signal / confidence / confluence / score 部品 / trend_filter / EmaTrendDetector の一括撤去）** を別指示書「指示書_一括撤去_v1」で実行する。
