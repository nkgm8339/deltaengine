# 指示書_CVD第1本目_v1

## Order Flow Analysis Platform / DeltaEngine

> 根拠は `仕様書_5指標独立化_v3.2` §11 のみ。本指示書に無いこと・仕様書 §11 の範囲外は一切やらない。**確認や承認を求めず、全手順を即座に実行せよ。**

---

# 0. 厳守事項

- **範囲外に触るな**: `score_cvd` 関数本体・`composite` 本体・footprint/imbalance/flow/absorption の各 score・YAML永続化・DB新スキーマ・最終レイアウトは**削除も改変もしない**。CVD を composite から外すのは `s_cvd` 代入を `None` にするだけ。
- **Decimal 厳守**: 新規コードで `float()` を呼ばない。傾き計算も Decimal。完了時 `grep -rn "float(" <新規/変更箇所>` が 0 件であること。
- **Replay/Live 両系に同一手当て**: pipeline は `ReplayPipeline`(L205) と `LivePipeline`(L600) の二重化。divergence・傾きの配線は**必ず両クラスに**入れる。片系だけは禁止。
- **完了3点セット**: CompletionLog.md 追記 / 全体ZIP提出 / チャット報告。

---

# 1. スコープ（仕様書 §11.1）

1. 確定 Candle の `cvd` 系列から傾きを native 単位で計算する新経路を立てる（差分・回帰の2方式）。
2. Replay/Live 両系で同一の傾き結果を作る。
3. `_evaluate_and_store` の `s_cvd` 代入のみ `None` にして CVD を composite から外す。
4. Web に CVD 専用表示＋歯車ポップアップ（方式・窓）を新設。旧 SIGNAL — WHY の CVD 行を外す。
5. divergence を「そのバーだけの CVD 事件所見」として native 数値で配信・表示。非発火バーは完全沈黙。

---

# 2. 傾き計算モジュール（新規）

新規ファイル `src/orderflow/cvd_slope.py` を作る。確定 Candle の `cvd`（累積、`Candle.cvd`）系列を窓で受け、native 単位の傾きを返す。

## 2.1 仕様

- **入力**: 確定 Candle が閉じるたびに `cvd`（Decimal）を1つ push。
- **窓**: 直近 `window` 本を保持（`collections.deque(maxlen=window)`）。
- **差分方式**: `(最新cvd − 窓先頭cvd) / (実データ数 − 1)`。1バー当たりの傾き。データ数が1以下なら `None`。
- **回帰方式**: 窓内の (x=0..n-1, y=cvd) に対する最小二乗の傾き `slope = Σ((xᵢ−x̄)(yᵢ−ȳ)) / Σ((xᵢ−x̄)²)`。全て Decimal。分母0（n<2）なら `None`。
- **ウォームアップ**: 実データ数 `n < window` の間は `ready=False` と `n`/`window` を返す（傾き値は途中でも計算して返してよいが、UI 側が n/window 表示に使う）。
- **方式・窓は実行時可変**: `set_method(method)` / `set_window(window)` を持ち、呼ばれたら以後その設定で計算。窓縮小時は deque を作り直す（既存データは保持可能なだけ引き継ぐ）。

## 2.2 決定性

- 同一 cvd 系列＋同一設定 → 同一傾き。wall-clock・乱数を計算経路に入れない（cvd.py と同じ規律）。

## 2.3 テスト（新規 `tests/orderflow/test_cvd_slope.py`）

- 差分方式: 既知系列で `(last-first)/(n-1)` を Decimal 一致で検証。
- 回帰方式: 直線系列で傾きが厳密一致、水平系列で 0。
- ウォームアップ: n<window で ready=False、揃ったら True。
- set_method/set_window 後に計算が切り替わる。
- n<2 で None。

---

# 3. pipeline 配線（両系・仕様書 §11.5）

## 3.1 傾き計算器の生成（両系）

`ReplayPipeline`(L205) と `LivePipeline`(L600) の各 `__init__` で、divergence_detector を生成しているのと同じ箇所（Replay L343 付近 / Live L855 付近）の近傍に、傾き計算器を生成する。初期値は**回帰・窓20**（仕様書 §11.2）。config から読める形にしておくが、YAML 永続化は本指示書では追加しない（起動時デフォルト20・regression でよい）。

## 3.2 確定 Candle で傾きを push（両系）

両系の `if cvd_result.closed_candle is not None:` ブロック（Replay L394 / Live L990）で、`closed_candle.cvd` を傾き計算器へ push し、結果（傾き値・ready・n・window・method）を後段の push に渡せるよう保持する。

## 3.3 divergence を「そのバーだけ」に（両系・既存バグ修正）

**現状（Replay L395-397 / Live L991-993、両系同一）**:

```python
                detected_divergence = divergence_detector.update(cvd_result.closed_candle)
                if detected_divergence is not None:
                    self.divergence = detected_divergence
```

`self.divergence` は発火時のみ代入され、非発火バーで消えない。最初の発火後、同じ divergence が後続バーに残り続ける。

**修正（両系とも）**: そのバーで検出された値のみを保持し、非発火バーでは None に戻す。

```python
                detected_divergence = divergence_detector.update(cvd_result.closed_candle)
                self.divergence = detected_divergence  # 非発火バーは None → 沈黙
```

これで非発火バーは沈黙する（仕様書 §3.2 / §11.5）。

## 3.4 CVD を composite から外す（`_evaluate_and_store` L469、共有＝1箇所）

**現状（L530）**:

```python
    s_cvd = score_cvd(candle.delta, cvd_slope_ref)
```

**変更**:

```python
    s_cvd = None  # CVD独立化: composite から外す（score_cvd 関数は残置・撤去は後段）
```

`score_cvd` 関数定義・`composite` 本体・他4指標の score 代入（`s_fp` / `s_imb` / flow）は**触らない**。`evaluate` は `s_cvd=None` を受けて cvd を entries に入れない（既存 None 除外設計、signal.py L183-190）。composite は footprint/imbalance/flow で縮小生存する。

---

# 4. 配信 payload（両系フック・仕様書 §11.4/§11.5）

## 4.1 CVD 傾き payload

CVD 専用の配信を追加する。既存の push フック機構（`on_candle` / `on_analysis`）に相乗りしてよい。載せる値（全て Decimal→str、`float()` 禁止）:

- `slope`（傾き native 値、ready 前でも計算値を出してよい）
- `method`（"regression" | "difference"）
- `window`（int）
- `n`（現在の実データ数）
- `ready`（bool: n>=window）

## 4.2 divergence native payload

**現状（push_broker L261）は direction だけ配信し native を捨てている**:

```python
            "divergence": divergence.direction.value if divergence is not None else None,
```

**変更**: `DivergenceEvent` の native フィールドを載せる。非発火（None）時は `null`。

```python
            "divergence": None if divergence is None else {
                "direction": divergence.direction.value,
                "kind": divergence.kind.value,
                "pivot_price": d2s(divergence.pivot_price),
                "previous_pivot_price": d2s(divergence.previous_pivot_price),
                "pivot_cvd": d2s(divergence.pivot_cvd),
                "previous_pivot_cvd": d2s(divergence.previous_pivot_cvd),
                "price_change": d2s(divergence.price_change),
                "cvd_change": d2s(divergence.cvd_change),
                "bars_between": divergence.bars_between,
            },
```

（`DivergenceEvent` の実フィールドは divergence.py L31-45: direction/kind/detected_time/pivot_time/previous_pivot_time/pivot_price/previous_pivot_price/pivot_cvd/previous_pivot_cvd/price_change/cvd_change/bars_between。`kind` の enum 値名は実物に合わせる。）

---

# 5. Web（`webapp/static/index.html`・仕様書 §11.1/§11.4）

## 5.1 旧 CVD 行を外す

SIGNAL — WHY 内の CVD 行（L654-665: `cvd_unref` 分岐と `scoreRow("CVD",sc.cvd)`）を除去。footprint/imbalance の score 行は残す（それらは後段で独立化）。

## 5.2 CVD 専用表示（最下段 CVD 領域を暫定利用）

最下段の CVD+Δ チャート領域のヘッダ付近に、CVD 傾きの native 数値表示を新設:

- 傾き値（native、丸めない。符号付き）
- 現在の method / window
- ウォームアップ中は `n/window`（例 `12/20`）を表示し、傾き値は薄い扱い（ready=false）
- divergence: **発火時のみ** direction と native 数値（price_change / cvd_change / bars_between 等）を表示。payload が null のバーは**何も出さない（沈黙）**。飾りで残さない。

## 5.3 歯車ポップアップ（方式・窓のみ）

CVD 表示ヘッダ横に歯車アイコン。クリックでその場にポップアップ:

- **方式**: regression / difference のトグル
- **窓**: 数値入力（例 5〜200）
- 変更で即時反映（§5.4）。**divergence 閾値は含めない**（仕様書 §11.4）。

## 5.4 即時反映の実行時 API（新設）

現行 `/api/config` は GET 専用。CVD 傾き設定用の実行時 POST を新設する（CVD 専用・最小）:

- `POST /api/cvd/slope-config` body `{"method": "...", "window": N}`
- 受けたら pipeline の傾き計算器の `set_method` / `set_window` を両系の稼働インスタンスに適用（稼働中インスタンスへの参照を app.state 経由で解決）。
- 単一 asyncio ループ内での差し替え。window 変更は deque 再構築（§2.1）。ADR-003 の起動時読み込みは変更しない（本 API は稼働中の CVD 傾き設定のみを差し替える最小契約）。
- レスポンスは適用後の `{method, window}` を返す。

**注意**: 本 API は CVD 傾きの方式・窓のみ。他指標・他パラメータには触れない。

---

# 6. テスト（仕様書 §10・新契約）

- `tests/orderflow/test_cvd_slope.py`（§2.3）
- pipeline: 確定 Candle push で傾きが両系（Replay/Live）に出ることの回帰テスト。
- divergence 沈黙: 非発火バーで `self.divergence is None` になることを両系で検証（既存の発火保持を期待していたテストがあれば新仕様へ更新）。
- payload: divergence native フィールドが載る / None バーで null になる。
- `s_cvd=None` で composite が footprint/imbalance/flow のみで計算されること（cvd が entries に入らない）。
- 既存テストのうち「CVD が composite に入る」「divergence が発火後も保持される」を前提にしたものは新仕様へ更新（撤去対象の延命はしない）。

---

# 7. 完了条件（仕様書 §11.6）

- Replay/Live 両系で傾きが native 数値で出る（回帰20本初期、n/20 ウォームアップ）。
- 歯車で方式・窓が即時反映される（POST /api/cvd/slope-config）。
- divergence が発火バーのみ表示・非発火沈黙（両系）。
- CVD が composite から外れている（s_cvd=None）。他4指標・composite 本体は無傷で並走。
- 新契約テスト green。`grep -rn "float(" <新規/変更箇所>` 0件。
- 変更なしファイルの AST 不変を確認（範囲外無改変の証明）。

---

# 8. 完了報告（3点セット）

1. `CompletionLog.md` に追記（新規テスト件数・変更ファイル一覧・逸脱有無・両系手当ての確認・float スキャン結果）。
2. `DeltaEngine_CVD第1本目_完了.zip` として全体 ZIP を提出。
3. チャット報告とZIPの両方を提出。

**確認や承認を求めず、全手順を即座に実行せよ。**
