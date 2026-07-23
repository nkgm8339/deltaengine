この指示書を受領したら、確認や承認を求めずに全手順を即座に実行せよ。

# 指示書_B-2_M9_Absorption実装_v2

**対象**: Order Flow Analysis Platform — M9（Absorption 検出器）+ volume_ref 共有機構 + pipeline 配線
**参照正本**: Absorption_v3.1.md / TestSpecification_v3.2.md §4.4（TV-ABS-01〜05）/ SignalEngine_v3.1.md / MarketDataSchema_v3.2.md
**前提状態**: B-1 完了時点（168 passed）。`src/orderflow/volume_ref.py` は既にファイルとして存在する（後述 §1）。

本 v2 は、B-1 完了 ZIP の実ファイル検証結果を反映した改訂版である。旧 B-2 は破棄せよ。

---

## 0. スコープ

1. `volume_ref.py` の検収とテスト追加（実装は既存を維持）
2. `absorption.py` の stub を実装で置換（`AbsorptionResult` 型シグネチャは不変）
3. `imbalance.py` に `volume_ref` keyword 引数追加（既存呼び出し無影響）
4. `pipeline.py` に depth 経路 + Absorption 配線、`absorption_result=None` 固定接続の置換
5. `ArchitectureRepository/00_Master/CompletionLog.md` 新規作成（B-1 分の後追い追記を含む）

**Repository（docs）正本は無変更**。正本の空白は本指示書 §5 の決定に従う。

---

## 1. volume_ref.py（既存維持 + テスト新設）

`src/orderflow/volume_ref.py` は既にリポジトリに存在し、web が実装内容を検証済みである。**一切変更しない**。以下のテストを `tests/orderflow/test_volume_ref.py` として新規作成する（6 本）:

1. `bars=1` で 1 バー観測後、`current()` = そのバーの平均
2. window 超過時に最古バーが脱落する（`bars=2` で 3 バー観測 → 先頭が除外された平均）
3. 観測前は `current()` が `None`
4. 全空バー（level 0 件）観測時に `current()` = `Decimal(0)`
5. レベル数が異なるバー混在時、level-weighted 平均が正しい（例: bar1 = [10, 20]、bar2 = [30] → (10+20+30)/3 = 20）
6. 決定的リプレイ（同一 observe 列 2 回で `current()` 完全一致）

全て Decimal で検証し、float リテラルを使用しないこと。

---

## 2. absorption.py（stub 置換）

### 2.1 型

既存 `AbsorptionResult(classification: str, strength: Decimal)` は**フィールド名・型・順序とも不変**（SignalEngine と TV-SIG-04 が依存）。docstring の「stub」記述は実装版の説明に書き換えてよい。

追加する型:

```python
@dataclass(frozen=True)
class AbsorptionTrade:
    event_time: datetime
    price: Decimal
    quantity: Decimal
    side: str  # "BUY" | "SELL"
```

`__post_init__` で price/quantity を `_to_decimal` により Decimal 化（cvd.py のパターン踏襲、float 禁止）。

### 2.2 検出器 API

```python
class AbsorptionDetector:
    def __init__(
        self,
        window_sec: int,
        price_stall_ticks: int,
        volume_multiplier: Decimal,
        tick_size: Decimal,
        volume_ref: VolumeRefTracker,
    ) -> None: ...

    def on_depth(self, snapshot: OrderBookSnapshot) -> None:
        """最新の板状態を受け取る。価格レベル別に、現在窓の開始時点数量（baseline）
        と最新数量を保持する。"""

    def on_trade(self, trade: AbsorptionTrade) -> Optional[AbsorptionResult]:
        """1 約定を窓に追加し、期限切れ約定を除去した上で評価する。
        3 条件成立時に AbsorptionResult を返し、窓をリセットする。不成立は None。"""
```

### 2.3 評価ロジック（Absorption_v3.1 §5 逐語準拠）

窓 = 最新 trade の `event_time` から遡って `window_sec` 秒以内の trade 群。

1. **Stall**: 窓内 trade の `(max_price − min_price) / tick_size ≤ price_stall_ticks`
2. **Aggression**: 各 side S ∈ {SELL, BUY} について、価格レベルごとの S 側 aggressive volume 合計が `volume_ref.current() × volume_multiplier` 以上のレベルが存在する
3. **Replenish**: 条件 2 を満たすレベルにおいて、反対側 resting liquidity（S=SELL なら bid、S=BUY なら ask）の最新数量 ≥ 窓開始時点 baseline 数量

3 条件成立時:
- S=SELL → `classification="BUY_ABSORPTION"`
- S=BUY → `classification="SELL_ABSORPTION"`
- `strength = min(aggressive_volume / (volume_ref × volume_multiplier), Decimal(1))`（該当レベルの volume を使用。複数レベル成立時は strength 最大のレベルを採用）
- 返却後、trade 窓と baseline をリセットする（同一状態での連続発火防止）

**`volume_ref.current()` が `None` または `0` の場合は検出を行わず `None` を返す**（cold start 安全化、§5 決定3）。

board baseline が未観測（`on_depth` 未受領）のレベルは Replenish 条件を判定不能として不成立扱い。

---

## 3. imbalance.py（volume_ref 引数追加）

`ImbalanceDetector.__init__` に keyword 引数 `volume_ref: Optional[VolumeRefTracker] = None` を追加する。挙動:

- `detect()` 冒頭で、`self.volume_ref is not None` の場合、その呼び出しにおける実効 min_volume を `volume_ref.current()`（`None` なら `self.min_volume`）とする
- `volume_ref=None`（既存呼び出し全て）では**挙動完全不変**。既存テストは 1 本も変更しない

---

## 4. pipeline.py（配線）

### 4.1 depth 経路

- Replay / Live 両経路で `normalizer.classify_raw(raw)` により trade/depth を振り分ける
- depth は `normalizer.process_depth(raw)` → `OrderBookStateManager.apply(update)` → 適用成功時 `manager.snapshot()` を `absorption_detector.on_depth(...)` へ渡す
- Live の `event_filter` デフォルトを `is_agg_trade` から `is_agg_trade_or_depth` に変更する（既存テストが `is_agg_trade` を明示指定している場合は無影響であることを確認せよ）

### 4.2 trade 経路と評価

- 正規化済み trade を `AbsorptionTrade` に写像して `absorption_detector.on_trade(...)` に渡し、返却された `AbsorptionResult` を「現在バーの最新結果」として保持する
- `_evaluate_and_store` に `absorption_result: Optional[AbsorptionResult]` 引数を追加し、`signal_engine.evaluate(..., absorption_result=<保持値>)` へ渡す。**`absorption_result=None` のリテラル固定接続を残さない**
- バー確定時、`fp_bar.levels` の各レベルの `buy_volume + sell_volume` を共有 `VolumeRefTracker.observe_bar(...)` に投入する。この tracker を ImbalanceDetector（`volume_ref=tracker`）と AbsorptionDetector の両方に注入する
- バー確定後、保持中の AbsorptionResult をクリアする（次バーへ持ち越さない）

### 4.3 config

- `config.yaml` の `market:` に `tick_size: 0.1` を追加、`src/config.py` の market スキーマに `Field(v_number(gt=0), 0.1)` を追加（§5 決定2）
- Pipeline は `absorption.*` と `market.tick_size` を読んで AbsorptionDetector を構築する

---

## 5. 設計判断（正本に明記がないため本指示書で確定）

1. **tick_size**: 正本に定義がないため `market.tick_size` を config に新設（default 0.1 = Binance Futures BTCUSDT）。stall 判定にのみ使用
2. **評価粒度**: Aggression / Replenish は価格レベル単位で判定（TV-ABS が単一価格 100 / 200 で記述されているため）
3. **cold start**: `volume_ref` 未成立（None/0）の間は検出無効。TV-ABS テストでは `VolumeRefTracker(bars=1)` に per-level volume 50 のバーを 1 本観測させてから使用する（→ volume_ref=50、multiplier 2.0 で閾値 100。TV-ABS-01 の 120/100=1.0 と整合）
4. **発火後リセット**: 同一窓での連続発火を防ぐため、イベント返却時に窓と baseline をリセット
5. **エラーハンドリング**: side が BUY/SELL 以外の trade は E3001 で棄却・状態不変（多層防御、CVD 踏襲）

実装上やむを得ず逸脱する場合は完了報告に明記せよ。

---

## 6. テスト

新規 `tests/orderflow/test_absorption.py`（9 本）:

- TV-ABS-01〜05（逐語。§5 決定3 のセットアップを使用）
- cold start（volume_ref 未観測時は如何なる入力でも None）
- 発火後リセット（同一入力継続で二重発火しない）
- 不正 side 棄却（状態不変）
- 決定的リプレイ（同一入力列 2 回で出力列完全一致）

新規 `tests/orderflow/test_volume_ref.py`（§1 の 6 本）

pipeline 配線テスト（2 本、`tests/test_pipeline.py` 追記または新規）:

- depth fixture + trade fixture のリプレイで Absorption 発火 → SignalEngine の veto 経路まで到達すること
- depth を含まない既存 fixture のリプレイで従来と完全同一の結果（後方互換）

合計 17 本以上、既存 168 tests は 1 本も変更・削除しない。

---

## 7. CompletionLog.md

`ArchitectureRepository/00_Master/CompletionLog.md` を新規作成し、以下 2 エントリを時系列で記載する:

1. **B-1**（後追い）: 成果物・テスト 168 passed・逸脱なし
2. **B-2**（本指示書）: 完了時に追記

以後、全指示書完了時に末尾追記する運用である旨を冒頭に明記する。

---

## 8. 完了条件

- [ ] 全計算経路 Decimal（`float(` 出現 0 件、テスト内 float リテラル含む）
- [ ] TV-ABS-01〜05 green（逐語）
- [ ] 新規 17 本以上 green、既存 168 本無影響で green（合計 185 本以上）
- [ ] `AbsorptionResult` のシグネチャ不変
- [ ] `pipeline.py` に `absorption_result=None` のリテラル固定接続が残存しない
- [ ] `ImbalanceDetector` の既存呼び出し（volume_ref なし）の挙動完全不変
- [ ] `docs/`（Repository 正本）無変更
- [ ] CompletionLog.md 作成（B-1 後追い含む）

---

## 9. 報告

完了時、以下 3 点セットを提出する:

1. `CompletionLog.md` への B-2 エントリ追記
2. `DeltaEngine_B2_完了.zip`（`__pycache__` / `.pytest_cache` / `data/parquet` / `data/duckdb` 除外可、`ArchitectureRepository/` と `project/` は全て含む）
3. チャット完了報告: 新規テスト件数（168 + n）、TV-ABS-01〜05 実測結果、§5 決定 5 点からの逸脱有無、次フェーズ着手可否の一言
